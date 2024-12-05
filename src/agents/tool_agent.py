import asyncio
from typing import Any, List, Optional, Set, Dict
from api_queue import enqueue_api_call
from shared_resources import logger, AGENT_NAME, DEBUG_ENABLED
from constants import LogLevel, ToolName
from model_configuration import CHAT_AGENT_MODEL
from prompt_helpers import get_system_message, DEFAULT_SYSTEM_PROMPT_PARTS
from custom_dataclasses import ChatMessage, ToolLoopData, SystemPromptPartsData, SystemPromptPartInfo
from .tool_schemas import TOOL_SCHEMAS
from utils import log_performance, convert_messages_to_string
from .chat_history import ChatHistory
from .tool_helpers import process_tool_calls, handle_tool_loop_parts, remove_tool_loop_part, log_token_budget_warnings
from system_prompt_parts import DEFAULT_TOOL_AGENT_SYSTEM_PROMPT_PARTS

class ToolAgent:
    """An agent that focuses on making tool calls and may optionally generate messages."""

    def __init__(self, chat_history: ChatHistory):
        self.chat_history = chat_history

    @log_performance
    async def get_tool_response(
        self,
        tools: Optional[Set[ToolName]] = None,
        tool_loop_data: Optional[ToolLoopData] = None,
        token_budget: int = 20000,
        mock: bool = False,
        mock_messages: Optional[List[ChatMessage]] = None,
        system_prompt_parts: Optional[SystemPromptPartsData] = None
    ) -> Optional[str]:
        """
        Sends a message to the tool agent to analyze chat history and make proactive tool calls.
        Unlike the chat agent, this agent focuses on making tool calls and may optionally generate messages.

        Args:
            tools: A set of ToolName enums representing the tools available to the agent.
            tool_loop_data: An optional ToolLoopData instance to manage the state within a tool loop.
            token_budget: Maximum number of tokens allowed for the tool loop.
            mock: If True, uses mock_messages instead of normal message setup.
            mock_messages: List of mock messages to use when mock=True.
            system_prompt_parts: Optional SystemPromptPartsData instance with prompt parts.

        Returns:
            Optional[str]: The message to be returned, if any.
        """
        try:
            # Initialize system_prompt_parts with default if none provided
            if not system_prompt_parts:
                system_prompt_parts = DEFAULT_TOOL_AGENT_SYSTEM_PROMPT_PARTS
            
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
                temperature=0.0,
                mock=mock,
                system_prompt_parts=system_prompt_parts,
                tool_choice="required"
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

            # Process tool calls if present
            if 'tool_call_results' in response:
                if not isinstance(response['tool_call_results'], dict):
                    logger.error(f"Expected dict for tool_call_results, got {type(response['tool_call_results'])}")
                    if DEBUG_ENABLED:
                        raise 
                    return "Sorry, I encountered an error while processing your request."

                return await process_tool_calls(
                    tool_call_results=response['tool_call_results'],
                    available_tools=tools,
                    tool_loop_data=tool_loop_data,
                    chat_history=self.chat_history,
                    chat_agent=self,  # Pass self since we need an agent instance
                    token_budget=token_budget,
                    mock=mock,
                    mock_messages=mock_messages,
                    system_prompt_parts=system_prompt_parts
                )

            return response.get('content', '')

        except Exception as e:
            logger.error(f"Error in get_tool_response: {str(e)}")
            if DEBUG_ENABLED:
                raise
            return None
