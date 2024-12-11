from typing import Dict, List, Optional, Union
from .agent_types import TaskStatus, Task
import uuid
from shared_resources import logger

class Taskpad:
    """A class to manage tasks for an agent."""
    
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
    
    @property
    def has_tasks(self) -> bool:
        """Return whether there are any active tasks."""
        return len(self.tasks) > 0

    def _get_tasks_by_index(self) -> Dict[int, str]:
        """Get mapping of display indices to task IDs."""
        return {task.display_index: tid for tid, task in self.tasks.items()}

    def _find_next_id(self) -> str:
        """Find next available task ID."""
        return str(uuid.uuid4())

    def _find_first_gap(self) -> int:
        """Find the first unused display index, filling any gaps."""
        used_indices = {task.display_index for task in self.tasks.values()}
        index = 0
        while index in used_indices:
            index += 1
        return index

    def _cascade_tasks(self, start_index: int) -> None:
        """Move tasks at or after start_index up by one, but only up to the first gap."""
        # Find the first gap after start_index
        gap_index = start_index
        while any(task.display_index == gap_index for task in self.tasks.values()):
            gap_index += 1

        # Only cascade tasks between start_index and the first gap
        for task in sorted(self.tasks.values(), key=lambda t: t.display_index, reverse=True):
            if start_index <= task.display_index < gap_index:
                task.display_index += 1

    def add_task(
        self,
        description: str,
        parent_task_index: Optional[str] = None,
        insertion_index: Optional[Union[str, int]] = None,
        metadata_tags: Optional[List[str]] = None,
        status: TaskStatus = TaskStatus.READY,
    ) -> None:
        """Add a task to the taskpad.
        
        Args:
            description: Task description
            parent_task_index: Optional index of parent task (A-Z)
            insertion_index: Optional index for insertion. For main tasks, must be A-Z.
                           For subtasks, must be a number (1-based index).
            metadata_tags: Optional list of metadata tags
            status: Task status, defaults to READY
        """
        if not self.has_tasks and parent_task_index is not None:
            logger.warning("Cannot add subtask when no tasks exist")
            return

        # If this is a subtask, add it to the parent task
        if parent_task_index is not None:
            parent_idx = ord(parent_task_index.upper()) - ord('A')
            # Find the task with this display index
            parent_task = None
            for task in self.tasks.values():
                if task.display_index == parent_idx:
                    parent_task = task
                    break
            if parent_task is None:
                logger.warning(f"No task found with index {parent_task_index}")
                return

            # Create the subtask
            subtask = Task(
                description=description,
                display_index=parent_idx,  # Use parent's index for subtask
                metadata_tags=metadata_tags,
                status=status
            )

            # Add subtask at specific index if provided
            subtask_idx = None
            if insertion_index is not None:
                if isinstance(insertion_index, str) and insertion_index.isdigit():
                    subtask_idx = int(insertion_index) - 1  # Convert to 0-based index
                elif isinstance(insertion_index, int):
                    subtask_idx = insertion_index - 1  # Convert to 0-based index
                else:
                    logger.warning("Subtask insertion index must be a number")
                    return

            parent_task.add_subtask(subtask, subtask_idx)
            return

        # This is a main task
        if insertion_index is not None:
            if not isinstance(insertion_index, str) or not insertion_index.isalpha() or len(insertion_index) != 1:
                logger.warning("Main task insertion index must be a single letter A-Z")
                return
            display_index = ord(insertion_index.upper()) - ord('A')
            self._cascade_tasks(display_index)
        else:
            display_index = self._find_first_gap()

        # Create and add the main task
        task = Task(
            description=description,
            display_index=display_index,
            metadata_tags=metadata_tags,
            status=status
        )
        self.tasks[str(uuid.uuid4())] = task

    def format_taskpad(self) -> str:
        """Format the taskpad for inclusion in system prompt."""
        if not self.has_tasks:
            return "No current tasks"
            
        # Sort tasks by display index
        sorted_tasks = sorted(
            self.tasks.items(),
            key=lambda x: x[1].display_index
        )
        
        task_lines = []
        hidden_count = max(0, len(sorted_tasks) - 26)
        
        # Only show first 26 tasks in display
        for task_id, task in sorted_tasks[:26]:
            # Format tags if present
            tags_str = f" [{', '.join(task.metadata_tags or [])}]" if task.metadata_tags else ""
            status_str = f" ({task.status.value})" if task.status != TaskStatus.READY else ""
            
            # Convert numeric index to A-Z for display (only first 26 tasks get letters)
            display_idx = chr(ord('A') + min(task.display_index, 25))
            task_lines.append(f"{display_idx}) {task.description}{tags_str}{status_str}")
            
            # Add subtasks if present
            if task.subtasks:
                for i, subtask in enumerate(task.subtasks, 1):
                    subtask_tags = f" [{', '.join(subtask.metadata_tags or [])}]" if subtask.metadata_tags else ""
                    subtask_status = f" ({subtask.status.value})" if subtask.status != TaskStatus.READY else ""
                    task_lines.append(f"    {i}. {subtask.description}{subtask_tags}{subtask_status}")
        
        formatted_tasks = "\n".join(task_lines)
        if hidden_count > 0:
            formatted_tasks += f"\n({hidden_count} additional tasks hidden)"
            
        return formatted_tasks
