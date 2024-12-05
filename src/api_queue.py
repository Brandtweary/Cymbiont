import asyncio
import time
import json
from typing import Any, Optional, List, Dict, Set, Union, Literal
from collections import deque
from shared_resources import DEBUG_ENABLED, logger, openai_client, anthropic_client
from token_logger import token_logger
from custom_dataclasses import APICall, TokenUsage, ChatMessage, SystemPromptPartsData
from process_log import ProcessLog
from constants import LLM, model_data, ToolName
from api_conversions import convert_from_anthropic_response, convert_from_openai_response, convert_to_anthropic_params, convert_to_openai_params

# Constants
BATCH_INTERVAL_TIME: float = 1/15  # seconds
TPM_WINDOW: float = 60.0  # seconds to look back for token usage
TOKEN_HISTORY_SIZE: int = 1000
TPM_SOFT_LIMIT: float = 0.75  # percentage where interpolation begins

# Global state
pending_calls: deque[APICall] = deque()
processor_task: Optional[asyncio.Task] = None
batch_lock = asyncio.Lock()
token_history: Dict[str, List[TokenUsage]] = {}  # per-model token history


async def process_pending_calls() -> None:
    """Process pending API calls within rate limits.
    Processes calls on a per-model basis within their respective rate limits."""
    while True:
        try:
            async with batch_lock:
                current_time = time.time()
                
                # Clean up old token usage records
                for model in list(token_history.keys()):
                    history = token_history[model]
                    cutoff_idx = 0
                    for idx, usage in enumerate(history):
                        if usage.timestamp >= current_time - TPM_WINDOW:
                            break
                        cutoff_idx = idx + 1
                    if cutoff_idx > 0:
                        token_history[model] = history[cutoff_idx:]
                
                # Group pending calls by model
                model_calls: Dict[str, List[APICall]] = {}
                for call in pending_calls:
                    if call.model not in model_calls:
                        model_calls[call.model] = []
                    model_calls[call.model].append(call)
                
                # Process each model's calls separately
                calls_to_process = []
                for model, calls in model_calls.items():
                    model_config = model_data[model]
                    
                    # Calculate requests per minute limit
                    rpm_limit = model_config.get("requests_per_minute", float('inf'))
                    model_batch_limit = int(rpm_limit / (60 / BATCH_INTERVAL_TIME))
                    
                    # Calculate token-based interpolation factor
                    interpolation_factor = 1.0
                    if model not in token_history:
                        token_history[model] = []
                    
                    # Get recent token usage for this model
                    recent_usage = token_history[model]
                    
                    if "total_tokens_per_minute" in model_config:
                        # OpenAI-style total token limiting
                        total_tokens = sum(usage.total_tokens for usage in recent_usage)
                        tokens_per_minute = total_tokens * (60 / TPM_WINDOW)
                        limit = model_config["total_tokens_per_minute"]
                        
                        if tokens_per_minute > limit * TPM_SOFT_LIMIT:
                            interpolation_factor = max(0.0,
                                1.0 - (tokens_per_minute - limit * TPM_SOFT_LIMIT) /
                                (limit * (1.0 - TPM_SOFT_LIMIT)))
                    else:
                        # Anthropic-style separate input/output token limiting
                        input_factor = output_factor = 1.0
                        
                        if "input_tokens_per_minute" in model_config:
                            input_tokens = sum(usage.input_tokens for usage in recent_usage)
                            input_tpm = input_tokens * (60 / TPM_WINDOW)
                            input_limit = model_config["input_tokens_per_minute"]
                            
                            if input_tpm > input_limit * TPM_SOFT_LIMIT:
                                input_factor = max(0.0,
                                    1.0 - (input_tpm - input_limit * TPM_SOFT_LIMIT) /
                                    (input_limit * (1.0 - TPM_SOFT_LIMIT)))
                        
                        if "output_tokens_per_minute" in model_config:
                            output_tokens = sum(usage.output_tokens for usage in recent_usage)
                            output_tpm = output_tokens * (60 / TPM_WINDOW)
                            output_limit = model_config["output_tokens_per_minute"]
                            
                            if output_tpm > output_limit * TPM_SOFT_LIMIT:
                                output_factor = max(0.0,
                                    1.0 - (output_tpm - output_limit * TPM_SOFT_LIMIT) /
                                    (output_limit * (1.0 - TPM_SOFT_LIMIT)))
                        
                        # Use the more restrictive factor
                        interpolation_factor = min(input_factor, output_factor)
                    
                    # Calculate final batch limit for this model
                    model_interpolated_limit = int(model_batch_limit * interpolation_factor)
                    
                    # Select calls to process for this model
                    model_calls_to_process = []
                    while calls and len(model_calls_to_process) < model_interpolated_limit:
                        model_calls_to_process.append(calls.pop(0))
                    
                    if model_calls_to_process:
                        logger.debug(
                            f"Processing {len(model_calls_to_process)} API calls: {model} "
                        )
                    
                    calls_to_process.extend(model_calls_to_process)
                
                # Remove processed calls from pending_calls
                remaining_calls = deque()
                for call in pending_calls:
                    if call not in calls_to_process:
                        remaining_calls.append(call)
                pending_calls.clear()
                pending_calls.extend(remaining_calls)
                
                # Create tasks for processing
                if calls_to_process:
                    for call in calls_to_process:
                        asyncio.create_task(execute_call(call))
            
            # Wait for next batch window
            await asyncio.sleep(BATCH_INTERVAL_TIME)
        except Exception as e:
            logger.error(f"Error in processor: {str(e)}")
            if DEBUG_ENABLED:
                raise

