from openai.types.chat import ChatCompletionUserMessageParam, ChatCompletionSystemMessageParam, ChatCompletionAssistantMessageParam
from openai.types.chat.completion_create_params import ResponseFormat
from openai.types.shared_params.response_format_json_object import ResponseFormatJSONObject
from openai.types.shared_params.response_format_text import ResponseFormatText
from agents.tool_schemas import TOOL_SCHEMAS
from custom_dataclasses import APICall
import time
import json
from typing import Dict, Any


def convert_to_openai_params(call: APICall) -> Dict[str, Any]:
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
    
    # Group remaining system messages with next user message
    processed_messages = []
    pending_system_msgs = []
    
    for msg in messages:
        if msg.role == "system":
            pending_system_msgs.append(msg.content)
            continue
            
        content = msg.content
        if pending_system_msgs and msg.role == "user":
            system_content = "\n\n".join(pending_system_msgs)
            if msg.name:
                content = f"{msg.name.upper()}: {content}"
            content = f"SYSTEM: {system_content}\n\n{content}"
            pending_system_msgs = []
        elif msg.role == "user" and msg.name:
            content = f"{msg.name.upper()}: {content}"
            
        msg.content = content
        processed_messages.append(msg)
    
    messages = processed_messages  # Replace messages with processed version
    
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
        
        # For assistant messages, add name prefix after combining
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
                "content": " "
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