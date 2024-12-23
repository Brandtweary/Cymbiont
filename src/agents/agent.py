import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple, Literal, Union, Callable
from shared_resources import logger, AGENT_NAME, DEBUG_ENABLED, get_shell
from cymbiont_logger.logger_types import LogLevel
from llms.model_registry import registry
from llms.prompt_helpers import get_system_message, DEFAULT_SYSTEM_PROMPT_PARTS
from llms.llm_types import SystemPromptPartInfo, SystemPromptPartsData, ChatMessage, ToolName, ToolChoice, ContextPart, TemporaryContextValue
from utils import log_performance, convert_messages_to_string
from llms.api_queue import enqueue_api_call
from .chat_history import ChatHistory
from .tool_helpers import process_tool_calls
from .agent_types import ActivationMode
from .taskpad import Taskpad


class Agent:
    """Base agent class that provides core functionality for all agent types.
    
    Provides core message handling and tool usage capabilities.
    """
    
    def __init__(
        self,
        chat_history: ChatHistory,
        model: Optional[str] = None,
        agent_name: str = AGENT_NAME,
        default_system_prompt_parts: SystemPromptPartsData = DEFAULT_SYSTEM_PROMPT_PARTS,
        default_tool_choice: ToolChoice = ToolChoice.AUTO,  # should be auto, set to none temporarily
        default_temperature: float = 0.7,
        default_tools: Optional[Set[ToolName]] = None,
        activation_mode: ActivationMode = ActivationMode.CONTINUOUS
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
        
        self.chat_history = chat_history
        self.model = model or registry.chat_agent_model
        self.agent_name = agent_name
        self.activation_mode = activation_mode  # Active by default in continuous mode
        self.active = activation_mode == ActivationMode.CONTINUOUS  # Active by default in continuous mode

        self.default_system_prompt_parts = default_system_prompt_parts
        self.default_tool_choice = default_tool_choice
        self.default_temperature = default_temperature
        self.default_tools = default_tools or set()
        self.previous_tool_call = ""  # Stores the last tool call as "tool name with args"
        
        # Create mutable copies of defaults for runtime modification
        self.current_system_prompt_parts = SystemPromptPartsData(
            parts={name: SystemPromptPartInfo(**info.__dict__) 
                  for name, info in default_system_prompt_parts.parts.items()},
            kwargs=dict(default_system_prompt_parts.kwargs)
        )
        self.current_tools = set(self.default_tools)
        self.temporary_context: Dict[str, TemporaryContextValue] = {}  # Store temporarily active context parts
        self.taskpad = Taskpad()
        
    def update_temporary_context(self, new_context: List[ContextPart], expiration: int = 5) -> None:
        """Update temporary context and expiration counters.
        
        This method updates the temporary context with new context parts and manages
        their expiration. Each time this is called, existing counters are
        decremented and expired parts are removed.
        
        When a context part is added again while already active, its expiration is
        increased geometrically: (current + expiration) * 1.5. This ensures that
        frequently relevant context persists longer in the conversation.
        
        Args:
            new_context: New context parts to add
            expiration: Number of turns before a context part expires (default: 5)
        """
        # First untoggle any parts and tools from contexts that will be removed
        for name in list(self.temporary_context.keys()):
            context_value = self.temporary_context[name]
            context_value.expiration -= 1
            if context_value.expiration <= 0:
                # Untoggle any parts this context had temporarily toggled
                for part_name in context_value.temporary_parts:
                    if part_name in self.current_system_prompt_parts.parts:
                        self.current_system_prompt_parts.parts[part_name].toggled = False
                # Remove any tools this context had temporarily added
                for tool in context_value.temporary_tools:
                    if tool in self.current_tools:
                        self.current_tools.remove(tool)
                del self.temporary_context[name]
        
        # Add or update context parts
        for context in new_context:
            # Create new context value (either fresh or with updated expiration)
            if context.name in self.temporary_context:
                # For repeated context, increase expiration geometrically
                current_value = self.temporary_context[context.name]
                new_expiration = int((current_value.expiration + expiration) * 1.5)
            else:
                # For new context, use base expiration
                new_expiration = expiration
        
            # Create new context value with empty temporary sets
            context_value = TemporaryContextValue(
                context=context,
                expiration=new_expiration
            )
        
            # Always evaluate which parts should be toggled for this context
            for part_name in context.system_prompt_parts:
                if part_name in self.current_system_prompt_parts.parts:
                    part_info = self.current_system_prompt_parts.parts[part_name]
                    part_info.toggled = True
                    context_value.temporary_parts.add(part_name)
                
            # Always evaluate which tools should be added for this context
            for tool in context.tools:
                self.current_tools.add(tool)
                context_value.temporary_tools.add(tool)
        
            self.temporary_context[context.name] = context_value

    def setup_system_prompt_parts(
        self,
        system_prompt_parts: Optional[SystemPromptPartsData],
        summary: Optional[str] = None
    ) -> SystemPromptPartsData:
        """Helper method to set up system prompt parts with summary handling."""
        if not system_prompt_parts:
            system_prompt_parts = self.current_system_prompt_parts

        system_prompt_parts.kwargs["agent_name"] = self.agent_name
        
        # Add taskpad content if taskpad part is enabled
        if "taskpad" in system_prompt_parts.parts:
            system_prompt_parts.kwargs["taskpad"] = self.taskpad.format_taskpad()
        
        # Add activation mode prompt part
        activation_mode_part = "activation_mode_continuous" if self.activation_mode == ActivationMode.CONTINUOUS else "activation_mode_chat"
        if activation_mode_part not in system_prompt_parts.parts:
            system_prompt_parts.parts[activation_mode_part] = SystemPromptPartInfo(toggled=True, index=len(system_prompt_parts.parts))
        
        # Handle progressive summary if provided
        if summary and system_prompt_parts:
            system_prompt_parts.kwargs["summary"] = summary
            system_prompt_parts.parts["progressive_summary"] = SystemPromptPartInfo(toggled=True, index=len(system_prompt_parts.parts))
        elif system_prompt_parts and "progressive_summary" in system_prompt_parts.parts:
            del system_prompt_parts.parts["progressive_summary"]
        
        # Handle previous tool call if present
        if "previous_tool_call" in system_prompt_parts.parts:
            system_prompt_parts.kwargs["previous_tool_call"] = self.previous_tool_call
            system_prompt_parts.parts["previous_tool_call"].toggled = bool(self.previous_tool_call)
        
        return system_prompt_parts

    def clean_agent_prefix(self, message: str) -> str:
        """
        Removes accidental agent name prefixes from the message.
        Handles cases like "HECTOR: message" or "Hector>message".
        """
        if not message:  # Handle None or empty string
            return ""
            
        agent_name = self.agent_name.upper()
        # Check for patterns like "HECTOR: " or "Hector: "
        if message.upper().startswith(f"{agent_name}: "):
            message = message[len(agent_name) + 2:]
        # Check for patterns like "HECTOR>" or "Hector>"
        elif message.upper().startswith(f"{agent_name}>"):
            message = message[len(agent_name) + 1:]
        return message.strip()

    @log_performance
    async def get_response(
        self,
        tools: Optional[Set[ToolName]] = None,
        mock: bool = False,
        mock_messages: Optional[List[ChatMessage]] = None,
        system_prompt_parts: Optional[SystemPromptPartsData] = None,
        tool_choice: Optional[ToolChoice] = None,
        temperature: Optional[float] = None
    ) -> str:
        try:
            # Handle system prompt parts first, before any other logic
            if system_prompt_parts is None:
                system_prompt_parts = self.current_system_prompt_parts

            if mock and mock_messages:
                messages_to_send = mock_messages
                system_content = "mock system message"
            else:
                messages, summary = self.chat_history.get_recent_messages()
                # First set up basic prompt parts
                system_prompt_parts = self.setup_system_prompt_parts(
                    system_prompt_parts,
                    summary
                )
                system_content = get_system_message(system_prompt_parts=system_prompt_parts)
                messages_to_send = messages

            prompt_text = f"SYSTEM: {system_content}\n\n{convert_messages_to_string(messages_to_send, truncate_last=False)}"
            logger.log(LogLevel.PROMPT, f"{prompt_text}")

            # Convert tool choice enum to literal for backward compatibility
            current_tool_choice = (tool_choice or self.default_tool_choice).to_literal()

            # Use default tools if none provided
            current_tools = tools if tools is not None else self.current_tools

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

            # Get content from response - this should always be present
            content = response['content']  # Will raise KeyError if missing
            # Clean any accidental agent prefixes from the content
            content = self.clean_agent_prefix(content)
            
            # Only add non-empty content to chat history
            if content.strip():
                self.chat_history.add_message("assistant", content, name=self.agent_name)
                logger.log(LogLevel.CHAT_RESPONSE, f"{self.agent_name}> {content}")

            # Handle deactivation chat mode for text-only responses
            if self.activation_mode == ActivationMode.CHAT:
                if 'tool_call_results' not in response:
                    self.active = False

            # Process tool calls after text response if present
            if 'tool_call_results' in response:
                user_message = await process_tool_calls(
                    tool_call_results=response['tool_call_results'],
                    available_tools=tools,
                    agent=self,
                    system_prompt_parts=system_prompt_parts,
                    mock=mock,
                    mock_messages=mock_messages
                )
                
                if user_message:
                    # Clean any accidental agent prefixes
                    user_message = self.clean_agent_prefix(user_message)
                    # Add to chat history and log the response
                    self.chat_history.add_message("assistant", user_message, name=self.agent_name)
                    logger.log(LogLevel.CHAT_RESPONSE, f"{self.agent_name}> {user_message}")
                    # Return original message as per ChatAgent behavior
                    return user_message

            return content
        
        except Exception as e:
            logger.error(f"Error in get_response: {str(e)}")
            # Deactivate on errors in chat mode to prevent infinite error loops
            if self.activation_mode == ActivationMode.CHAT:
                self.active = False
            if DEBUG_ENABLED:
                raise
            return "I encountered an error while processing your request."
