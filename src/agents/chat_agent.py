import asyncio
from typing import Any, List, Optional, Set, Dict, Tuple, Union, Callable
from api_queue import enqueue_api_call
from shared_resources import logger, AGENT_NAME, DEBUG_ENABLED
from constants import LogLevel, ToolName
from model_configuration import CHAT_AGENT_MODEL
from prompt_helpers import get_system_message
from custom_dataclasses import ChatMessage, ToolLoopData, SystemPromptPartsData, SystemPromptPartInfo
from .tool_schemas import TOOL_SCHEMAS
from utils import log_performance, convert_messages_to_string
from .chat_history import ChatHistory
import inspect
from functools import lru_cache
from prompt_helpers import DEFAULT_SYSTEM_PROMPT_PARTS


@lru_cache(maxsize=1)
def get_tool_function_map():
    """Get the mapping of tool names to their processing functions.
    Lazily imports the functions when first accessed."""
    from .agent_tools import (
                            process_contemplate_loop, 
                            process_exit_loop, 
                            process_message_self,
                            process_execute_shell_command,
                            process_toggle_prompt_part,
                            process_introduce_self,
                            process_shell_loop
                            )
    import inspect
    from . import agent_tools

    tool_map = {
        ToolName.CONTEMPLATE_LOOP.value: process_contemplate_loop,
        ToolName.EXIT_LOOP.value: process_exit_loop,
        ToolName.MESSAGE_SELF.value: process_message_self,
        ToolName.EXECUTE_SHELL_COMMAND.value: process_execute_shell_command,
        ToolName.TOGGLE_PROMPT_PART.value: process_toggle_prompt_part,
        ToolName.INTRODUCE_SELF.value: process_introduce_self,
        ToolName.SHELL_LOOP.value: process_shell_loop
    }

    # Get all functions from agent_tools module
    all_functions = {name: obj for name, obj in inspect.getmembers(agent_tools, inspect.isfunction)}
    mapped_functions = set(tool_map.values())
    
    # Check for unmapped functions (excluding create_tool_loop_data)
    unmapped = [name for name, func in all_functions.items() 
                if func not in mapped_functions 
                and name != 'create_tool_loop_data'
                and name.startswith('process_')]
    
    if unmapped:
        logger.warning(f"Found unmapped tool functions in agent_tools: {', '.join(unmapped)}")

    return tool_map


# Common arguments that can be passed to any tool processing function from process_tool_calls
COMMON_TOOL_ARGS = {
    'chat_history',          
    'tool_loop_data',        
    'token_budget',          
    'mock',                  
    'mock_messages',        
    'system_prompt_parts'
}

