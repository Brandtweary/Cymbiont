import asyncio
from json import tool
from typing import Any, List, Optional, Set, Dict
from dataclasses import dataclass, field
from api_queue import enqueue_api_call
from shared_resources import logger, AGENT_NAME
from constants import CHAT_AGENT_MODEL, LogLevel, ToolName
from prompts import CHAT_AGENT_SYSTEM_PROMPT, TOOL_SCHEMAS
from utils import log_performance, convert_messages_to_string
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionAssistantMessageParam
)
from custom_dataclasses import ChatMessage, ToolLoopData, MessageRole
from chat_history import ChatHistory
import inspect


tool_function_map = {
    ToolName.CONTEMPLATE.value: 'process_contemplate',
    ToolName.EXIT_LOOP.value: 'process_exit_loop',
    ToolName.MESSAGE_SELF.value: 'process_message_self',
    # Add more tool-function mappings here
}


def convert_to_openai_message(message: ChatMessage) -> ChatCompletionMessageParam:
    """Convert our message format to OpenAI's format"""
    if message.role == "system":
        return ChatCompletionSystemMessageParam(role=message.role, content=message.content)
    elif message.role == "user":
        return ChatCompletionUserMessageParam(role=message.role, content=message.content)
    else:  # assistant
        return ChatCompletionAssistantMessageParam(role=message.role, content=message.content)

@log_performance
async def get_response(
    chat_history: ChatHistory,
    tools: Optional[Set[ToolName]] = None,
    tool_loop_data: Optional[ToolLoopData] = None
) -> str:
    """
    Sends a message to the OpenAI chat agent with conversation history.

    Args:
        chat_history: The ChatHistory instance containing the conversation history.
        tools: A set of ToolName enums representing the tools available to the agent.
        loop_message: A message describing information pertinent to the current loop.
        tool_loop_data: An optional ToolLoopData instance to manage the state within a tool loop.

    Returns:
        str: The assistant's response.
    """
    try:
        system_content_parts = [CHAT_AGENT_SYSTEM_PROMPT]

        if tool_loop_data:
            system_content_parts.append(tool_loop_data.loop_message)

        messages, summary = chat_history.get_recent_messages()

        if summary:
            system_content_parts.append(summary)

        system_content = '\n'.join(system_content_parts)

        messages_to_send: List[ChatMessage] = [
            ChatMessage(role="system", content=system_content),
            *messages
        ]

        prompt_text = convert_messages_to_string(messages_to_send, truncate_last=False)
        logger.log(LogLevel.PROMPT, f"{prompt_text}")

        response = await enqueue_api_call(
            model=CHAT_AGENT_MODEL,
            messages=messages_to_send,
            tools=tools,
            response_format={"type": "text"},
            temperature=0.7
        )

        if 'tool_call_results' in response:
            if not isinstance(response['tool_call_results'], dict):
                logger.error(f"Expected dict for tool_call_results, got {type(response['tool_call_results'])}")
                return "Sorry, I encountered an error while processing your request."

            user_message = await process_tool_calls(
                tool_call_results=response['tool_call_results'],
                available_tools=tools,
                tool_loop_data=tool_loop_data,
                chat_history=chat_history
            )
            if user_message:
                if tool_loop_data:
                    prefixed_message = f"[{tool_loop_data.loop_type}_LOOP] {user_message}"
                else:
                    prefixed_message = user_message
                chat_history.add_message("assistant", prefixed_message, name=AGENT_NAME)
                return user_message
            return ''

        if not response["content"]:
            logger.error("Received an empty message from the OpenAI API.")
            return "Sorry, I encountered an error while processing your request."

        if tool_loop_data and tool_loop_data.loop_type:
            prefixed_content = f"[{tool_loop_data.loop_type}_LOOP] {response['content']}"
        else:
            prefixed_content = response["content"]

        chat_history.add_message("assistant", prefixed_content, name=AGENT_NAME)

        return response["content"]
    except Exception as e:
        logger.error(f"Error communicating with OpenAI API: {e}")
        return "Sorry, I encountered an error while processing your request."


async def process_tool_calls(
    tool_call_results: Dict[str, Dict[str, Any]],
    available_tools: Optional[Set[ToolName]],
    tool_loop_data: Optional[ToolLoopData],
    chat_history: ChatHistory
) -> Optional[str]:
    """
    Process tool calls by matching them to corresponding functions.

    Args:
        tool_call_results: A dictionary of tool call results from the API response.
        available_tools: A set of ToolName enums representing the tools available to the agent.
        tool_loop_data: An optional ToolLoopData instance to manage the state within the tool loop.
        chat_history: The ChatHistory instance.

    Returns:
        Optional[str]: A message to be returned to the user, if available.
    """
    messages = []
    for call_id, tool_call in tool_call_results.items():
        assert isinstance(call_id, str), f"Tool call ID must be string, got {type(call_id)}: {call_id}"
        tool_name = tool_call['tool_name']
        arguments = tool_call['arguments']

        try:
            tool_enum = ToolName(tool_name)
        except ValueError:
            logger.error(f"Invalid tool name: {tool_name}")
            continue

        if available_tools and tool_enum not in available_tools:
            logger.error(f"Tool '{tool_name}' is not in the available tools list.")
            continue

        processing_function_name = tool_function_map.get(tool_name)
        if not processing_function_name:
            logger.error(f"No processing function found for tool: {tool_name}")
            continue

        processing_function = globals().get(processing_function_name)
        if not processing_function:
            logger.error(f"Processing function '{processing_function_name}' not found.")
            continue

        tool_schema = TOOL_SCHEMAS[tool_enum]["function"]["parameters"]
        required_params = tool_schema.get("required", [])
        properties = tool_schema.get("properties", {})

        missing_params = [param for param in required_params if param not in arguments]
        if missing_params:
            logger.error(f"Missing required parameters {missing_params} for tool '{tool_name}'")
            continue

        unrecognized_args = [arg for arg in arguments if arg not in properties]
        if unrecognized_args:
            logger.error(f"Unrecognized arguments {unrecognized_args} for tool '{tool_name}'")
            continue

        args_to_pass = {param: arguments[param] for param in required_params}

        try:
            response = await processing_function(
                **args_to_pass,
                tool_loop_data=tool_loop_data,
                chat_history=chat_history
            )
            if response is not None:
                messages.append(response)
                if tool_name == ToolName.EXIT_LOOP.value:
                    pass
        except Exception as e:
            logger.error(f"Error processing tool '{tool_name}': {e}")

    if messages:
        final_message = ' '.join(messages)
        return final_message
    else:
        return None


