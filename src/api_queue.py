import asyncio
import time
import json
from typing import Any, Callable, Optional, NamedTuple, List, Dict, Set
from collections import deque
from shared_resources import logger, openai_client, anthropic_client, token_logger
from openai.types.chat import ChatCompletionUserMessageParam, ChatCompletionSystemMessageParam, ChatCompletionAssistantMessageParam
from openai.types.chat.completion_create_params import ResponseFormat
from openai.types.shared_params.response_format_json_object import ResponseFormatJSONObject
from openai.types.shared_params.response_format_text import ResponseFormatText
from custom_dataclasses import APICall, TokenUsage, ChatMessage
from process_log import ProcessLog
from constants import ToolName, MODEL_PROVIDERS
from tool_schemas import TOOL_SCHEMAS

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

def _convert_to_openai_params(call: APICall) -> Dict[str, Any]:
    """Convert APICall to OpenAI API parameters."""
    openai_messages = []
    for msg in call.messages:
        # For o1-preview models, convert system messages to user messages
        if call.model.startswith('o1') and msg.role == "system":
            openai_messages.append(ChatCompletionUserMessageParam(role="user", content=msg.content))
        else:
            if msg.role == "system":
                openai_messages.append(ChatCompletionSystemMessageParam(role="system", content=msg.content))
            elif msg.role == "user":
                if msg.name:
                    openai_messages.append(ChatCompletionUserMessageParam(role="user", content=msg.content, name=msg.name))
                else:
                    openai_messages.append(ChatCompletionUserMessageParam(role="user", content=msg.content))
            elif msg.role == "assistant":
                if msg.name:
                    openai_messages.append(ChatCompletionAssistantMessageParam(role="assistant", content=msg.content, name=msg.name))
                else:
                    openai_messages.append(ChatCompletionAssistantMessageParam(role="assistant", content=msg.content))
    
    api_params = {
        "model": call.model,
        "messages": openai_messages,
        "temperature": call.temperature,
        "max_tokens": call.max_completion_tokens
    }
    
    if call.tools:
        selected_tool_schemas = [schema for tool, schema in TOOL_SCHEMAS.items() if tool in call.tools]
        api_params["tools"] = selected_tool_schemas
        api_params["tool_choice"] = "auto"
        api_params["response_format"] = ResponseFormatJSONObject(type="json_object")
    
    return api_params

def _convert_from_openai_response(response, call: APICall) -> Dict[str, Any]:
    """Convert OpenAI API response to our standard format."""
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
    
    if response.choices[0].finish_reason == 'tool_calls' and response.choices[0].message.tool_calls:
        tool_call_results = {}
        for tool_call in response.choices[0].message.tool_calls:
            arguments = json.loads(tool_call.function.arguments)
            tool_call_results[str(tool_call.id)] = {
                "tool_name": tool_call.function.name,
                "arguments": arguments
            }
        result["tool_call_results"] = tool_call_results
    
    return result

def _convert_to_anthropic_params(call: APICall) -> Dict[str, Any]:
    """Convert APICall to Anthropic API parameters."""
    api_params = {
        "model": call.model,
        "temperature": call.temperature,
        "max_tokens": call.max_completion_tokens
    }
    
    # Extract the first system message for the system parameter
    messages = list(call.messages)  # Make a copy so we don't modify the original
    system_message = None
    for i, msg in enumerate(messages):
        if msg.role == "system":
            system_message = messages.pop(i)
            break
    
    if system_message:
        api_params["system"] = system_message.content
    
    # Group messages by name and role
    current_group = []
    anthropic_messages = []
    prev_name = None
    prev_role = None
    
    def flush_group():
        if not current_group:
            return
        # Get role and name from the first message in group
        role = "user" if current_group[0].role == "system" else current_group[0].role
        name = current_group[0].name if current_group[0].name else "System" if current_group[0].role == "system" else None
        
        # Combine contents with double newlines
        contents = [msg.content for msg in current_group if msg.content.strip()]
        if not contents:
            return
        
        content = "\n\n".join(contents)
        if name:
            content = f"{name.upper()}: {content}"
        
        anthropic_messages.append({
            "role": role,
            "content": content
        })
    
    for msg in messages:
        name = msg.name if msg.name else "System" if msg.role == "system" else None
        role = "user" if msg.role == "system" else msg.role
        
        # If name or role changes, flush the current group
        if name != prev_name or role != prev_role:
            flush_group()
            current_group = []
        
        current_group.append(msg)
        prev_name = name
        prev_role = role
    
    # Flush the final group
    flush_group()
    
    # Ensure alternating pattern by adding messages with {no content}
    final_messages = []
    prev_role = None
    
    for msg in anthropic_messages:
        if prev_role and prev_role == msg["role"]:
            final_messages.append({
                "role": "assistant" if msg["role"] == "user" else "user",
                "content": "{NO CONTENT}"
            })
        final_messages.append(msg)
        prev_role = msg["role"]
    
    api_params["messages"] = final_messages
    
    # Convert tool schemas if present
    if call.tools:
        tools = []
        for tool in call.tools:
            schema = TOOL_SCHEMAS[tool]
            anthropic_tool = {
                "name": schema["function"]["name"],
                "description": schema["function"]["description"],
                "input_schema": schema["function"]["parameters"]
            }
            tools.append(anthropic_tool)
        api_params["tools"] = tools
        api_params["tool_choice"] = {"type": "auto"}
    
    return api_params

