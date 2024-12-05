import asyncio
from typing import Any, List, Optional, Set, Dict, Tuple, Union, Callable
from functools import lru_cache
import inspect
from shared_resources import logger
from constants import ToolName
from custom_dataclasses import ChatMessage, ToolLoopData, SystemPromptPartsData, SystemPromptPartInfo
from .tool_schemas import TOOL_SCHEMAS

# Common arguments that can be passed to any tool processing function
COMMON_TOOL_ARGS = {
    'tool_loop_data',        
    'token_budget',          
    'mock',                  
    'mock_messages',        
    'system_prompt_parts',
    'agent'
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

    # Validate required parameters
    required_params = tool_schema["function"]["parameters"].get("required", [])
    missing_params = [param for param in required_params if param not in arguments]
    if missing_params:
        return None, f"Missing required parameters: {', '.join(missing_params)}"

    # Validate no unrecognized arguments
    valid_params = tool_schema["function"]["parameters"]["properties"].keys()
    invalid_params = [param for param in arguments if param not in valid_params]
    if invalid_params:
        return None, f"Unrecognized arguments: {', '.join(invalid_params)}"

    return arguments, None

async def process_tool_calls(
    tool_call_results: Dict[str, Dict[str, Any]],
    available_tools: Optional[Set[ToolName]],
    agent: Any,  # Avoiding circular import but should be an Agent instance
    system_prompt_parts: SystemPromptPartsData,
    tool_loop_data: Optional[ToolLoopData] = None,
    token_budget: int = 20000,
    mock: bool = False,
    mock_messages: Optional[List[ChatMessage]] = None
) -> Optional[str]:
    """
    Process tool calls by matching them to corresponding functions.

    Args:
        tool_call_results: A dictionary of tool call results from the API response.
        available_tools: A set of ToolName enums representing the tools available to the agent.
        agent: The Agent instance.
        system_prompt_parts: SystemPromptPartsData instance with prompt parts.
        tool_loop_data: An optional ToolLoopData instance to manage the state within the tool loop.
        token_budget: Maximum number of tokens allowed for the tool loop.
        mock: If True, uses mock_messages instead of normal message setup.
        mock_messages: List of mock messages to use when mock=True.

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
                tool_loop_data=tool_loop_data,
                token_budget=token_budget,
                mock=mock,
                mock_messages=mock_messages,
                system_prompt_parts=system_prompt_parts,
                agent=agent
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

def create_tool_loop_data(
    loop_type: str,
    loop_message: str,
    system_prompt_parts: SystemPromptPartsData,
    tools: Optional[Set[ToolName]] = None,
    new_system_prompt: bool = False
) -> ToolLoopData:
    """Create a ToolLoopData instance with required tools and settings.
    
    Args:
        loop_type: Type of the loop (e.g., "CONTEMPLATION")
        loop_message: Message describing the loop's purpose
        system_prompt_parts: The system prompt parts to use
        tools: Optional set of additional tools to include
        new_system_prompt: If True, creates a copy of system prompt parts. If False, uses the provided parts directly.
    """
    # Always include these tools in any loop
    required_tools = {
        ToolName.EXIT_LOOP,
        ToolName.MESSAGE_SELF,
        ToolName.TOGGLE_PROMPT_PART
    }

    # Combine with provided tools if any
    final_tools = required_tools | (tools or set())

    # Handle system prompt parts
    if new_system_prompt:
        # Create a deep copy of the provided parts
        from copy import deepcopy
        final_prompt_parts = deepcopy(system_prompt_parts)
    else:
        # Use the provided parts directly
        final_prompt_parts = system_prompt_parts

    return ToolLoopData(
        loop_type=loop_type,
        loop_message=loop_message,
        system_prompt_parts=final_prompt_parts,
        available_tools=final_tools
    )