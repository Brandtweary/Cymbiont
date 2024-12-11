from shared_resources import logger, get_shell, DEBUG_ENABLED
from cymbiont_logger.logger_types import LogLevel
from .agent import Agent
from llms.llm_types import SystemPromptPartsData, ToolName
from typing import Optional, List, Dict, Any, Union
import asyncio
from .agent_types import TaskStatus
from enum import Enum

async def process_message_self(
    message: str,
    agent: Agent
) -> Optional[str]:
    """
    Process the message_self tool call.
    
    Args:
        message: The message to record
        agent: The Agent instance
    """
    logger.log(LogLevel.TOOL, f"{agent.agent_name} recorded personal message: {message}")
    get_shell().keyword_router.toggle_context(message, agent) # permits agent to potentially toggle their own context organically
    return ''

async def process_toggle_prompt_part(
    part_name: str,
    agent: Agent,
    system_prompt_parts: Optional[SystemPromptPartsData] = None
) -> str:
    """Process the toggle_prompt_part tool call."""
    # Strip any trailing asterisks from part name
    clean_part_name = part_name.rstrip('*')
    
    # Check if part exists in agent's current system prompt parts
    if clean_part_name not in agent.current_system_prompt_parts.parts:
        logger.error(f"Unknown prompt part '{clean_part_name}'")
        if DEBUG_ENABLED:
            raise
        return ""
    
    # Log warning if part doesn't exist in temporary system prompt parts
    if system_prompt_parts and clean_part_name not in system_prompt_parts.parts:
        logger.warning(f"Prompt part '{clean_part_name}' not found in temporary system prompt parts")
    
    # Toggle the part in agent's current system prompt parts
    part_info = agent.current_system_prompt_parts.parts[clean_part_name]
    part_info.toggled = not part_info.toggled
    
    # Remove this part from any temporary contexts since it's being explicitly controlled
    for context_value in list(agent.temporary_context.values()):
        if clean_part_name in context_value.temporary_parts:
            context_value.temporary_parts.remove(clean_part_name)
    
    # Get current state
    state = "on" if part_info.toggled else "off"
    logger.log(LogLevel.TOOL, f"{agent.agent_name} used tool: toggle_prompt_part - Toggled prompt part '{clean_part_name}' {state}")
    return f"I've turned {clean_part_name} {state}."


async def process_execute_shell_command(
    command: str,
    agent: Agent,
    args: Optional[List[str]] = None
):
    """Process the execute_shell_command tool call."""
    if args is None:
        args = []
    logger.log(
        LogLevel.TOOL,
        f"{agent.agent_name} used tool: execute_shell_command - {command}{' with args: ' + ', '.join(args) if args else ''}"
    )
    shell = get_shell()
    args_str = ' '.join(args) if args else ''
    success, should_exit = await shell.execute_command(command, args_str, name=agent.agent_name)
    if not success:
        return f"Failed to execute command: {command}{' ' + args_str if args_str else ''}"
    elif should_exit:
        return f"Command {command} requested shell exit"
    
    # Format command and args in blue
    formatted_cmd = f"\033[38;2;0;128;254m{command}\033[0m"  # #0080FE in RGB
    formatted_args = ', '.join(f"\033[38;2;0;128;254m{arg}\033[0m" for arg in args) if args else ""
    if args:
        return f"I have executed the command: {formatted_cmd} with args {formatted_args}"
    else:
        return f"I have executed the command: {formatted_cmd}"
    
async def process_toggle_tool(
    tool_name: str,
    agent: Agent,
) -> str:
    """Process the toggle_tool tool call.
    
    Args:
        tool_name: Name of the tool to toggle (may include trailing asterisk)
        agent: Agent instance to toggle the tool for
        
    Returns:
        Response message indicating what was done
    """
    # Strip any trailing asterisks from tool name
    clean_tool_name = tool_name.rstrip('*')
    
    try:
        # Convert string to ToolName enum
        tool_enum = ToolName(clean_tool_name)
    except ValueError:
        logger.error(f"Unknown tool '{clean_tool_name}'")
        if DEBUG_ENABLED:
            raise
        return ""
    
    # Don't allow toggling toggle_tool itself
    if tool_enum == ToolName.TOGGLE_TOOL:
        return "The toggle_tool cannot be toggled."
    
    # Toggle the tool in agent's current tools
    if tool_enum in agent.current_tools:
        agent.current_tools.remove(tool_enum)
    else:
        agent.current_tools.add(tool_enum)
    
    # Remove this tool from temporary management in any contexts
    for context_value in list(agent.temporary_context.values()):
        if tool_enum in context_value.temporary_tools:
            context_value.temporary_tools.remove(tool_enum)
    
    # Get current state
    state = "on" if tool_enum in agent.current_tools else "off"
    logger.log(LogLevel.TOOL, f"{agent.agent_name} used tool: toggle_tool - Toggled tool '{clean_tool_name}' {state}")
    return f"I've turned {clean_tool_name} {state}."

async def process_meditate(agent: Agent, wait_time: int = 0) -> None:
    """Process the meditate tool call.
    
    In continuous mode, sets the agent to inactive for the specified wait time.
    If wait_time is 0 in continuous mode, the agent remains active (dummy tool call).
    In chat mode, simply sets active to false (wait time is ignored).
    
    Args:
        agent: The agent instance to meditate
        wait_time: Time in seconds to wait before reactivating (only used in continuous mode)
    """
    logger.log(LogLevel.TOOL, f"{agent.agent_name} used tool: meditate")
    
    if agent.activation_mode == "continuous":
        if wait_time > 0:
            agent.active = False
            await asyncio.sleep(wait_time)
            agent.active = True
        # If wait_time is 0, do nothing (remain active)
    else:  # chat mode
        agent.active = False

async def process_add_task(
    agent: Agent,
    description: str,
    parent_task_index: Optional[str] = None,
    insertion_index: Optional[Union[str, int]] = None,
    metadata_tags: Optional[List[str]] = None,
    status: Optional[str] = None
) -> None:
    """Process the add_task tool call."""
    # Convert status string to TaskStatus enum if provided
    task_status = TaskStatus(status) if status else TaskStatus.READY
    logger.log(
        LogLevel.TOOL,
        f"{agent.agent_name} used tool: add_task - {description}"
    )
    
    # Add the task
    agent.taskpad.add_task(
        description=description,
        parent_task_index=parent_task_index,
        insertion_index=insertion_index,
        metadata_tags=metadata_tags,
        status=task_status
    )

async def process_add_task_dependency(
    agent: Agent,
    blocked_task_index: str,
    blocking_task_index: str,
    insertion_index: Optional[int] = None
) -> None:
    """Process the add_task_dependency tool call.
    
    Args:
        agent: The agent instance
        blocked_task_index: Index of the task that is blocked (A-Z)
        blocking_task_index: Index of the task that is blocking (A-Z)
        insertion_index: Optional 1-based index for where to insert in subtask list
    """
    logger.log(
        LogLevel.TOOL,
        f"{agent.agent_name} used tool: add_task_dependency - Task {blocked_task_index} is blocked by task {blocking_task_index}"
    )
    
    # Add the dependency
    agent.taskpad.add_task_dependency(
        blocked_task_index=blocked_task_index,
        blocking_task_index=blocking_task_index,
        insertion_index=insertion_index
    )
