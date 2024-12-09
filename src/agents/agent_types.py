from enum import Enum


class ActivationMode(Enum):
    """Enum for agent activation modes.
    
    CONTINUOUS: Agent runs continuously, only deactivates with meditate tool
    AS_NEEDED: Agent activates for tool calls, deactivates after text responses
    """
    CONTINUOUS = "continuous"
    AS_NEEDED = "as_needed"