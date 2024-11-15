import asyncio
import time
from typing import Any, Callable, Optional, NamedTuple, List, Dict
from dataclasses import dataclass
from collections import deque
from shared_resources import logger, openai_client
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionUserMessageParam
from openai.types.chat.completion_create_params import ResponseFormat
from openai.types.shared_params.response_format_json_object import ResponseFormatJSONObject
from openai.types.shared_params.response_format_text import ResponseFormatText

# Rate limits
REQUESTS_PER_MINUTE = 5000
TOKENS_PER_MINUTE = 2000000

# Derived constants
REQUESTS_PER_TENTH = REQUESTS_PER_MINUTE / 600  # ≈8.33 requests per 0.1s

@dataclass
class APICall:
    model: str
    messages: List[Dict[str, Any]]
    response_format: Dict[str, str]
    future: asyncio.Future
    timestamp: float

# Global state
_request_times: deque[float] = deque(maxlen=int(REQUESTS_PER_TENTH))
_pending_calls: deque[APICall] = deque()
_processor_task: Optional[asyncio.Task] = None
_batch_lock = asyncio.Lock()

def _convert_response_format(format_dict: Dict[str, str]) -> ResponseFormat:
    """Convert generic response format dict to OpenAI type."""
    if format_dict.get("type") == "json_object":
        return ResponseFormatJSONObject(type="json_object")
    return ResponseFormatText(type="text")

async def _process_pending_calls() -> None:
    """Process pending API calls within rate limits."""
    while True:
        try:
            async with _batch_lock:
                current_time = time.time()
                
                # Remove timestamps older than 0.1 seconds
                while _request_times and _request_times[0] < current_time - 0.1:
                    _request_times.popleft()
                
                calls_to_process = []
                while _pending_calls and len(_request_times) < REQUESTS_PER_TENTH:
                    calls_to_process.append(_pending_calls.popleft())
                    _request_times.append(current_time)
                
                # Create tasks for each call without waiting for them
                if calls_to_process:
                    logger.debug(f"Creating {len(calls_to_process)} API call tasks")
                    for call in calls_to_process:
                        asyncio.create_task(_execute_call(call))
            
            # Wait until next 0.1s window
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error in processor: {str(e)}")
            if asyncio.get_event_loop().get_debug():
                raise

async def _execute_call(call: APICall) -> None:
    """Execute a single API call and set its future."""
    try:
        openai_messages = [
            ChatCompletionUserMessageParam(
                role=msg["role"],
                content=msg["content"]
            ) for msg in call.messages
        ]
        
        response = await openai_client.chat.completions.create(
            model=call.model,
            messages=openai_messages,
            response_format=_convert_response_format(call.response_format)
        )
        
        # Package only what we need in a clean format
        assert response.usage is not None, "API response missing 'usage'"
        result = {
            "content": response.choices[0].message.content,
            "token_usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
        call.future.set_result(result)
    except Exception as e:
        logger.error(f"API call failed: {str(e)}")
        call.future.set_exception(e)

def enqueue_api_call(
    model: str,
    messages: List[Dict[str, Any]],
    response_format: Dict[str, str]
) -> asyncio.Future:
    """Add an API call to the queue and return a future for its result."""
    if _processor_task is None:
        raise RuntimeError("API queue not started. Call start_api_queue() first.")
        
    future: asyncio.Future = asyncio.get_event_loop().create_future()
    call = APICall(
        model=model,
        messages=messages,
        response_format=response_format,
        future=future,
        timestamp=time.time()
    )
    _pending_calls.append(call)
    return future

async def start_api_queue() -> None:
    """Start the API queue processor."""
    global _processor_task
    if _processor_task is None:
        _processor_task = asyncio.create_task(_process_pending_calls())

async def stop_api_queue() -> None:
    """Stop the API queue processor."""
    global _processor_task
    if _processor_task is not None:
        _processor_task.cancel()
        try:
            await _processor_task
        except asyncio.CancelledError:
            pass
        _processor_task = None