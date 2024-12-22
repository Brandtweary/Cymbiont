import json
import re
import time
import torch
from typing import Dict, Any, List, Optional, Set, Literal
from .llm_types import APICall, ChatMessage, ToolName
from .model_configuration import model_data
from shared_resources import logger
from agents.tool_schemas import TOOL_SCHEMAS
from transformers import AutoTokenizer
import asyncio
from functools import partial

def format_llama_input(
    tokenizer: AutoTokenizer,
    system_message: str,
    messages: List[ChatMessage],
    tools: Optional[Set[ToolName]] = None,
    tool_choice: Literal["auto", "required", "none"] = "none"
) -> torch.Tensor:
    """Format input for Llama models using the model's chat template.
    
    Args:
        tokenizer: The model's tokenizer
        system_message: System message to prepend
        messages: List of chat messages
        tools: Optional list of tool names to include
        tool_choice: Tool choice mode ("auto", "required", or "none")
    
    Returns:
        Tensor containing the formatted input
    """
    # Prepare tools if enabled
    tool_definitions = [TOOL_SCHEMAS[tool_name] for tool_name in tools] if tools else []
    if tools and tool_choice != "none":
        tool_instruction = {
            "auto": "-- Tool Instructions --\nYou can use tools when helpful. When using a tool, respond with a JSON object in the format: {\"name\": tool_name, \"parameters\": {parameter_dict}}",
            "required": "-- Tool Instructions --\nYou must use one of the available tools to respond. Respond with a JSON object in the format: {\"name\": tool_name, \"parameters\": {parameter_dict}}"
        }[tool_choice]
        
        system_message = f"{system_message}\n\n{tool_instruction}"

    # Format messages with proper name prefixes
    chat_messages = []
    
    # Add system message first
    chat_messages.append({
        "role": "system",
        "content": f"SYSTEM: {system_message}"
    })
    
    # Add remaining messages with name prefixes
    for msg in messages:
        content = msg.content
        
        if msg.role == "system":
            if msg.name:
                content = f"{msg.name.upper()}: {content}"
            else:
                content = f"SYSTEM: {content}"
        else:  # user or assistant
            if msg.name:
                content = f"{msg.name.upper()}: {content}"
        
        chat_messages.append({"role": msg.role, "content": content})
    
    # Apply chat template and convert to tensor
    device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        logger.debug("Attempting to use chat template...")
        formatted_input = tokenizer.apply_chat_template(  # type: ignore
            chat_messages,
            add_generation_prompt=True,
            return_tensors="pt",
            tools=tool_definitions if tools and tool_choice != "none" else None
        ).to(device)
    except Exception as e:
        logger.error(f"Failed to format input with tokenizer {type(tokenizer).__name__}: {str(e)}")
        logger.error(f"Available tokenizer methods: {dir(tokenizer)}")
        raise
        
    return formatted_input

async def generate_completion(api_call: APICall):
    """Generate a completion using a local Llama model."""
    # Get model and tokenizer from model configuration
    model_info = model_data.get(api_call.model)
    if not model_info or not model_info.get("model") or not model_info.get("tokenizer"):
        raise RuntimeError(f"{api_call.model} missing model or tokenizer.")
        
    model = model_info["model"]
    tokenizer = model_info["tokenizer"]
    
    try:
        model.eval()  # Ensure model is in eval mode
        
        # Format input
        formatted_input = format_llama_input(
            tokenizer=tokenizer,
            system_message=api_call.system_message,
            messages=api_call.messages,
            tools=api_call.tools,
            tool_choice=api_call.tool_choice
        )
        prompt_tokens = len(formatted_input[0])
            
        logger.debug("Running model inference...")
        
        with torch.inference_mode():
            outputs = model.generate(
                formatted_input,
                max_new_tokens=api_call.max_completion_tokens,
                temperature=api_call.temperature,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
            
        # Decode only the new tokens
        response = tokenizer.decode(
            outputs[0][prompt_tokens:],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True
        )
        
        completion_tokens = len(outputs[0]) - prompt_tokens
        
        result = {
            "content": response,
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            },
            "timestamp": time.time(),
            "expiration_counter": api_call.expiration_counter + 1
        }
        
        # Parse tool calls if present
        if api_call.tools and api_call.tool_choice != "none":
            try:
                # Extract JSON from response
                json_match = re.search(r'\{.*\}', response)
                if json_match:
                    tool_call = json.loads(json_match.group())
                    result["content"] = None  # No text response when tool calling
                    result["tool_call_results"] = {
                        "0": {  # Using "0" as ID since we don't have multiple tool calls yet
                            "tool_name": tool_call["name"],
                            "arguments": tool_call["parameters"]
                        }
                    }
            except json.JSONDecodeError:
                pass  # Handle as regular text response if JSON parsing fails
        
        return result
        
    except Exception as e:
        logger.error(f"Error in generate_completion: {str(e)}", exc_info=True)
        raise