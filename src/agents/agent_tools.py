from shared_resources import logger, AGENT_NAME, get_shell, DEBUG_ENABLED
from constants import LogLevel, ToolName, MAX_LOOP_ITERATIONS
from .chat_agent import ChatAgent
from .tool_agent import ToolAgent
from prompt_helpers import DEFAULT_SYSTEM_PROMPT_PARTS, create_system_prompt_parts_data
from custom_dataclasses import ToolLoopData, ChatMessage, SystemPromptPartsData, SystemPromptPartInfo
from .chat_history import ChatHistory
from typing import Optional, List, Set

async def process_contemplate_loop(
    question: str,
    tool_loop_data: Optional[ToolLoopData],
    chat_history: ChatHistory,
    token_budget: int = 20000,
    mock: bool = False,
    mock_messages: Optional[List[ChatMessage]] = None,
    system_prompt_parts: Optional[SystemPromptPartsData] = None
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
        logger.warning(f"{AGENT_NAME} used tool: contemplate_loop - no effect, agent already inside tool loop")
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
    max_iterations = MAX_LOOP_ITERATIONS  # Adjust as needed
    iterations = 0

    while iterations < max_iterations:
        iterations += 1
        chat_agent = ChatAgent(chat_history)
        response = await chat_agent.get_chat_response(
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
    system_prompt_parts: Optional[SystemPromptPartsData] = None
) -> str:
    """Process the toggle_prompt_part tool call."""
    if not system_prompt_parts:
        logger.error("No system prompt parts available")
        if DEBUG_ENABLED:
            raise
        return ""
    
    if part_name not in system_prompt_parts.parts:
        logger.error(f"Unknown prompt part '{part_name}'")
        if DEBUG_ENABLED:
            raise
        return ""
    
    # Toggle the part
    part_info = system_prompt_parts.parts[part_name]
    part_info.toggled = not part_info.toggled
    
    # Get current state
    state = "on" if part_info.toggled else "off"
    logger.log(LogLevel.TOOL, f"{AGENT_NAME} used tool: toggle_prompt_part - Toggled prompt part '{part_name}' {state}")
    return f"I've turned {part_name} {state}."

async def process_execute_shell_command(
    command: str,
    args: List[str],
    tool_loop_data: Optional[ToolLoopData] = None,
    chat_history: Optional[ChatHistory] = None,
    token_budget: int = 20000,
    mock: bool = False,
    mock_messages: Optional[List[ChatMessage]] = None,
    system_prompt_parts: Optional[SystemPromptPartsData] = None
) -> str:
    """Process the execute_shell_command tool call."""
    logger.log(
        LogLevel.TOOL,
        f"{AGENT_NAME} used tool: execute_shell_command - {command}{' with args: ' + ', '.join(args) if args else ''}"
    )
    shell = get_shell()
    args_str = ' '.join(args) if args else ''
    success, should_exit = await shell.execute_command(command, args_str, name=AGENT_NAME)
    if not success and not tool_loop_data and chat_history:
        # Command failed and we're not in a loop - start a shell loop
        logger.log(LogLevel.TOOL, f"Command failed, starting shell loop for troubleshooting")
        return await process_shell_loop(
            chat_history=chat_history,
            token_budget=token_budget,
            mock=mock,
            mock_messages=mock_messages,
            system_prompt_parts=system_prompt_parts
        ) or f"Failed to execute command: {command}{' ' + args_str if args_str else ''}"
    elif not success:
        # Command failed but we're either in a loop or missing chat_history
        return f"Failed to execute command: {command}{' ' + args_str if args_str else ''}"
    elif should_exit:
        return f"Command {command} requested shell exit"
    
    # Only return execution message if not in a tool loop
    if not tool_loop_data:
        # Format command and args in blue
        formatted_cmd = f"\033[38;2;0;128;254m{command}\033[0m"  # #0080FE in RGB
        formatted_args = ', '.join(f"\033[38;2;0;128;254m{arg}\033[0m" for arg in args) if args else ""
        if args:
            return f"I have executed the command: {formatted_cmd} with args {formatted_args}"
        else:
            return f"I have executed the command: {formatted_cmd}"
    
    return ''

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
    introduction_prompt_parts = create_system_prompt_parts_data(["biographical", "response_guidelines"])

    # Get response with biographical prompt
    chat_agent = ChatAgent(chat_history)
    response = await chat_agent.get_chat_response(
        token_budget=token_budget,
        mock=mock,
        mock_messages=mock_messages,
        system_prompt_parts=introduction_prompt_parts
    )

    return response

async def process_shell_loop(
    chat_history: ChatHistory,
    tool_loop_data: Optional[ToolLoopData] = None,
    token_budget: int = 20000,
    mock: bool = False,
    mock_messages: Optional[List[ChatMessage]] = None,
    system_prompt_parts: Optional[SystemPromptPartsData] = None
) -> Optional[str]:
    """
    Process the 'shell_loop' tool call.

    Args:
        chat_history: The ChatHistory instance.
        tool_loop_data: An optional ToolLoopData instance to manage the state within the tool loop.
        token_budget: Maximum number of tokens allowed for the tool loop. Default is 20000.
        mock: If True, uses mock_messages instead of normal message setup.
        mock_messages: List of mock messages to use when mock=True.
        system_prompt_parts: Optional dict of prompt parts with toggle and index info.

    Returns:
        Optional[str]: Message to the user, if any.
    """
    if tool_loop_data:
        logger.warning(f"{AGENT_NAME} used tool: shell_loop - no effect, agent already inside tool loop")
        return None

    # Start a new shell loop
    assert not tool_loop_data, f"Starting shell loop but loop already active: {tool_loop_data}"
    
    tool_loop_data = create_tool_loop_data(
        loop_type="SHELL",
        tools = {ToolName.EXECUTE_SHELL_COMMAND},
        loop_message=(
            "You are inside a shell loop where you can chain together shell commands. "
            "Use exit_loop when finished.\n"
        ),
        system_prompt_parts=system_prompt_parts,
        new_system_prompt=True  # Create a copy of system prompt parts
    )

    # Ensure system_prompt_parts is not None (should never happen due to create_tool_loop_data logic)
    assert tool_loop_data.system_prompt_parts is not None, "System prompt parts unexpectedly None after create_tool_loop_data"

    # Add shell_command_info part if it doesn't exist and ensure it's toggled on
    if 'shell_command_info' not in tool_loop_data.system_prompt_parts.parts:
        tool_loop_data.system_prompt_parts.parts['shell_command_info'] = SystemPromptPartInfo(toggled=True, index=len(tool_loop_data.system_prompt_parts.parts))
    else:
        tool_loop_data.system_prompt_parts.parts['shell_command_info'].toggled = True

    logger.log(LogLevel.TOOL, f"{AGENT_NAME} used tool: shell_loop - now entering shell loop")

    max_iterations = MAX_LOOP_ITERATIONS  # Adjust as needed
    iterations = 0

    while iterations < max_iterations:
        iterations += 1
        chat_agent = ChatAgent(chat_history)
        response = await chat_agent.get_chat_response(
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
        logger.warning("Max iterations reached in shell loop without exit.")
        return None

    return None

def create_tool_loop_data(
    loop_type: str,
    loop_message: str,
    system_prompt_parts: Optional[SystemPromptPartsData] = None,
    tools: Optional[Set[ToolName]] = None,
    new_system_prompt: bool = False
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
