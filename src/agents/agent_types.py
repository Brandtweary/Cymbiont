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

class ShellAccessTier(Enum):
    """Access tiers for shell command execution.
    
    TIER_1_PROJECT_READ: Read-only access to project files only. Cannot execute files or navigate outside project directory. Uses OS-level isolation.
    
    TIER_2_SYSTEM_READ: Read-only access to system files. Cannot execute files but can navigate outside project directory. Uses OS-level isolation.
    
    TIER_3_PROJECT_RESTRICTED: Read-only access to system files with write access to agent notes directory only. Cannot execute files. Uses OS-level isolation.
    
    TIER_4_PROJECT_WRITE: Read-only access to system files with read/write/execute access within project directory. Uses OS-level isolation. Not recommended.
    
    TIER_5_UNRESTRICTED: Full system access with no restrictions. No OS-level isolation. Not recommended.

    TODO: Consider implementing Docker containers for stronger isolation, particularly
    for TIER_1_PROJECT_READ. Restricting filesystem access to only the project directory
    is difficult to enforce at the OS level without proper containerization. While command
    validation provides good protection, Docker would provide proper filesystem isolation
    with industry-standard containerization.
    """
    TIER_1_PROJECT_READ = 1
    TIER_2_SYSTEM_READ = 2
    TIER_3_PROJECT_RESTRICTED_WRITE = 3
    TIER_4_PROJECT_WRITE_EXECUTE = 4
    TIER_5_UNRESTRICTED = 5

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

    def remove_subtask(self, subtask: "Task") -> bool:
        """Remove a subtask from this task.
        
        Args:
            subtask: The task to remove from subtasks
            
        Returns:
            bool: True if subtask was found and removed, False otherwise
        """
        if self.subtasks and subtask in self.subtasks:
            self.subtasks.remove(subtask)
            return True
        return False