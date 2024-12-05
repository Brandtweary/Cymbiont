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
from prompt_helpers import DEFAULT_SYSTEM_PROMPT_PARTS
from .tool_helpers import (
    process_tool_calls,
    register_tools,
    COMMON_TOOL_ARGS
)

class ChatAgent:
    """
    An agent that responds to user messages and can use tools.
    Unlike ToolAgent, this agent generates chat messages and uses tools only when needed.
    """
    
    def __init__(self, chat_history: ChatHistory):
        self.chat_history = chat_history
        register_tools()  # Register tools during initialization
    
    @log_performance
    async def get_chat_response(
        self,
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
                    system_prompt_parts = self.handle_tool_loop_parts(system_prompt_parts, tool_loop_data, kwargs)
                else:
                    system_prompt_parts = self.remove_tool_loop_part(system_prompt_parts)
                
                messages, summary = self.chat_history.get_recent_messages()
                
                # Only include progressive summary if there's actually a summary
                if summary and system_prompt_parts:
                    kwargs["summary"] = summary
                    system_prompt_parts.parts["progressive_summary"] = SystemPromptPartInfo(toggled=True, index=len(system_prompt_parts.parts))
                elif system_prompt_parts and "progressive_summary" in system_prompt_parts.parts:
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
                self.log_token_budget_warnings(tool_loop_data.loop_tokens, token_budget, tool_loop_data.loop_type)
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
                    chat_history=self.chat_history,
                    chat_agent=self,
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
                        self.chat_history.add_message("assistant", prefixed_message, name=AGENT_NAME)
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
                self.chat_history.add_message("assistant", prefixed_content, name=AGENT_NAME)

            return content
        except Exception as e:
            logger.error(f"Error communicating with API: {e}")
            if DEBUG_ENABLED:
                raise
            return "Sorry, I encountered an error while processing your request."


    @staticmethod
    def handle_tool_loop_parts(system_prompt_parts, tool_loop_data, kwargs):
        system_prompt_parts.parts["tool_loop"] = SystemPromptPartInfo(toggled=True, index=len(system_prompt_parts.parts))
        tool_loop_data.system_prompt_parts = system_prompt_parts
        kwargs["loop_message"] = tool_loop_data.loop_message
        return system_prompt_parts

    @staticmethod
    def remove_tool_loop_part(system_prompt_parts):
        if "tool_loop" in system_prompt_parts.parts:
            del system_prompt_parts.parts["tool_loop"]
        return system_prompt_parts

    @staticmethod
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
