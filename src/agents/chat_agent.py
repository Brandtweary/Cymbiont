import asyncio
from shared_resources import logger, AGENT_NAME, DEBUG_ENABLED
from llms.model_configuration import CHAT_AGENT_MODEL
from llms.llm_types import ToolName
from .chat_history import ChatHistory
from .agent import Agent
from typing import Any

class ChatAgent(Agent):
    """
    An agent that responds to user messages and can use tools.
    Unlike ToolAgent, this agent generates chat messages and uses tools only when needed.
    """
    
    def __init__(self, chat_history: ChatHistory, agent_name: str = AGENT_NAME, model: str = CHAT_AGENT_MODEL):
        super().__init__(
            chat_history=chat_history,
            agent_name=agent_name,
            model=model,
            default_tools={
                ToolName.TOGGLE_PROMPT_PART,
                ToolName.MEDITATE
            }
        )