import asyncio
from unittest.mock import DEFAULT
from shared_resources import logger, AGENT_NAME, DEBUG_ENABLED
from model_configuration import CHAT_AGENT_MODEL
from .chat_history import ChatHistory
from constants import ToolName
from .agent import Agent

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
                ToolName.USE_TOOL,
                ToolName.INTRODUCE_SELF
            }
        )