from unittest.mock import DEFAULT
from openai.types.chat import ChatCompletionUserMessageParam, ChatCompletionSystemMessageParam, ChatCompletionAssistantMessageParam
from openai.types.chat.completion_create_params import ResponseFormat
from openai.types.shared_params.response_format_json_object import ResponseFormatJSONObject
from openai.types.shared_params.response_format_text import ResponseFormatText
from agents.tool_schemas import TOOL_SCHEMAS, format_tool_schema
from prompts import DEFAULT_SYSTEM_PROMPT_PARTS
from custom_dataclasses import APICall, ChatMessage
import time
import json
from typing import Dict, Any, Optional, Set, List, Union
from constants import ToolName

def get_formatted_tool_schemas(tools: Optional[Set[ToolName]], system_prompt_parts: Optional[Dict[str, Dict[str, Union[bool, int]]]] = None) -> Optional[List[Dict[str, Any]]]:
    """Get formatted tool schemas without modifying the original schemas.
    
    Args:
        tools: Set of tool names to format, or None
        system_prompt_parts: Optional dict of system prompt parts to use for formatting.
                           If None, uses DEFAULT_SYSTEM_PROMPT_PARTS.
    
    Returns:
        List of formatted tool schemas or None if no tools provided or no valid schemas found
    """
    if not tools:
        return None
        
    formatted_tools = []
    for tool in tools:
        if tool not in TOOL_SCHEMAS:
            continue
            
        schema = TOOL_SCHEMAS[tool].copy()
        # Only format toggle_prompt_part if system_prompt_parts is provided or using defaults
        if tool == ToolName.TOGGLE_PROMPT_PART:
            current_parts = system_prompt_parts or DEFAULT_SYSTEM_PROMPT_PARTS
            schema = format_tool_schema(schema, system_prompt_parts=current_parts)
                
        formatted_tools.append(schema)
        
    return formatted_tools if formatted_tools else None

def convert_to_openai_params(call: APICall) -> Dict[str, Any]:
    """Convert APICall to OpenAI API parameters."""
    openai_messages = []
    
    # Add system message as first message
    if call.model.startswith('o1'):
        # For o1-preview models, convert system message to user message
        openai_messages.append(ChatCompletionUserMessageParam(role="user", content=call.system_message))
    else:
        openai_messages.append(ChatCompletionSystemMessageParam(role="system", content=call.system_message))
    
    # Handle remaining messages
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
        formatted_tools = get_formatted_tool_schemas(call.tools, call.system_prompt_parts)
        if formatted_tools:
            api_params["tools"] = formatted_tools
            api_params["tool_choice"] = "auto"
            api_params["response_format"] = ResponseFormatJSONObject(type="json_object")
    
    return api_params

def convert_from_openai_response(response, call: APICall) -> Dict[str, Any]:
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

def convert_to_anthropic_params(call: APICall) -> Dict[str, Any]:
    """Convert APICall to Anthropic API parameters."""
    api_params = {
        "model": call.model,
        "temperature": call.temperature,
        "max_tokens": call.max_completion_tokens,
        "system": call.system_message
    }
    
    # Make a copy of messages to avoid modifying the original
    messages = list(call.messages)
    
    # Group messages by name and role
    processed_messages = []
    pending_system_msgs = []
    
    def flush_system_messages():
        if not pending_system_msgs:
            return
        system_content = "\n\n".join(pending_system_msgs)
        
        # Case 1: Append to prior user message if it exists
        if processed_messages and processed_messages[-1].role == "user":
            processed_messages[-1].content = f"{processed_messages[-1].content}\n\nSYSTEM: {system_content}"
        # Case 3: Create new user message if no prior user message
        else:
            processed_messages.append(ChatMessage(
                role="user",
                content=f"SYSTEM: {system_content}",
                name=None
            ))
        pending_system_msgs.clear()
    
    for i, msg in enumerate(messages):
        # Handle system messages
        if msg.role == "system":
            pending_system_msgs.append(msg.content)
            # Look ahead to next non-system message
            next_msg = None
            for future_msg in messages[i+1:]:
                if future_msg.role != "system":
                    next_msg = future_msg
                    break
            
            # Case 2: If next message is user, save for prepending
            # Otherwise, flush system messages now
            if not next_msg or next_msg.role != "user":
                flush_system_messages()
            continue
        
        # Add name prefix for user messages
        if msg.role == "user" and msg.name:
            msg.content = f"{msg.name.upper()}: {msg.content}"
        
        # If this is a user message and there are pending system messages,
        # prepend them (Case 2)
        if msg.role == "user" and pending_system_msgs:
            system_content = "\n\n".join(pending_system_msgs)
            msg.content = f"SYSTEM: {system_content}\n\n{msg.content}"
            pending_system_msgs.clear()
        
        processed_messages.append(msg)
    
    # Handle any remaining system messages at the end
    flush_system_messages()
    
    messages = processed_messages
    
    # Group messages by name and role
    current_group = []
    anthropic_messages = []
    prev_name = None
    prev_role = None
    
    def flush_group():
        if not current_group:
            return
        # Get role and name from the first message in group
        role = current_group[0].role
        name = current_group[0].name
        
        # Combine contents with double newlines
        contents = [msg.content for msg in current_group if msg.content.strip()]
        if not contents:
            return
        
        content = "\n\n".join(contents)
        
        # For assistant messages, add name prefix only in the Anthropic message
        if role == "assistant" and name:
            content = f"{name.upper()}: {content}"
        
        anthropic_messages.append({
            "role": role,
            "content": content
        })
    
    for msg in messages:
        name = msg.name
        role = msg.role
        
        # If name or role changes, flush the current group
        if name != prev_name or role != prev_role:
            flush_group()
            current_group = []
        
        current_group.append(msg)
        prev_name = name
        prev_role = role
    
    # Flush the final group
    flush_group()
    
    # Ensure alternating pattern by adding messages
    final_messages = []
    prev_role = None
    
    for msg in anthropic_messages:
        if prev_role and prev_role == msg["role"]:
            final_messages.append({
                "role": "assistant" if msg["role"] == "user" else "user",
                "content": "..."
            })
        final_messages.append(msg)
        prev_role = msg["role"]
    
    api_params["messages"] = final_messages
    
    # Convert tool schemas if present
    if call.tools:
        formatted_tools = get_formatted_tool_schemas(call.tools, call.system_prompt_parts)
        if formatted_tools:
            tools = []
            for tool in formatted_tools:
                anthropic_tool = {
                    "name": tool["function"]["name"],
                    "description": tool["function"]["description"],
                    "input_schema": tool["function"]["parameters"]
                }
                tools.append(anthropic_tool)
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}
    
    return api_params

def convert_from_anthropic_response(response, call: APICall) -> Dict[str, Any]:
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