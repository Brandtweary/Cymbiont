from typing import Optional, Set, List, Literal, Any, Dict, Tuple
from shared_resources import logger, AGENT_NAME
from custom_dataclasses import SystemPromptPartsData, SystemPromptPartInfo
from model_configuration import CHAT_AGENT_MODEL 
from constants import ToolChoice, ToolName
from .agent import Agent
from .chat_history import ChatHistory


class ToolAgent(Agent):
    """Agent focused on making tool calls and optionally generating messages."""

    def __init__(self, chat_history: ChatHistory, activation_mode: str = "continuous"):
        super().__init__(
            chat_history=chat_history,
            model=CHAT_AGENT_MODEL,
            agent_name=f"Tool {AGENT_NAME}",
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
                ToolName.RESOLVE_TOOL_REQUEST
            }
        )
        self.activation_mode = activation_mode
        self.active = activation_mode == "continuous"  # Active by default in continuous mode
        self.active_tool_requests: List[str] = []  # List of active tool requests
        
    def setup_unique_prompt_parts(self, system_prompt_parts: SystemPromptPartsData, kwargs: Dict[str, Any]) -> Tuple[SystemPromptPartsData, Dict[str, Any]]:
        """Add active tool requests to prompt parts if any exist."""
        if self.active_tool_requests:
            system_prompt_parts.parts["active_tool_requests"] = SystemPromptPartInfo(
                toggled=True,
                index=len(system_prompt_parts.parts)
            )
            # Add letter labels A, B, C, etc.
            labeled_requests = [f"{chr(65 + i)}) {req}" for i, req in enumerate(self.active_tool_requests)]
            kwargs["active_tool_requests"] = "\n".join(labeled_requests)
        return system_prompt_parts, kwargs
            
    def activate_for_tool_request(self, tool_name: Optional[str] = None) -> None:
        """Activate the agent for a tool request.
        
        Args:
            tool_name: Optional name of the tool being requested
        """
        self.active = True
        request_description = f"Tool request: {tool_name if tool_name else 'unspecified tool'}"
        self.active_tool_requests.append(request_description)
            
    def resolve_tool_request(self, request_letter: str) -> Optional[str]:
        """Mark a specific tool request as resolved.
        
        Args:
            request_letter: Letter label of the request to resolve (A, B, C, etc.)
            
        Returns:
            The resolved request description if found and resolved, None otherwise
        """
        try:
            # Convert letter to index (A->0, B->1, etc.)
            index = ord(request_letter) - ord('A')
            if 0 <= index < len(self.active_tool_requests):
                request = self.active_tool_requests.pop(index)
                
                # Deactivate if no more requests and not in continuous mode
                if not self.active_tool_requests and self.activation_mode != "continuous":
                    self.active = False
                return request
            
            return None
        except (TypeError, ValueError):
            return None