@log_performance
async def get_response(
    chat_history: ChatHistory,
    tools: Optional[Set[ToolName]] = None,
    tool_loop_data: Optional[ToolLoopData] = None,
    token_budget: int = 20000,
    mock: bool = False,
    mock_messages: Optional[List[ChatMessage]] = None,
    system_prompt_parts: Optional[SystemPromptPartsData] = None
) -> str:
    """
    Sends a message to the OpenAI chat agent with conversation history.

    Args:
        chat_history: The ChatHistory instance containing the conversation history.
        tools: A set of ToolName enums representing the tools available to the agent.
        tool_loop_data: An optional ToolLoopData instance to manage the state within a tool loop.
        token_budget: Maximum number of tokens allowed for the tool loop. Default is 20000.
        mock: If True, uses mock_messages instead of normal message setup.
        mock_messages: List of mock messages to use when mock=True.
        system_prompt_parts: Optional SystemPromptPartsData instance with prompt parts.

    Returns:
        str: The assistant's response.
    """
    try:
        # Initialize system_prompt_parts with default if none provided
        if not system_prompt_parts:
            system_prompt_parts = DEFAULT_SYSTEM_PROMPT_PARTS
        
        if mock and mock_messages:
            messages_to_send = mock_messages
            system_content = "mock system message"
        else:
            # Build system message from parts
            kwargs = {"agent_name": AGENT_NAME}
            
            # Handle tool loop parts
            if tool_loop_data:
                system_prompt_parts = handle_tool_loop_parts(system_prompt_parts, tool_loop_data, kwargs)
            else:
                system_prompt_parts = remove_tool_loop_part(system_prompt_parts)
            
            messages, summary = chat_history.get_recent_messages()
            
            # Only include progressive summary if there's actually a summary
            if summary:
                kwargs["summary"] = summary
                system_prompt_parts.parts["progressive_summary"] = SystemPromptPartInfo(toggled=True, index=len(system_prompt_parts.parts))
            elif "progressive_summary" in system_prompt_parts.parts:
                del system_prompt_parts.parts["progressive_summary"]
            
            system_content = get_system_message(system_prompt_parts=system_prompt_parts, **kwargs)
            messages_to_send = messages

        prompt_text = f"SYSTEM: {system_content}\n\n{convert_messages_to_string(messages_to_send, truncate_last=False)}"
        logger.log(LogLevel.PROMPT, f"{prompt_text}")

        response = await enqueue_api_call(
            model=CHAT_AGENT_MODEL,
            messages=messages_to_send,
            system_message=system_content,
            tools=tools,
            temperature=0.7,
            mock=mock,
            system_prompt_parts=system_prompt_parts
        )

        # Update token usage if in a tool loop
        if tool_loop_data:
            tool_loop_data.loop_tokens += response.get('token_usage', {}).get('total_tokens', 0)
            log_token_budget_warnings(tool_loop_data.loop_tokens, token_budget, tool_loop_data.loop_type)
            if tool_loop_data.loop_tokens > token_budget:
                tool_loop_data.active = False
                if 'tool_call_results' in response:
                    tool_name = next(iter(response['tool_call_results'].values()))['tool_name']
                    logger.warning(f'Token budget reached - {tool_name} tool call aborted')
                    return 'Sorry, my token budget has been exceeded during a tool call.'
                logger.warning(f'Token budget reached - ending {tool_loop_data.loop_type} loop')

        if 'tool_call_results' in response:
            if not isinstance(response['tool_call_results'], dict):
                logger.error(f"Expected dict for tool_call_results, got {type(response['tool_call_results'])}")
                if DEBUG_ENABLED:
                    raise 
                return "Sorry, I encountered an error while processing your request."

            user_message = await process_tool_calls(
                tool_call_results=response['tool_call_results'],
                available_tools=tools,
                tool_loop_data=tool_loop_data,
                chat_history=chat_history,
                token_budget=token_budget,
                mock=mock,
                mock_messages=mock_messages,
                system_prompt_parts=system_prompt_parts
            )
            if user_message:
                if tool_loop_data:
                    prefix = f"[{tool_loop_data.loop_type}_LOOP] "
                    prefixed_message = user_message if user_message.startswith(prefix) else prefix + user_message
                else:
                    prefixed_message = user_message
                if not (tool_loop_data and not tool_loop_data.active):
                    chat_history.add_message("assistant", prefixed_message, name=AGENT_NAME)
                return user_message
            return ''

        if not response["content"]:
            logger.error("Received an empty message from the OpenAI API.")
            if DEBUG_ENABLED:
                raise
            return "Sorry, I encountered an error while processing your request."

        content = response["content"]
        # Remove any agent name prefix if present (both regular and uppercase)
        prefixes = [
            f"{AGENT_NAME}: ",
            f"{AGENT_NAME.upper()}: "
        ]
        for prefix in prefixes:
            if content.startswith(prefix):
                content = content[len(prefix):]
                break

        if tool_loop_data and tool_loop_data.loop_type:
            prefix = f"[{tool_loop_data.loop_type}_LOOP] "
            prefixed_content = content if content.startswith(prefix) else prefix + content
        else:
            prefixed_content = content

        if not (tool_loop_data and not tool_loop_data.active):
            chat_history.add_message("assistant", prefixed_content, name=AGENT_NAME)

        return content
    except Exception as e:
        logger.error(f"Error communicating with API: {e}")
        if DEBUG_ENABLED:
            raise
        return "Sorry, I encountered an error while processing your request."


async def process_tool_calls(
    tool_call_results: Dict[str, Dict[str, Any]],
    available_tools: Optional[Set[ToolName]],
    tool_loop_data: Optional[ToolLoopData],
    chat_history: ChatHistory,
    token_budget: int = 20000,
    mock: bool = False,
    mock_messages: Optional[List[ChatMessage]] = None,
    system_prompt_parts: Optional[SystemPromptPartsData] = None
) -> Optional[str]:
    """
    Process tool calls by matching them to corresponding functions.

    Args:
        tool_call_results: A dictionary of tool call results from the API response.
        available_tools: A set of ToolName enums representing the tools available to the agent.
        tool_loop_data: An optional ToolLoopData instance to manage the state within the tool loop.
        chat_history: The ChatHistory instance.
        token_budget: Maximum number of tokens allowed for the tool loop. Default is 20000.
        mock: If True, uses mock_messages instead of normal message setup.
        mock_messages: List of mock messages to use when mock=True.
        system_prompt_parts: Optional SystemPromptPartsData instance with prompt parts.

    Returns:
        Optional[str]: A message to be returned to the user, if available.
    """
    messages = []
    tool_map = get_tool_function_map()
    
    def get_common_args_for_function(function: Callable, **kwargs) -> Dict[str, Any]:
        """Get the common args that this function accepts."""
        # Check for any missing common args
        missing_args = COMMON_TOOL_ARGS - set(kwargs.keys())
        if missing_args:
            logger.warning(f"Missing common tool args in process_tool_calls: {missing_args}")

        return {
            k: v for k, v in kwargs.items()
            if k in COMMON_TOOL_ARGS and k in inspect.signature(function).parameters
        }

    for call_id, tool_call in tool_call_results.items():
        assert isinstance(call_id, str), f"Tool call ID must be string, got {type(call_id)}: {call_id}"
        tool_name = tool_call['tool_name']
        arguments = tool_call['arguments']

        args_to_pass, error = validate_tool_args(tool_name, arguments, available_tools)
        if error:
            logger.error(error)
            continue

        processing_function = tool_map[tool_name]

        try:
            common_args = get_common_args_for_function(
                processing_function,
                tool_loop_data=tool_loop_data,
                chat_history=chat_history,
                token_budget=token_budget,
                mock=mock,
                mock_messages=mock_messages,
                system_prompt_parts=system_prompt_parts
            )
            
            response = await processing_function(
                **args_to_pass,  # Schema-required args
                **common_args    # Only the common args this function wants
            )
            if response is not None:
                messages.append(response)
        except Exception as e:
            logger.error(f"Error processing tool '{tool_name}': {e}")
            if DEBUG_ENABLED:
                raise

    if messages:
        final_message = ' '.join(messages)
        return final_message
    else:
        return None


