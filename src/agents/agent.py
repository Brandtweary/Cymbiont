import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple, Literal, Union, Callable
from shared_resources import logger, AGENT_NAME, DEBUG_ENABLED
from cymbiont_logger.logger_types import LogLevel
from llms.model_configuration import CHAT_AGENT_MODEL
from llms.prompt_helpers import get_system_message, DEFAULT_SYSTEM_PROMPT_PARTS
from llms.llm_types import SystemPromptPartInfo, SystemPromptPartsData, ChatMessage, ToolName, ToolChoice, ToolLoopData
from utils import log_performance, convert_messages_to_string
from llms.api_queue import enqueue_api_call
from .chat_history import ChatHistory
from .tool_helpers import process_tool_calls


class Agent:
    """Base agent class that provides core functionality for all agent types.
    
    Provides core message handling and tool usage capabilities.
    """
    
    def __init__(
        self,
        chat_history: ChatHistory,
        model: str = CHAT_AGENT_MODEL,
        agent_name: str = AGENT_NAME,
        default_system_prompt_parts: SystemPromptPartsData = DEFAULT_SYSTEM_PROMPT_PARTS,
        default_tool_choice: ToolChoice = ToolChoice.AUTO,
        default_temperature: float = 0.7,
        default_tools: Optional[Set[ToolName]] = None,
    ):
        """Initialize the agent with chat history and model configuration.

        Args:
            chat_history: ChatHistory instance to use
            model: Name of the model to use
            agent_name: Name of the agent for chat history
            default_system_prompt_parts: Default system prompt parts to use
            default_tool_choice: Default tool choice setting for API calls
            default_temperature: Default temperature for API calls
            default_tools: Default set of tools available to this agent
        """
        # Import here to avoid circular imports
        from .chat_agent import ChatAgent
        from .tool_agent import ToolAgent
        
        self.chat_history = chat_history
        self.model = model
        self.agent_name = agent_name
        self.default_system_prompt_parts = default_system_prompt_parts
        self.default_tool_choice = default_tool_choice
        self.default_temperature = default_temperature
        self.default_tools = default_tools or set()
        self.active = False  # Base activation state
        self.activation_mode = "as_needed"  # Default to as_needed mode
        self.bound_tool_agent: Optional[ToolAgent] = None  # Reference to bound tool agent, if this is a chat agent
        self.bound_chat_agent: Optional[ChatAgent] = None  # Reference to bound chat agent, if this is a tool agent

    @staticmethod
    def bind_agents(chat_agent: Any, tool_agent: Any) -> None:
        """Bind a chat agent and tool agent together.
        
        This creates a bidirectional reference between the agents, allowing them
        to coordinate on operations.
        
        Args:
            chat_agent: The chat agent to bind
            tool_agent: The tool agent to bind
            
        Raises:
            TypeError: If either agent is not of the correct type
        """
        # Import here to avoid circular imports
        from .chat_agent import ChatAgent
        from .tool_agent import ToolAgent
        
        if not isinstance(chat_agent, ChatAgent):
            raise TypeError("chat_agent must be an instance of ChatAgent")
        if not isinstance(tool_agent, ToolAgent):
            raise TypeError("tool_agent must be an instance of ToolAgent")
            
        chat_agent.bound_tool_agent = tool_agent
        tool_agent.bound_chat_agent = chat_agent
        tool_agent.agent_name = chat_agent.agent_name

    def setup_unique_prompt_parts(
        self,
        system_prompt_parts: SystemPromptPartsData
    ) -> SystemPromptPartsData:
        """Add unique prompt parts for this agent type."""
        # Base agent has no unique parts to add
        return system_prompt_parts

    def setup_system_prompt_parts(
        self,
        system_prompt_parts: Optional[SystemPromptPartsData],
        tool_loop_data: Optional[ToolLoopData] = None,
        summary: Optional[str] = None
    ) -> SystemPromptPartsData:
        """Helper method to set up system prompt parts with tool loop and summary handling."""
        if not system_prompt_parts:
            system_prompt_parts = self.default_system_prompt_parts
        
        system_prompt_parts.kwargs["agent_name"] = self.agent_name
        
        # Handle tool loop parts
        if tool_loop_data:
            system_prompt_parts.kwargs.update({
                "loop_type": tool_loop_data.loop_type,
                "loop_message": tool_loop_data.loop_message
            })
            if "tool_loop" not in system_prompt_parts.parts:
                system_prompt_parts.parts["tool_loop"] = SystemPromptPartInfo(toggled=True, index=len(system_prompt_parts.parts))
        elif "tool_loop" in system_prompt_parts.parts:
            del system_prompt_parts.parts["tool_loop"]
        
        # Handle progressive summary if provided
        if summary and system_prompt_parts:
            system_prompt_parts.kwargs["summary"] = summary
            system_prompt_parts.parts["progressive_summary"] = SystemPromptPartInfo(toggled=True, index=len(system_prompt_parts.parts))
        elif system_prompt_parts and "progressive_summary" in system_prompt_parts.parts:
            del system_prompt_parts.parts["progressive_summary"]
            
        # Let subclasses add their unique prompt parts
        return self.setup_unique_prompt_parts(system_prompt_parts)

    def handle_token_usage(
        self,
        response: Dict[str, Any],
        tool_loop_data: Optional[ToolLoopData],
        token_budget: int
    ) -> Optional[str]:
        """Helper method to handle token usage and budget."""
        if not tool_loop_data:
            return None
            
        tool_loop_data.loop_tokens += response.get('token_usage', {}).get('total_tokens', 0)
        self.log_token_budget_warnings(tool_loop_data.loop_tokens, token_budget, tool_loop_data.loop_type)
        
        if tool_loop_data.loop_tokens > token_budget:
            tool_loop_data.active = False
            if 'tool_call_results' in response:
                tool_name = next(iter(response['tool_call_results'].values()))['tool_name']
                logger.warning(f'Token budget reached - {tool_name} tool call aborted')
                return 'Sorry, my token budget has been exceeded during a tool call.'
            logger.warning(f'Token budget reached - ending {tool_loop_data.loop_type} loop')
            return None

    def prefix_message(self, message: str, tool_loop_data: Optional[ToolLoopData]) -> str:
        """Helper method to prefix messages with loop type if needed."""
        if tool_loop_data:
            prefix = f"[{tool_loop_data.loop_type}_LOOP] "
            return message if message.startswith(prefix) else prefix + message
        return message

    def log_token_budget_warnings(self, loop_tokens: int, token_budget: int, loop_type: str) -> None:
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
                    f"{self.agent_name} in {loop_type} loop has used {percent} of token budget "
                    f"({loop_tokens}/{token_budget} tokens)"
                )
                break

    @log_performance
    async def get_response(
        self,
        tools: Optional[Set[ToolName]] = None,
        tool_loop_data: Optional[ToolLoopData] = None,
        token_budget: int = 20000,
        mock: bool = False,
        mock_messages: Optional[List[ChatMessage]] = None,
        system_prompt_parts: Optional[SystemPromptPartsData] = None,
        tool_choice: Optional[ToolChoice] = None,
        temperature: Optional[float] = None
    ) -> str:
        """
        Sends a message to the OpenAI chat agent with conversation history.

        Args:
            tools: A set of ToolName enums representing the tools available to the agent.
                  If None, uses default_tools.
            tool_loop_data: An optional ToolLoopData instance to manage the state within the tool loop.
            token_budget: Maximum number of tokens allowed for the tool loop. Default is 20000.
            mock: If True, uses mock_messages instead of normal message setup.
            mock_messages: List of mock messages to use when mock=True.
            system_prompt_parts: Optional SystemPromptPartsData instance with prompt parts.
                           If not provided, will use default_system_prompt_parts.
            tool_choice: Tool choice setting for API calls. If None, uses default_tool_choice.
            temperature: Temperature for API calls. If None, uses default_temperature.

        Returns:
            str: The assistant's response.
        """
        try:
            # Handle system prompt parts first, before any other logic
            if system_prompt_parts is None:
                system_prompt_parts = self.default_system_prompt_parts

            if mock and mock_messages:
                messages_to_send = mock_messages
                system_content = "mock system message"
            else:
                messages, summary = self.chat_history.get_recent_messages()
                system_prompt_parts = self.setup_system_prompt_parts(
                    system_prompt_parts,
                    tool_loop_data,
                    summary
                )
                system_content = get_system_message(system_prompt_parts=system_prompt_parts)
                messages_to_send = messages

            prompt_text = f"SYSTEM: {system_content}\n\n{convert_messages_to_string(messages_to_send, truncate_last=False)}"
            logger.log(LogLevel.PROMPT, f"{prompt_text}")

            # Convert tool choice enum to literal for backward compatibility
            current_tool_choice = (tool_choice or self.default_tool_choice).to_literal()

            # Use default tools if none provided
            current_tools = tools if tools is not None else self.default_tools

            response = await enqueue_api_call(
                model=self.model,
                messages=messages_to_send,
                system_message=system_content,
                tools=current_tools,
                temperature=temperature if temperature is not None else self.default_temperature,
                mock=mock,
                system_prompt_parts=system_prompt_parts,
                tool_choice=current_tool_choice
            )

            # Handle token usage and check budget
            error_message = self.handle_token_usage(response, tool_loop_data, token_budget)
            if error_message:
                return error_message

            if 'tool_call_results' in response:
                user_message = await process_tool_calls(
                    tool_call_results=response['tool_call_results'],
                    available_tools=tools,
                    agent=self,
                    system_prompt_parts=system_prompt_parts,
                    tool_loop_data=tool_loop_data,
                    token_budget=token_budget,
                    mock=mock,
                    mock_messages=mock_messages
                )
                
                if user_message:
                    # Get prefixed version for chat history
                    prefixed_message = self.prefix_message(user_message, tool_loop_data)
                    if not (tool_loop_data and not tool_loop_data.active):
                        self.chat_history.add_message("assistant", prefixed_message, name=self.agent_name)
                    # Return original message as per ChatAgent behavior
                    return user_message

            # Get content from response - this should always be present
            content = response['content']  # Will raise KeyError if missing
            # Add prefixed version to chat history but return original
            prefixed_message = self.prefix_message(content, tool_loop_data)
            if not (tool_loop_data and not tool_loop_data.active):
                self.chat_history.add_message("assistant", prefixed_message, name=self.agent_name)
            return content
            
        except Exception as e:
            logger.error(f"Error in get_response: {str(e)}")
            if DEBUG_ENABLED:
                raise
            return "I encountered an error while processing your request."