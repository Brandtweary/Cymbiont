from typing import Optional, Set, List, Literal
from shared_resources import logger, AGENT_NAME
from custom_dataclasses import SystemPromptPartsData, SystemPromptPartInfo
from model_configuration import CHAT_AGENT_MODEL 
from constants import ToolChoice, ToolName
from .agent import Agent
from .chat_history import ChatHistory

DEFAULT_TOOL_AGENT_SYSTEM_PROMPT_PARTS = SystemPromptPartsData(parts={
    "tool_agent_base_prompt": SystemPromptPartInfo(toggled=True, index=0),
    "cymbiont_agent_overview": SystemPromptPartInfo(toggled=False, index=1),
    "shell_command_info": SystemPromptPartInfo(toggled=True, index=2),
    "handling_shell_command_requests": SystemPromptPartInfo(toggled=True, index=3),
})

class ToolAgent(Agent):
    """Agent focused on making tool calls and optionally generating messages."""

    def __init__(self, chat_history: ChatHistory):
        super().__init__(
            chat_history=chat_history,
            model=CHAT_AGENT_MODEL,
            agent_name=f"Tool {AGENT_NAME}",
            default_system_prompt_parts=SystemPromptPartsData(
                parts={
                    "tool_agent_base_prompt": SystemPromptPartInfo(toggled=True, index=0),
                    "cymbiont_agent_overview": SystemPromptPartInfo(toggled=False, index=1),
                    "shell_command_info": SystemPromptPartInfo(toggled=True, index=2),
                    "handling_shell_command_requests": SystemPromptPartInfo(toggled=True, index=3),
                }
            ),
            default_tool_choice=ToolChoice.REQUIRED,
            default_temperature=0.0,
            default_tools={
                ToolName.CONTEMPLATE_LOOP,
                ToolName.EXECUTE_SHELL_COMMAND,
                ToolName.SHELL_LOOP,
                ToolName.TOGGLE_PROMPT_PART
            }
        )
