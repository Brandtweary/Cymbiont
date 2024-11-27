from shared_resources import logger, AGENT_NAME
from constants import LogLevel, ToolName
from chat_agent import get_response
from custom_dataclasses import ToolLoopData
from chat_history import ChatHistory
from typing import Optional


async def process_contemplate(
    question: str,
    tool_loop_data: Optional[ToolLoopData],
    chat_history: ChatHistory,
    token_budget: int = 20000
) -> Optional[str]:
    """
    Process the 'contemplate' tool call.

    Args:
        question: The question to ponder during the contemplation loop.
        tool_loop_data: An optional ToolLoopData instance to manage the state within the tool loop.
        chat_history: The ChatHistory instance.
        token_budget: Maximum number of tokens allowed for the tool loop. Default is 20000.

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
            tool_loop_data=tool_loop_data,
            token_budget=token_budget
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
    tool_loop_data: Optional[ToolLoopData],
    chat_history: ChatHistory,
    token_budget: int = 20000
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
    chat_history: ChatHistory,
    token_budget: int = 20000
) -> str:
    """
    Process the 'message_self' tool call.

    Args:
        message: The message to send to self.
        tool_loop_data: An optional ToolLoopData instance to manage the state within the tool loop.
        chat_history: The ChatHistory instance.
        token_budget: Maximum number of tokens allowed for the tool loop. Default is 20000.

    Returns:
        str: The message that was sent to self.
    """
    logger.log(LogLevel.TOOL, f"{AGENT_NAME} used tool: message_self")
    return message