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
                ToolName.MEDITATE
            }
        )
        self.activation_mode = activation_mode
        self.active = activation_mode == "continuous"  # Active by default in continuous mode
        self.pending_operations: List[str] = []  # List of pending operations
            