async def process_contemplate(
    question: str,
    tool_loop_data: Optional[ToolLoopData],
    chat_history: ChatHistory
) -> Optional[str]:
    """
    Process the 'contemplate' tool call.

    Args:
        question: The question to ponder during the contemplation loop.
        tool_loop_data: An optional ToolLoopData instance to manage the state within the tool loop.
        chat_history: The ChatHistory instance.

    Returns:
        Optional[str]: Message to the user, if any.
    """
    
    if tool_loop_data:
        logger.log(LogLevel.TOOL, f"{AGENT_NAME} used tool: contemplate - no effect, agent already inside tool loop")
        return None

    # Start a new contemplation loop
    assert not tool_loop_data, f"Starting contemplate but loop already active: {tool_loop_data}"
    tool_loop_data = ToolLoopData(
        loop_type="CONTEMPLATION",
        available_tools={ToolName.MESSAGE_SELF, ToolName.EXIT_LOOP},
        loop_message=(
            f"You are inside a tool loop contemplating the following question:\n"
            f"{question}\n"
            "To record your thoughts during contemplation, use the message_self tool. "
            "These messages will be added to your chat history and automatically prefixed with [CONTEMPLATION_LOOP], "
            "but will not be shown to the user. This allows you to think through the problem step by step.\n"
            "When you have reached a conclusion, use the exit_loop tool with your final answer "
            "to end contemplation and respond to the user. Do not prefix your messages yourself.\n"
        ),
        active=True
    )

    logger.log(LogLevel.TOOL, f"{AGENT_NAME} used tool: contemplate - now entering contemplation loop")
    max_iterations = 5  # Adjust as needed
    iterations = 0

    while iterations < max_iterations:
        iterations += 1
        response = await get_response(
            chat_history=chat_history,
            tools=tool_loop_data.available_tools,
            tool_loop_data=tool_loop_data
        )
        response = response if isinstance(response, str) else response.get('content', '')
        # Check if exit_loop was called
        if not tool_loop_data.active:
            if not response:
                logger.warning("Exit loop called but no response message provided")
            return response

        # If no response (i.e., continue looping), pass

    if tool_loop_data.active:
        logger.warning("Max iterations reached in contemplation loop without exit.")
        return None

    return None


async def process_exit_loop(
    exit_message: str,
    tool_loop_data: Optional[ToolLoopData],
    chat_history: ChatHistory
) -> Optional[str]:
    """Process the exit_loop tool call."""
    if not tool_loop_data or not tool_loop_data.active:
        logger.warning(f"{AGENT_NAME} used tool: exit_loop - no effect, agent not inside tool loop")
        return None

    tool_loop_data.active = False
    logger.log(LogLevel.TOOL, f"{AGENT_NAME} used tool: exit_loop - exiting tool loop")
    return exit_message


async def process_message_self(
    message: str,
    tool_loop_data: Optional[ToolLoopData],
    chat_history: ChatHistory
) -> str:
    """
    Process the 'message_self' tool call.

    Args:
        message: The message to send to self.
        tool_loop_data: An optional ToolLoopData instance to manage the state within the tool loop.
        chat_history: The ChatHistory instance.

    Returns:
        str: The message that was sent to self.
    """
    logger.log(LogLevel.TOOL, f"{AGENT_NAME} used tool: message_self")
    return message


def register_tools():
    """
    Validate that each tool in tool_function_map has a corresponding processing function
    and that the function parameters match the tool schema.
    
    Raises:
        ValueError: If any tool processing function is missing or parameters do not match.
    """
    for tool_name, function_name in tool_function_map.items():
        try:
            tool_enum = ToolName(tool_name)
            schema = TOOL_SCHEMAS[tool_enum]["function"]["parameters"]
        except KeyError:
            raise ValueError(f"Schema for tool '{tool_name}' not found in TOOL_SCHEMAS.")

        func = globals().get(function_name)
        if not func:
            raise ValueError(f"Processing function '{function_name}' for tool '{tool_name}' not found.")

        sig = inspect.signature(func)

        required_params = schema.get("required", [])
        schema_properties = schema.get("properties", {})

        for param in required_params:
            if param not in sig.parameters:
                raise ValueError(f"Function '{function_name}' missing required parameter '{param}' for tool '{tool_name}'.")

        func_params = set(sig.parameters.keys())
        schema_params = set(schema_properties.keys())
        # Ignore common parameters that are passed to all processing functions
        common_params = {'tool_loop_data', 'chat_history'}
        extra_params = func_params - schema_params - common_params
        if extra_params:
            raise ValueError(f"Function '{function_name}' has unrecognized parameters {extra_params} for tool '{tool_name}'.")

register_tools()
