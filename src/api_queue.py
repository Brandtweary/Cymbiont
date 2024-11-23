import asyncio
import time
from typing import Any, Callable, Optional, NamedTuple, List, Dict
from dataclasses import dataclass
from collections import deque
from shared_resources import logger, openai_client, token_logger
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionUserMessageParam, ChatCompletionSystemMessageParam, ChatCompletionAssistantMessageParam
from openai.types.chat.completion_create_params import ResponseFormat
from openai.types.shared_params.response_format_json_object import ResponseFormatJSONObject
from openai.types.shared_params.response_format_text import ResponseFormatText
from custom_dataclasses import APICall, TokenUsage, ChatMessage


# Constants
REQUESTS_PER_MINUTE: int = 5000
TOKENS_PER_MINUTE: int = 2000000
BATCH_TIMER: float = 0.1  # seconds
BATCH_LIMIT: int = int(REQUESTS_PER_MINUTE * BATCH_TIMER / 60)  # requests per batch
TPM_WINDOW: float = 60.0  # seconds to look back for token usage
TOKEN_HISTORY_SIZE: int = 1000
TPM_SOFT_LIMIT: float = 0.75  # percentage where interpolation begins

# Global state
_pending_calls: deque[APICall] = deque()
_processor_task: Optional[asyncio.Task] = None
_batch_lock = asyncio.Lock()
_token_history: deque[TokenUsage] = deque(maxlen=TOKEN_HISTORY_SIZE)

def _convert_response_format(format_dict: Dict[str, str]) -> ResponseFormat:
    """Convert generic response format dict to OpenAI type."""
    if format_dict.get("type") == "json_object":
        return ResponseFormatJSONObject(type="json_object")
    return ResponseFormatText(type="text")

async def _process_pending_calls() -> None:
    """Process pending API calls within rate limits.
    Processes up to BATCH_LIMIT calls every BATCH_TIMER seconds."""
    while True:
        try:
            async with _batch_lock:
                current_time = time.time()
                
                # Clean up old token usage records and calculate recent usage
                while _token_history and _token_history[0].timestamp < current_time - TPM_WINDOW:
                    _token_history.popleft()
                
                recent_tokens = sum(usage.tokens for usage in _token_history)
                tokens_per_minute = recent_tokens * (60 / TPM_WINDOW)  # extrapolate to per-minute rate
                
                # Calculate interpolated batch limit
                interpolation_factor = 1.0
                if tokens_per_minute > TOKENS_PER_MINUTE * TPM_SOFT_LIMIT:
                    # Linear interpolation between soft limit and hard limit
                    interpolation_factor = max(0.0, 
                        1.0 - (tokens_per_minute - TOKENS_PER_MINUTE * TPM_SOFT_LIMIT) / 
                        (TOKENS_PER_MINUTE * (1.0 - TPM_SOFT_LIMIT)))
                
                interpolated_batch_limit = int(BATCH_LIMIT * interpolation_factor)
                
                # Process up to interpolated_batch_limit calls
                calls_to_process = []
                while _pending_calls and len(calls_to_process) < interpolated_batch_limit:
                    calls_to_process.append(_pending_calls.popleft())
                
                if calls_to_process:
                    logger.debug(f"Creating {len(calls_to_process)} API call tasks " +
                               f"(TPM: {tokens_per_minute:.0f}, factor: {interpolation_factor:.2f})")
                    for call in calls_to_process:
                        asyncio.create_task(_execute_call(call))
            
            # Wait for next batch window
            await asyncio.sleep(BATCH_TIMER)
        except Exception as e:
            logger.error(f"Error in processor: {str(e)}")
            if asyncio.get_event_loop().get_debug():
                raise

async def _execute_call(call: APICall) -> None:
    """Execute a single API call with retry logic."""
    try:
        if call.mock:
            # Check for the special error-triggering message
            if any(msg.content == "halt and catch fire" for msg in call.messages):
                raise RuntimeError("🔥 The system caught fire, as requested")
                
            # Regular mock logic continues...
            mock_tokens = call.mock_tokens if call.mock_tokens is not None else sum(len(msg.content) for msg in call.messages)
            result = {
                "content": call.messages[-1].content,
                "token_usage": {
                    "prompt_tokens": mock_tokens,
                    "completion_tokens": mock_tokens,
                    "total_tokens": mock_tokens * 2
                },
                "timestamp": time.time(),
                "expiration_counter": call.expiration_counter + 1
            }
            mock_total_tokens = result["token_usage"]["total_tokens"]
            token_logger.add_tokens(mock_total_tokens)
        else:
            # Real API call logic
            openai_messages = [
                ChatCompletionSystemMessageParam(role="system", content=msg.content) if msg.role == "system"
                else ChatCompletionUserMessageParam(role="user", content=msg.content) if msg.role == "user"
                else ChatCompletionAssistantMessageParam(role="assistant", content=msg.content)
                for msg in call.messages
            ]
            
            response = await openai_client.chat.completions.create(
                model=call.model,
                messages=openai_messages,
                response_format=_convert_response_format(call.response_format),
                temperature=call.temperature
            )
            assert response.usage is not None, "API response missing 'usage'"

            result = {
                "content": response.choices[0].message.content,
                "token_usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                },
                "timestamp": time.time(),
                "expiration_counter": call.expiration_counter + 1
            }
            token_logger.add_tokens(response.usage.total_tokens)

        # Add token usage to history (both real and mock calls)
        _token_history.append(TokenUsage(
            tokens=result["token_usage"]["total_tokens"],
            timestamp=time.time()
        ))
        
        call.future.set_result(result)
    except Exception as e:
        if call.expiration_counter < 2:  # Allow up to 3 total attempts (0-2)
            logger.warning(f"API call failed (attempt {call.expiration_counter + 1}), retrying: {str(e)}")
            # Re-queue with incremented counter
            new_future = enqueue_api_call(
                model=call.model,
                messages=call.messages,
                response_format=call.response_format,
                mock=call.mock,
                mock_tokens=call.mock_tokens,
                expiration_counter=call.expiration_counter + 1,
                temperature=call.temperature
            )
            # Link the futures
            new_future.add_done_callback(
                lambda f: call.future.set_result(f.result()) if not f.exception() 
                else call.future.set_exception(f.exception() or RuntimeError("Unknown error occurred"))
            )
        else:
            logger.error(f"API call failed after 3 attempts: {str(e)}")
            call.future.set_exception(e)

def enqueue_api_call(
    model: str,
    messages: List[ChatMessage],
    response_format: Dict[str, str],
    mock: bool = False,
    mock_tokens: Optional[int] = None,
    expiration_counter: int = 0,
    temperature: float = 0.7
) -> asyncio.Future[Dict[str, Any]]:
    """Enqueue an API call with retry counter."""
    call = APICall(
        model=model,
        messages=messages,
        response_format=response_format,
        timestamp=time.time(),
        mock=mock,
        mock_tokens=mock_tokens,
        expiration_counter=expiration_counter,
        future=asyncio.Future(),
        temperature=temperature
    )
    _pending_calls.append(call)
    return call.future

def is_queue_empty() -> bool:
    """Check if the API queue is empty."""
    return len(_pending_calls) == 0

async def clear_token_history() -> None:
    """Clear the token history to prevent test contamination."""
    global _token_history
    _token_history.clear()
    logger.debug("Token history cleared.")

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