async def execute_call(call: APICall) -> None:
    """Execute a single API call with retry logic."""
    try:
        if call.mock:
            # Check for the special error-triggering message
            if any(msg.content == "halt and catch fire" for msg in call.messages):
                raise RuntimeError("🔥 The system caught fire, as requested")
            
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
                api_params = convert_to_openai_params(call)
                response = await openai_client.chat.completions.create(**api_params)
                assert response.usage is not None, "API response missing 'usage'"
                result = convert_from_openai_response(response, call)
                token_logger.add_tokens(result["token_usage"]["total_tokens"])
            elif call.provider == "anthropic":
                api_params = convert_to_anthropic_params(call)
                response = await anthropic_client.messages.create(**api_params)
                result = convert_from_anthropic_response(response, call)
                token_logger.add_tokens(result["token_usage"]["total_tokens"])
            else:
                raise ValueError(f"Unknown provider: {call.provider}")
        
        # Initialize token history for model if it doesn't exist
        if call.model not in token_history:
            token_history[call.model] = []
            
        # Add token usage to history (both real and mock calls)
        token_history[call.model].append(TokenUsage(
            input_tokens=result["token_usage"]["prompt_tokens"],
            output_tokens=result["token_usage"]["completion_tokens"],
            total_tokens=result["token_usage"]["total_tokens"],
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
                system_message=call.system_message,
                timestamp=call.timestamp,
                mock=call.mock,
                mock_tokens=call.mock_tokens,
                expiration_counter=call.expiration_counter + 1,
                future=call.future,
                provider=call.provider,
                temperature=call.temperature,
                process_log=call.process_log,
                max_completion_tokens=call.max_completion_tokens,
                tools=call.tools,
                system_prompt_parts=call.system_prompt_parts,
                tool_choice=call.tool_choice
            )
            pending_calls.append(new_call)
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
    system_message: str,
    mock: bool = False,
    mock_tokens: Optional[int] = None,
    expiration_counter: int = 0,
    temperature: float = 0.7,
    process_log: Optional[ProcessLog] = None,
    tools: Optional[Set[ToolName]] = None,
    max_completion_tokens: int = 4000,
    system_prompt_parts: Optional[SystemPromptPartsData] = None,
    tool_choice: Literal["auto", "required", "none"] = "auto"
) -> asyncio.Future[Dict[str, Any]]:
    """Enqueue an API call with retry counter."""
    try:
        model_config = model_data[model]
        provider = model_config["provider"]
        
        # Enforce max_output_tokens limit
        model_max_tokens = model_config["max_output_tokens"]
        if max_completion_tokens > model_max_tokens:
            logger.warning(
                f"Requested max_completion_tokens ({max_completion_tokens}) exceeds model's "
                f"max_output_tokens ({model_max_tokens}). Reducing to {model_max_tokens}."
            )
            max_completion_tokens = model_max_tokens
            
    except KeyError:
        raise ValueError(f"Unknown model: {model}. Model must be one of: {list(model_data.keys())}")
    
    call = APICall(
        model=model,
        system_message=system_message,
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
        tools=tools,
        system_prompt_parts=system_prompt_parts,
        tool_choice=tool_choice
    )
    pending_calls.append(call)
    return call.future

def is_queue_empty() -> bool:
    """Check if the API queue is empty."""
    return len(pending_calls) == 0

async def clear_token_history() -> None:
    """Clear the token history to prevent test contamination."""
    global token_history
    token_history.clear()
    logger.debug("Token history cleared.")

async def start_api_queue() -> None:
    """Start the API queue processor."""
    global processor_task
    if processor_task is None:
        processor_task = asyncio.create_task(process_pending_calls())

async def stop_api_queue() -> None:
    """Stop the API queue processor."""
    global processor_task
    if processor_task is not None:
        processor_task.cancel()
        try:
            await processor_task
        except asyncio.CancelledError:
            pass
        processor_task = None
