from enum import Enum


class ActivationMode(Enum):
    """Enum for agent activation modes.
    
    CONTINUOUS: Agent runs continuously, only deactivates with meditate tool
    CHAT: Agent activates for tool calls, deactivates after text responses
    """
    CONTINUOUS = "continuous"
    CHAT = "chat"