def _convert_from_anthropic_response(response, call: APICall) -> Dict[str, Any]:
    """Convert Anthropic API response to our standard format."""
    result = {
        "content": "",  # Will be populated below
        "token_usage": {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens
        },
        "timestamp": time.time(),
        "expiration_counter": call.expiration_counter + 1
    }
    
    # Handle different content types
    tool_call_results = {}
    for content_block in response.content:
        if content_block.type == "text":
            result["content"] = content_block.text
        elif content_block.type == "tool_use":
            tool_call_results[content_block.id] = {
                "tool_name": content_block.name,
                "arguments": content_block.input
            }
    
    if tool_call_results:
        result["tool_call_results"] = tool_call_results
    
    return result

async def process_pending_calls() -> None:
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
                        asyncio.create_task(execute_call(call))
            
            # Wait for next batch window
            await asyncio.sleep(BATCH_TIMER)
        except Exception as e:
            logger.error(f"Error in processor: {str(e)}")
            if asyncio.get_event_loop().get_debug():
                raise

async def execute_call(call: APICall) -> None:
    """Execute a single API call with retry logic."""
    try:
        if call.mock:
            # Check for the special error-triggering message
            if any(msg.content == "halt and catch fire" for msg in call.messages):
                raise RuntimeError(" The system caught fire, as requested")
                
            # Regular mock logic continues...
            mock_tokens = call.mock_tokens if call.mock_tokens is not None else len(call.messages[-1].content.split())
            
            # Pop the last message instead of just accessing it
            mock_content = call.messages.pop().content
            result = {
                "content": mock_content,
                "token_usage": {
                    "prompt_tokens": mock_tokens,
                    "completion_tokens": mock_tokens,
                    "total_tokens": mock_tokens * 2
                },
                "timestamp": time.time(),
                "expiration_counter": call.expiration_counter + 1
            }
            
            # If the mock content is a tool call, parse it as such
            try:
                tool_call_data = json.loads(mock_content)
                if "tool_call_results" in tool_call_data:
                    result["tool_call_results"] = tool_call_data["tool_call_results"]
            except (json.JSONDecodeError, TypeError):
                pass
        else:
            # Real API call logic
            if call.provider == "openai":
                api_params = _convert_to_openai_params(call)
                response = await openai_client.chat.completions.create(**api_params)
                assert response.usage is not None, "API response missing 'usage'"
                result = _convert_from_openai_response(response, call)
                token_logger.add_tokens(response.usage.total_tokens)
            elif call.provider == "anthropic":
                api_params = _convert_to_anthropic_params(call)
                response = await anthropic_client.messages.create(**api_params)
                result = _convert_from_anthropic_response(response, call)
                token_logger.add_tokens(result["token_usage"]["total_tokens"])
            else:
                raise ValueError(f"Unknown provider: {call.provider}")
        
        # Add token usage to history (both real and mock calls)
        _token_history.append(TokenUsage(
            tokens=result["token_usage"]["total_tokens"],
            timestamp=time.time()
        ))
        
        call.future.set_result(result)
    except Exception as e:
        if call.expiration_counter < 2:  # Allow up to 3 total attempts (0-2)
            error_msg = f"API call failed (attempt {call.expiration_counter + 1}), retrying: {str(e)}"
            logger.warning(error_msg)
            if call.process_log:
                call.process_log.warning(error_msg)
                
            # Re-queue with incremented counter
            new_call = APICall(
                model=call.model,
                messages=call.messages,
                timestamp=call.timestamp,
                mock=call.mock,
                mock_tokens=call.mock_tokens,
                expiration_counter=call.expiration_counter + 1,
                future=call.future,
                provider=call.provider,
                temperature=call.temperature,
                process_log=call.process_log,
                max_completion_tokens=call.max_completion_tokens,
                tools=call.tools 
            )
            _pending_calls.append(new_call)
        else:
            # Add standardized attempt count message
            attempt_msg = f"Final attempt count: {call.expiration_counter + 1}"
            if call.process_log:
                call.process_log.debug(attempt_msg)
            logger.debug(attempt_msg)
            
            # Original error message
            error_msg = f"API call failed after 3 attempts: {str(e)}"
            logger.error(error_msg)
            if call.process_log:
                call.process_log.error(error_msg)
            call.future.set_exception(e)

def enqueue_api_call(
    model: str,
    messages: List[ChatMessage],
    mock: bool = False,
    mock_tokens: Optional[int] = None,
    expiration_counter: int = 0,
    temperature: float = 0.7,
    process_log: Optional[ProcessLog] = None,
    tools: Optional[Set[ToolName]] = None,
    max_completion_tokens: int = 4000
) -> asyncio.Future[Dict[str, Any]]:
    """Enqueue an API call with retry counter."""
    try:
        provider = MODEL_PROVIDERS[model]
    except KeyError:
        raise ValueError(f"Unknown model: {model}. Model must be one of: {list(MODEL_PROVIDERS.keys())}")
    
    call = APICall(
        model=model,
        messages=messages,
        timestamp=time.time(),
        mock=mock,
        mock_tokens=mock_tokens,
        expiration_counter=expiration_counter,
        future=asyncio.Future(),
        provider=provider,
        temperature=temperature,
        process_log=process_log,
        max_completion_tokens=max_completion_tokens,
        tools=tools
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
        _processor_task = asyncio.create_task(process_pending_calls())

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
