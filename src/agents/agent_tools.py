from sympy import true
from shared_resources import logger, AGENT_NAME, get_shell
from constants import LogLevel, ToolName
from .chat_agent import get_response
from prompts import DEFAULT_SYSTEM_PROMPT_PARTS
from custom_dataclasses import ToolLoopData, ChatMessage
from .chat_history import ChatHistory
from typing import Optional, List, Any, Dict, Union, Set
from prompt_toolkit.formatted_text import ANSI

async def process_contemplate_loop(
    question: str,
    tool_loop_data: Optional[ToolLoopData],
    chat_history: ChatHistory,
    token_budget: int = 20000,
    mock: bool = False,
    mock_messages: Optional[List[ChatMessage]] = None,
    system_prompt_parts: Optional[Dict[str, Dict[str, Union[bool, int]]]] = None
) -> Optional[str]:
    """
    Process the 'contemplate_loop' tool call.

    Args:
        question: The question to ponder during the contemplation loop.
        tool_loop_data: An optional ToolLoopData instance to manage the state within the tool loop.
        chat_history: The ChatHistory instance.
        token_budget: Maximum number of tokens allowed for the tool loop. Default is 20000.
        mock: If True, uses mock_messages instead of normal message setup.
        mock_messages: List of mock messages to use when mock=True.
        system_prompt_parts: Optional dict of prompt parts with toggle and index info.

    Returns:
        Optional[str]: Message to the user, if any.
    """
    if tool_loop_data:
        logger.log(LogLevel.TOOL, f"{AGENT_NAME} used tool: contemplate_loop - no effect, agent already inside tool loop")
        return None

    # Start a new contemplation loop
    assert not tool_loop_data, f"Starting contemplate but loop already active: {tool_loop_data}"
    
    tool_loop_data = create_tool_loop_data(
        loop_type="CONTEMPLATION",
        loop_message=(
            f"You are inside a tool loop contemplating the following question:\n"
            f"{question}\n"
            "To record your thoughts during contemplation, use the message_self tool. "
            "These messages will be added to your chat history and automatically prefixed with [CONTEMPLATION_LOOP], "
            "but will not be shown to the user. This allows you to think through the problem step by step.\n"
            "When you have reached a conclusion, use the exit_loop tool with your final answer "
            "to end contemplation and respond to the user. Do not prefix your messages yourself.\n"
        ),
        system_prompt_parts=system_prompt_parts,
    )

    logger.log(LogLevel.TOOL, f"{AGENT_NAME} used tool: contemplate - now entering contemplation loop")
    max_iterations = 5  # Adjust as needed
    iterations = 0

    while iterations < max_iterations:
        iterations += 1
        response = await get_response(
            chat_history=chat_history,
            tools=tool_loop_data.available_tools,
            tool_loop_data=tool_loop_data,
            token_budget=token_budget,
            mock=mock,
            mock_messages=mock_messages,
            system_prompt_parts=tool_loop_data.system_prompt_parts
        )
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
    tool_loop_data: Optional[ToolLoopData]
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
    tool_loop_data: Optional[ToolLoopData]
) -> Optional[str]:
    """Process the message_self tool call."""
    if not tool_loop_data or not tool_loop_data.active:
        logger.warning(f"{AGENT_NAME} used tool: message_self - no effect, agent not inside tool loop")
        return None

    logger.log(LogLevel.TOOL, f"{AGENT_NAME} used tool: message_self - recording message")
    return message

async def process_toggle_prompt_part(
    part_name: str,
    system_prompt_parts: Optional[Dict[str, Dict[str, Union[bool, int]]]] = None
) -> str:
    """Process the toggle_prompt_part tool call."""
    if not system_prompt_parts:
        logger.error("No system prompt parts available")
        return ""
    
    if part_name not in system_prompt_parts:
        logger.error(f"Unknown prompt part '{part_name}'")
        return ""
    
    # Toggle the part
    part_info = system_prompt_parts[part_name]
    part_info["toggled"] = not part_info.get("toggled", True)
    
    # Get current state
    state = "on" if part_info["toggled"] else "off"
    logger.log(LogLevel.TOOL, f"{AGENT_NAME} used tool: toggle_prompt_part - Toggled prompt part '{part_name}' {state}")
    return f"I've turned {part_name} {state}."

async def process_execute_shell_command(
    command: str,
    args: List[str],
) -> str:
    """Process the execute_shell_command tool call."""
    logger.log(
        LogLevel.TOOL,
        f"{AGENT_NAME} used tool: execute_shell_command - {command}{' with args: ' + ', '.join(args) if args else ''}"
    )
    shell = get_shell()
    args_str = ' '.join(args) if args else ''
    success, should_exit = await shell.execute_command(command, args_str, name=AGENT_NAME)
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

async def process_introduce_self(
    tool_loop_data: Optional[ToolLoopData],
    chat_history: ChatHistory,
    token_budget: int = 2000,
    mock: bool = False,
    mock_messages: Optional[List[ChatMessage]] = None
) -> Optional[str]:
    """
    Process the introduce_self tool call.

    Args:
        tool_loop_data: An optional ToolLoopData instance to manage the state within the tool loop.
        chat_history: The ChatHistory instance to maintain conversation context.
        token_budget: Maximum number of tokens allowed. Default is 2000.
        mock: If True, uses mock_messages instead of normal message setup.
        mock_messages: List of mock messages to use when mock=True.

    Returns:
        Optional[str]: Message to the user, if any.
    """
    if tool_loop_data:
        logger.log(LogLevel.TOOL, f"{AGENT_NAME} used tool: introduce_self - no effect, agent already inside tool loop")
        return None

    # Create a new system prompt with just the biographical information
    introduction_prompt_parts = {
        "biographical": {"toggled": True, "index": 0},
        "response_guidelines": {"toggled": True, "index": 1}
    }

    # Get response with biographical prompt
    response = await get_response(
        chat_history=chat_history,
        token_budget=token_budget,
        mock=mock,
        mock_messages=mock_messages,
        system_prompt_parts=introduction_prompt_parts
    )

    return response

def create_tool_loop_data(
    loop_type: str,
    loop_message: str,
    system_prompt_parts: Optional[Dict[str, Dict[str, Union[bool, int]]]] = None,
    tools: Optional[Set[ToolName]] = None,
    new_system_prompt: bool = True
) -> ToolLoopData:
    """Create a ToolLoopData instance with required tools and settings.
    
    Args:
        loop_type: Type of the loop (e.g., "CONTEMPLATION")
        loop_message: Message describing the loop's purpose
        system_prompt_parts: Optional dict of prompt parts with toggle and index info
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
        # Create a deep copy of the provided parts or default parts
        from copy import deepcopy
        parts_to_copy = system_prompt_parts if system_prompt_parts is not None else DEFAULT_SYSTEM_PROMPT_PARTS
        final_prompt_parts = deepcopy(parts_to_copy)
    else:
        # Use the provided parts directly, falling back to default if none provided
        final_prompt_parts = system_prompt_parts if system_prompt_parts is not None else DEFAULT_SYSTEM_PROMPT_PARTS

    return ToolLoopData(
        loop_type=loop_type,
        loop_message=loop_message,
        system_prompt_parts=final_prompt_parts,
        available_tools=final_tools
    )
