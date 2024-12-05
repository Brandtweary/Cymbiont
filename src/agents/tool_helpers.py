import asyncio
from typing import Any, List, Optional, Set, Dict, Tuple, Union, Callable
from functools import lru_cache
import inspect
from prompt_helpers import DEFAULT_SYSTEM_PROMPT_PARTS
from shared_resources import logger
from constants import ToolName
from custom_dataclasses import ChatMessage, ToolLoopData, SystemPromptPartsData, SystemPromptPartInfo
from .tool_schemas import TOOL_SCHEMAS

# Common arguments that can be passed to any tool processing function
COMMON_TOOL_ARGS = {
    'chat_history',          
    'tool_loop_data',        
    'token_budget',          
    'mock',                  
    'mock_messages',        
    'system_prompt_parts',
    'chat_agent'
}

@lru_cache(maxsize=1)
def get_tool_function_map() -> Dict[str, Callable]:
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
    # Check if tool is available
    if available_tools is not None:
        try:
            tool_enum = ToolName(tool_name)
            if tool_enum not in available_tools:
                return None, f"Tool '{tool_name}' is not available in current context"
        except ValueError:
            return None, f"Unknown tool: '{tool_name}'"

    # Get tool schema
    try:
        tool_schema = TOOL_SCHEMAS[ToolName(tool_name)]
    except (KeyError, ValueError):
        return None, f"No schema found for tool: '{tool_name}'"

    # TODO: Implement schema validation
    # For now, just return the arguments as is
    return arguments, None

async def process_tool_calls(
    tool_call_results: Dict[str, Dict[str, Any]],
    available_tools: Optional[Set[ToolName]],
    tool_loop_data: Optional[ToolLoopData],
    chat_history: Any,  # ChatHistory type
    chat_agent: Any,  # ChatAgent type
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
        chat_agent: The ChatAgent instance.
        token_budget: Maximum number of tokens allowed for the tool loop.
        mock: If True, uses mock_messages instead of normal message setup.
        mock_messages: List of mock messages to use when mock=True.
        system_prompt_parts: Optional SystemPromptPartsData instance with prompt parts.

    Returns:
        Optional[str]: A message to be returned to the user, if available.
    """
    tool_map = get_tool_function_map()
    
    for tool_name, tool_data in tool_call_results.items():
        # Validate tool arguments
        validated_args, error = validate_tool_args(tool_name, tool_data.get("arguments", {}), available_tools)
        if error:
            logger.error(f"Tool validation error: {error}")
            continue
            
        if tool_name not in tool_map:
            logger.error(f"No processing function found for tool: {tool_name}")
            continue

        try:
            # Get common args for this function
            common_args = get_common_args_for_function(
                tool_map[tool_name],
                chat_history=chat_history,
                tool_loop_data=tool_loop_data,
                token_budget=token_budget,
                mock=mock,
                mock_messages=mock_messages,
                system_prompt_parts=system_prompt_parts,
                chat_agent=chat_agent
            )
            
            # Build kwargs by combining common args with validated args
            kwargs = common_args
            if validated_args is not None:
                kwargs.update(validated_args)
            
            # Call the tool processing function
            result = await tool_map[tool_name](**kwargs)
            if result:
                return result

        except Exception as e:
            logger.error(f"Error processing tool {tool_name}: {str(e)}")
            continue
    
    return None

def register_tools() -> None:
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
    
    for tool_name, func in tool_map.items():
        try:
            tool_enum = ToolName(tool_name)
            schema = TOOL_SCHEMAS[tool_enum]
        except (ValueError, KeyError):
            logger.warning(f"No schema found for tool: {tool_name}")
            continue
            
        # Get function parameters
        sig = inspect.signature(func)
        func_params = set(sig.parameters.keys())
        
        # Get required parameters from schema
        required_params = set()
        if "parameters" in schema.get("function", {}):
            schema_params = schema["function"]["parameters"]
            if "required" in schema_params:
                required_params = set(schema_params["required"])
        
        # Validate parameters
        missing_params = required_params - func_params
        if missing_params:
            raise ValueError(f"Tool function {tool_name} missing required parameters: {missing_params}")
            
        # Check that any additional parameters are either optional in schema or common args
        extra_params = func_params - required_params - COMMON_TOOL_ARGS
        if extra_params:
            logger.warning(f"Tool function {tool_name} has extra parameters: {extra_params}")

def handle_tool_loop_parts(system_prompt_parts: Optional[SystemPromptPartsData], 
                         tool_loop_data: ToolLoopData, 
                         kwargs: Dict[str, Any]) -> SystemPromptPartsData:
    """Add tool loop parts to system prompt."""
    if system_prompt_parts is None:
        system_prompt_parts = DEFAULT_SYSTEM_PROMPT_PARTS
    system_prompt_parts.parts["tool_loop"] = SystemPromptPartInfo(toggled=True, index=len(system_prompt_parts.parts))
    tool_loop_data.system_prompt_parts = system_prompt_parts
    kwargs["loop_type"] = tool_loop_data.loop_type
    return system_prompt_parts

def remove_tool_loop_part(system_prompt_parts: Optional[SystemPromptPartsData]) -> SystemPromptPartsData:
    """Remove tool loop part from system prompt."""
    if system_prompt_parts is None:
        system_prompt_parts = DEFAULT_SYSTEM_PROMPT_PARTS
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
    if loop_tokens >= token_budget:
        logger.warning(f"{loop_type} loop has reached token budget limit of {token_budget}")
    elif loop_tokens >= token_budget * 0.9:
        logger.warning(f"{loop_type} loop is approaching token budget limit of {token_budget}")
    elif loop_tokens >= token_budget * 0.75:
        logger.warning(f"{loop_type} loop has used 75% of token budget {token_budget}")

# Note: register_tools() should be called by the application at startup, not at module level