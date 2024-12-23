import asyncio
from shared_resources import logger, AGENT_NAME, DEBUG_ENABLED
from llms.model_registry import registry
from llms.llm_types import ToolName
from .chat_history import ChatHistory
from .agent import Agent
from .agent_types import ActivationMode
from typing import Any, Optional

class ChatAgent(Agent):
    """
    An agent that responds to user messages and can use tools.
    Unlike ToolAgent, this agent generates chat messages and uses tools only when needed.
    """
    
    def __init__(self, chat_history: ChatHistory, agent_name: str = AGENT_NAME, model: Optional[str] = None, activation_mode: ActivationMode = ActivationMode.CONTINUOUS):
        default_tools = {
            ToolName.TOGGLE_PROMPT_PART,
            ToolName.TOGGLE_TOOL,
        #    ToolName.MESSAGE_SELF,
          #  ToolName.ADD_NOTE,  # don't forget to re-enable this tool, it's just annoying when the agent uses it for no reason
         #   ToolName.READ_NOTES,
        }
        if activation_mode == ActivationMode.CONTINUOUS:
            default_tools.add(ToolName.MEDITATE)
        
        super().__init__(
            chat_history=chat_history,
            agent_name=agent_name,
            model=model or registry.chat_agent_model,
            activation_mode=activation_mode,
            default_tools=default_tools
        )