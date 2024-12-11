import asyncio
from typing import Any, List, Optional, Set, Dict, Tuple, Union, Callable
from functools import lru_cache
import inspect
from shared_resources import logger
from llms.llm_types import SystemPromptPartsData, ChatMessage, ToolName
from .tool_schemas import TOOL_SCHEMAS
from copy import deepcopy


# Common arguments that can be passed to any tool processing function
COMMON_TOOL_ARGS = {
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
                            process_message_self,
                            process_execute_shell_command,
                            process_toggle_prompt_part,
                            process_meditate,
                            process_toggle_tool,
                            process_add_task,
                            process_add_task_dependency
                            )
    import inspect
    from . import agent_tools

    tool_map = {
        ToolName.MESSAGE_SELF.value: process_message_self,
        ToolName.EXECUTE_SHELL_COMMAND.value: process_execute_shell_command,
        ToolName.TOGGLE_PROMPT_PART.value: process_toggle_prompt_part,
        ToolName.MEDITATE.value: process_meditate,
        ToolName.TOGGLE_TOOL.value: process_toggle_tool,
        ToolName.ADD_TASK.value: process_add_task,
        ToolName.ADD_TASK_DEPENDENCY.value: process_add_task_dependency
    }

    # Get all functions from agent_tools module
    all_functions = {name: obj for name, obj in inspect.getmembers(agent_tools, inspect.isfunction)}
    mapped_functions = set(tool_map.values())
    
    # Check for unmapped functions
    unmapped = [name for name, func in all_functions.items() 
                if func not in mapped_functions 
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

    # Get parameters schema
    params_schema = tool_schema["function"]["parameters"]
    
    # Validate required parameters
    required_params = params_schema.get("required", [])
    missing_params = [param for param in required_params if param not in arguments]
    if missing_params:
        return None, f"Missing required parameters: {', '.join(missing_params)}"

    # Validate no unrecognized arguments
    valid_params = params_schema["properties"].keys()
    invalid_params = [param for param in arguments if param not in valid_params]
    if invalid_params:
        return None, f"Unrecognized arguments: {', '.join(invalid_params)}"

    return arguments, None

async def process_tool_calls(
    tool_call_results: Dict[str, Dict[str, Any]],
    available_tools: Optional[Set[ToolName]],
    agent: Any,  # Avoiding circular import but should be an Agent instance
    system_prompt_parts: SystemPromptPartsData,
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
                mock=mock,
                mock_messages=mock_messages,
                system_prompt_parts=system_prompt_parts,
                agent=agent
            )
            
            # Build kwargs by combining common args with validated args
            kwargs = common_args
            if validated_args is not None:
                kwargs.update(validated_args)
            
            # Update agent's previous_tool_call attribute
            tool_args_str = ", ".join(f"{k}={v}" for k, v in validated_args.items()) if validated_args else ""
            agent.previous_tool_call = f"{tool_name}({tool_args_str})"
            
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
        
        # Get required and optional parameters from schema
        required_params = set()
        optional_params = set()
        if "parameters" in schema.get("function", {}):
            schema_params = schema["function"]["parameters"]
            if "required" in schema_params:
                required_params = set(schema_params["required"])
            if "properties" in schema_params:
                optional_params = set(schema_params["properties"].keys()) - required_params
        
        # Validate parameters
        missing_params = required_params - func_params
        if missing_params:
            raise ValueError(f"Tool function {tool_name} missing required parameters: {missing_params}")
            
        # Check that any additional parameters are either in schema or common args
        extra_params = func_params - required_params - optional_params - COMMON_TOOL_ARGS
        if extra_params:
            logger.warning(f"Tool function {tool_name} has extra parameters: {extra_params}")

def format_tool_schema(schema: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """Format a single tool schema, handling any dynamic content based on runtime state.
    
    Args:
        schema: The base schema to format
        **kwargs: Dynamic parameters for initial schema formatting:
            - system_prompt_parts: Required for toggle_prompt_part schema
            - command_metadata: Required for execute_shell_command schema
            - tools: Required for toggle_tool schema, contains currently enabled tools
    """
    schema = deepcopy(schema)
    schema_name = schema.get("function", {}).get("name")
    
    match schema_name:
        case "toggle_prompt_part":
            if "system_prompt_parts" not in kwargs:
                logger.warning("Missing 'system_prompt_parts' kwarg required for toggle_prompt_part schema. "
                             "This should be added to the format_all_tool_schemas call in CymbiontShell.__init__")
                return schema
                
            system_prompt_parts = kwargs["system_prompt_parts"]
            assert isinstance(system_prompt_parts, SystemPromptPartsData), "system_prompt_parts must be SystemPromptPartsData"
            
            # Mark toggled-on parts with an asterisk
            marked_parts = []
            for part_name, part_info in system_prompt_parts.parts.items():
                if part_info.toggled:
                    marked_parts.append(f"{part_name}*")
                else:
                    marked_parts.append(part_name)
                    
            schema["function"]["parameters"]["properties"]["part_name"]["enum"] = marked_parts
            
        case "execute_shell_command":  
            if "command_metadata" not in kwargs:
                logger.warning("Missing 'command_metadata' kwarg required for execute_shell_command schema. "
                             "This should be added to the format_all_tool_schemas call in CymbiontShell.__init__")
                return schema
                
            # Mark commands that take args with an asterisk
            marked_commands = []
            for cmd, cmd_data in kwargs["command_metadata"].items():
                if cmd_data.takes_args:
                    marked_commands.append(f"{cmd}*")
                else:
                    marked_commands.append(cmd)
                    
            schema["function"]["parameters"]["properties"]["command"]["enum"] = marked_commands
            
        case "toggle_tool":
            if "tools" not in kwargs:
                logger.warning("Missing 'tools' kwarg required for toggle_tool schema. "
                             "This should be added to the format_all_tool_schemas call in CymbiontShell.__init__")
                return schema
                
            tools = kwargs["tools"]
            # Create list of all tool names (except toggle_tool itself), marking enabled ones with asterisk
            marked_tools = []
            for tool_name in ToolName:
                if tool_name == ToolName.TOGGLE_TOOL:
                    continue
                if tool_name in tools:
                    marked_tools.append(f"{tool_name.value}*")
                else:
                    marked_tools.append(tool_name.value)
                    
            schema["function"]["parameters"]["properties"]["tool_name"]["enum"] = marked_tools
            
    return schema

def format_all_tool_schemas(**kwargs) -> None:
    """Format all tool schemas with dynamic content.
    
    Args:
        **kwargs: Dynamic parameters that may be required by different schemas:
            - system_prompt_parts: Required for toggle_prompt_part schema
            - command_metadata: Required for execute_shell_command schema
            - tools: Required for toggle_tool schema
    """
    # Format each schema
    for tool_name, schema in TOOL_SCHEMAS.items():
        TOOL_SCHEMAS[tool_name] = format_tool_schema(schema, **kwargs)
