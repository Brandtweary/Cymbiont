from typing import Optional, Set, List, Literal, Any, Dict, Tuple
from shared_resources import logger, AGENT_NAME, DEBUG_ENABLED
from custom_dataclasses import SystemPromptPartsData, SystemPromptPartInfo
from model_configuration import CHAT_AGENT_MODEL 
from constants import ToolChoice, ToolName
from .agent import Agent
from .chat_history import ChatHistory
from agents import agent


class ToolAgent(Agent):
    """Agent focused on making tool calls and optionally generating messages."""

    def __init__(self, chat_history: ChatHistory, agent_name: str = AGENT_NAME, activation_mode: str = "continuous"):
        super().__init__(
            chat_history=chat_history,
            model=CHAT_AGENT_MODEL,
            agent_name=agent_name,
            default_system_prompt_parts=SystemPromptPartsData(
                parts={
                    "tool_agent_base_prompt": SystemPromptPartInfo(toggled=True, index=0),
                    "cymbiont_agent_overview": SystemPromptPartInfo(toggled=False, index=1),
                    "shell_command_info": SystemPromptPartInfo(toggled=True, index=2),
                }
            ),
            default_tool_choice=ToolChoice.REQUIRED,
            default_temperature=0.0,
            default_tools={
                ToolName.CONTEMPLATE_LOOP,
                ToolName.EXECUTE_SHELL_COMMAND,
                ToolName.SHELL_LOOP,
                ToolName.TOGGLE_PROMPT_PART,
                ToolName.RESOLVE_PENDING_OPERATION
            }
        )
        self.activation_mode = activation_mode
        self.active = activation_mode == "continuous"  # Active by default in continuous mode
        self.pending_operations: List[str] = []  # List of pending operations
        
    def setup_unique_prompt_parts(
        self,
        system_prompt_parts: SystemPromptPartsData
    ) -> SystemPromptPartsData:
        """Add pending operations to prompt parts if any exist."""
        if self.pending_operations:
            system_prompt_parts.parts["pending_operations"] = SystemPromptPartInfo(
                toggled=True,
                index=len(system_prompt_parts.parts)
            )
            # Add letter labels A, B, C, etc.
            labeled_requests = [f"{chr(65 + i)}) {req}" for i, req in enumerate(self.pending_operations)]
            system_prompt_parts.kwargs["pending_operations"] = "\n".join(labeled_requests)
        return system_prompt_parts
            
    def activate_for_operation(self, category: Optional[str] = None) -> None:
        """Activate the agent for a tool operation.
        
        Args:
            category: Optional category of the tool to use
        """
        self.active = True
        operation_description = f"Operation: {category if category else 'unspecified'}"
        self.pending_operations.append(operation_description)
            
    def resolve_pending_operation(self, letter: str) -> Optional[str]:
        """Complete a specific pending operation.
        
        Args:
            letter: Letter label of the operation to resolve (A, B, C, etc.)
            
        Returns:
            The operation description if found and resolved, None otherwise
        """
        try:
            # Convert letter to index (A->0, B->1, etc.)
            index = ord(letter) - ord('A')
            if 0 <= index < len(self.pending_operations):
                request = self.pending_operations.pop(index)
                
                # Deactivate if no more operations and not in continuous mode
                if not self.pending_operations and self.activation_mode != "continuous":
                    self.active = False
                return request
            
        except Exception as e:
            logger.error(f"Error resolving operation {letter}: {str(e)}")
            if DEBUG_ENABLED:
                raise
        return None
