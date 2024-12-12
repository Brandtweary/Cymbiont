from enum import Enum
from dataclasses import dataclass
from typing import List, Optional


class ActivationMode(Enum):
    """Enum for agent activation modes.
    
    CONTINUOUS: Agent runs continuously, only deactivates with meditate tool
    CHAT: Agent activates for tool calls, deactivates after text responses
    """
    CHAT = "chat"
    CONTINUOUS = "continuous"

class TaskStatus(Enum):
    READY = "ready"
    IN_PROGRESS = "in-progress"
    TENTATIVE = "tentative"
    POSTPONED = "postponed"
    ONGOING = "ongoing"
    COMPLETED = "completed"

@dataclass
class Task:
    """A task with its description and metadata."""
    description: str
    display_index: Optional[int] = None  # Numeric index for storage
    status: TaskStatus = TaskStatus.READY
    metadata_tags: Optional[List[str]] = None
    subtasks: Optional[List["Task"]] = None  # List of subtasks
    top_level: bool = False  # Whether this is a top-level task
    folded: bool = False  # Whether subtasks are hidden in display

    def __post_init__(self):
        """Initialize optional fields."""
        if self.metadata_tags is None:
            self.metadata_tags = []
        if self.subtasks is None:
            self.subtasks = []

    def add_subtask(self, subtask: "Task", insertion_index: Optional[int] = None) -> None:
        """Add a subtask at the specified index or at the end if no index provided.
        
        Args:
            subtask: The task to add as a subtask
            insertion_index: Optional 0-based index for insertion
        """
        # Ensure subtasks list exists
        if self.subtasks is None:
            self.subtasks = []
            
        if insertion_index is not None:
            # Insert will handle index bounds automatically
            self.subtasks.insert(min(insertion_index, len(self.subtasks)), subtask)
        else:
            self.subtasks.append(subtask)