def validate_tool_args(
    tool_name: str,
    arguments: Dict[str, Any],
    available_tools: Optional[Set[ToolName]]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Validate tool arguments against their schema and availability.

    Args:
        tool_name: The name of the tool being called.
        arguments: The arguments provided for the tool.
        available_tools: Optional set of available tools.

    Returns:
        Tuple containing:
        - Dict of validated arguments if validation succeeds, None if it fails
        - Error message if validation fails, None if it succeeds
    """
    try:
        tool_enum = ToolName(tool_name)
    except ValueError:
        return None, f"Invalid tool name: {tool_name}"

    if available_tools and tool_enum not in available_tools:
        return None, f"Tool '{tool_name}' is not in the available tools list."

    tool_map = get_tool_function_map()
    processing_function = tool_map.get(tool_name)
    if not processing_function:
        return None, f"No processing function found for tool: {tool_name}"

    tool_schema = TOOL_SCHEMAS[tool_enum]["function"]["parameters"]
    required_params = tool_schema.get("required", [])
    properties = tool_schema.get("properties", {})

    missing_params = [param for param in required_params if param not in arguments]
    if missing_params:
        return None, f"Missing required parameters {missing_params} for tool '{tool_name}'"

    unrecognized_args = [arg for arg in arguments if arg not in properties]
    if unrecognized_args:
        return None, f"Unrecognized arguments {unrecognized_args} for tool '{tool_name}'"

    args_to_pass = {param: arguments[param] for param in required_params}
    return args_to_pass, None

def handle_tool_loop_parts(system_prompt_parts, tool_loop_data, kwargs):
    system_prompt_parts.parts["tool_loop"] = SystemPromptPartInfo(toggled=True, index=len(system_prompt_parts.parts))
    tool_loop_data.system_prompt_parts = system_prompt_parts
    kwargs["loop_message"] = tool_loop_data.loop_message
    return system_prompt_parts

def remove_tool_loop_part(system_prompt_parts):
    if "tool_loop" in system_prompt_parts.parts:
        del system_prompt_parts.parts["tool_loop"]
    return system_prompt_parts

def log_token_budget_warnings(loop_tokens: int, token_budget: int, loop_type: str) -> None:
    """
    Log warnings when token usage approaches the budget limit.
    
    Args:
        loop_tokens: Current number of tokens used in the loop
        token_budget: Maximum token budget for the loop
        loop_type: Type of the current loop (e.g., "CONTEMPLATION")
    """
    thresholds = [
        (0.95, "95%"),
        (0.90, "90%"),
        (0.75, "75%"),
        (0.50, "50%")
    ]
    
    # Find highest threshold reached
    for threshold, percent in sorted(thresholds, reverse=True):
        if loop_tokens > token_budget * threshold:
            logger.warning(
                f"{AGENT_NAME} in {loop_type} loop has used {percent} of token budget "
                f"({loop_tokens}/{token_budget} tokens)"
            )
            break


def register_tools():
    """
    Validate that each tool processing function:
    1. Has all required parameters from its tool schema
    2. Any additional parameters must be either:
       - Optional parameters from the tool schema
       - Parameters from COMMON_TOOL_ARGS
    
    Raises:
        ValueError: If any tool processing function has invalid parameters.
    """
    tool_map = get_tool_function_map()
    
    for tool_name, function in tool_map.items():
        try:
            tool_enum = ToolName(tool_name)
            schema = TOOL_SCHEMAS[tool_enum]["function"]["parameters"]
        except KeyError:
            raise ValueError(f"Schema for tool '{tool_name}' not found in TOOL_SCHEMAS.")

        sig = inspect.signature(function)
        func_params = set(sig.parameters.keys())
        schema_properties = schema.get("properties", {})
        all_schema_params = set(schema_properties.keys())  # Both required and optional params
        required_params = set(schema.get("required", []))

        # 1. Ensure function has all required parameters from schema
        for param in required_params:
            if param not in sig.parameters:
                raise ValueError(f"Function '{function.__name__}' missing required parameter '{param}' for tool '{tool_name}'.")

        # 2. Any parameter not in schema (required or optional) must be from COMMON_TOOL_ARGS
        extra_params = func_params - all_schema_params
        invalid_params = extra_params - COMMON_TOOL_ARGS
        if invalid_params:
            raise ValueError(
                f"Function '{function.__name__}' has parameters {invalid_params} that are neither "
                f"in its tool schema nor in COMMON_TOOL_ARGS."
            )

register_tools()
