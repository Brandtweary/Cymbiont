from typing import Dict, List, Optional, Union
from .agent_types import TaskStatus, Task
import uuid
from shared_resources import logger

class Taskpad:
    """A class to manage tasks for an agent."""
    
    def __init__(self):
        self.top_level_tasks: Dict[str, Task] = {}
        self.completed_tasks: List[Task] = []
    
    @property
    def has_tasks(self) -> bool:
        """Return whether there are any active tasks."""
        return len(self.top_level_tasks) > 0

    def _get_tasks_by_index(self) -> Dict[int, str]:
        """Get mapping of display indices to task IDs."""
        return {task.display_index: tid for tid, task in self.top_level_tasks.items() 
                if task.display_index is not None}  # All top-level tasks should have display indices

    def _find_first_gap(self) -> int:
        """Find the first unused display index, filling any gaps."""
        used_indices = {task.display_index for task in self.top_level_tasks.values() 
                       if task.display_index is not None}  # All top-level tasks should have display indices
        index = 0
        while index in used_indices:
            index += 1
        return index

    def _cascade_tasks(self, start_index: int) -> None:
        """Move tasks at or after start_index up by one, but only up to the first gap."""
        # Find the first gap after start_index
        gap_index = start_index
        while any(task.display_index == gap_index for task in self.top_level_tasks.values() 
                 if task.display_index is not None):  # All top-level tasks should have display indices
            gap_index += 1

        # Only cascade tasks between start_index and the first gap
        for task in sorted(
            [t for t in self.top_level_tasks.values() if t.display_index is not None],  # All top-level tasks should have display indices
            key=lambda t: t.display_index,  # type: ignore  # We filtered for non-None above
            reverse=True
        ):
            if start_index <= task.display_index <= gap_index:  # type: ignore  # We filtered for non-None above
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
            for task in self.top_level_tasks.values():
                if task.display_index == parent_idx:  # Safe since we're only looking at top-level tasks
                    parent_task = task
                    break
            if parent_task is None:
                logger.warning(f"No task found with index {parent_task_index}")
                return

            # Create the subtask (no display_index needed)
            subtask = Task(
                description=description,
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

        # Create and add the main task (must have display_index)
        task = Task(
            description=description,
            display_index=display_index,
            metadata_tags=metadata_tags,
            status=status,
            top_level=True
        )
        self.top_level_tasks[str(uuid.uuid4())] = task

    def format_taskpad(self) -> str:
        """Format the taskpad for inclusion in system prompt."""
        if not self.has_tasks:
            return "No current tasks"
            
        def format_subtasks(task: Task, indent_level: int = 1) -> List[str]:
            """Helper function to recursively format subtasks.
            
            Args:
                task: The task to format subtasks for
                indent_level: Current indentation level
            """
            subtask_lines = []
            if task.subtasks:
                if task.folded:
                    indent = "    " * indent_level
                    num_subtasks = len(task.subtasks)
                    subtask_lines.append(f"{indent}({num_subtasks} subtask{'s' if num_subtasks != 1 else ''} folded)")
                else:
                    for i, subtask in enumerate(task.subtasks, 1):
                        subtask_tags = f" [{', '.join(subtask.metadata_tags or [])}]" if subtask.metadata_tags else ""
                        subtask_status = f" ({subtask.status.value})" if subtask.status != TaskStatus.READY else ""
                        indent = "    " * indent_level
                        
                        # Add checkbox or checkmark based on completion status
                        status_indicator = "✓" if subtask.status == TaskStatus.COMPLETED else "☐"

                        # Check if this subtask is a top-level task
                        if subtask.top_level:
                            # Add alphabetic index and [blocking] tag if it has a display index
                            display_idx = ""
                            if subtask.display_index is not None:
                                display_idx = f"{chr(ord('A') + min(subtask.display_index, 25))}) "
                            subtask_tags = f" [blocking{', ' + ', '.join(subtask.metadata_tags) if subtask.metadata_tags else ''}]"
                            subtask_lines.append(f"{indent}{status_indicator} {i}. {display_idx}{subtask.description}{subtask_tags}{subtask_status}")
                        else:
                            subtask_lines.append(f"{indent}{status_indicator} {i}. {subtask.description}{subtask_tags}{subtask_status}")
                        
                        # Recursively format any nested subtasks
                        subtask_lines.extend(format_subtasks(subtask, indent_level + 1))
            return subtask_lines
            
        # Sort tasks by display index (all top-level tasks should have display indices)
        sorted_tasks = sorted(
            self.top_level_tasks.items(),
            key=lambda x: x[1].display_index if x[1].display_index is not None else -1
        )
        
        task_lines = []
        hidden_count = max(0, len(sorted_tasks) - 26)
        
        # Only show first 26 tasks in display
        for task_id, task in sorted_tasks[:26]:
            # Format tags if present
            tags_str = f" [{', '.join(task.metadata_tags or [])}]" if task.metadata_tags else ""
            status_str = f" ({task.status.value})" if task.status != TaskStatus.READY else ""
            
            # Add checkbox or checkmark based on completion status
            status_indicator = "✓" if task.status == TaskStatus.COMPLETED else "☐"
            
            # Convert numeric index to A-Z for display
            assert task.display_index is not None, "Top-level task must have display_index"
            display_idx = chr(ord('A') + min(task.display_index, 25))
            task_lines.append(f"{status_indicator} {display_idx}) {task.description}{tags_str}{status_str}")
            
            # Add subtasks if present using recursive helper
            task_lines.extend(format_subtasks(task))
        
        formatted_tasks = "\n".join(task_lines)
        if hidden_count > 0:
            formatted_tasks += f"\n({hidden_count} additional tasks hidden)"
            
        return formatted_tasks

    def add_task_dependency(
        self,
        blocked_task_index: str,
        blocking_task_index: str,
        insertion_index: Optional[int] = None
    ) -> None:
        """Add a task dependency by adding the blocking task as a subtask of the blocked task.
        
        Args:
            blocked_task_index: Index of the task that is blocked (A-Z)
            blocking_task_index: Index of the task that is blocking (A-Z)
            insertion_index: Optional 1-based index for insertion into subtask list
        """
        # Convert A-Z indices to numeric indices
        blocked_idx = ord(blocked_task_index.upper()) - ord('A')
        blocking_idx = ord(blocking_task_index.upper()) - ord('A')

        # Find the tasks with these display indices
        blocked_task = None
        blocking_task = None
        for task in self.top_level_tasks.values():
            if task.display_index == blocked_idx:  # Safe since we're only looking at top-level tasks
                blocked_task = task
            elif task.display_index == blocking_idx:  # Safe since we're only looking at top-level tasks
                blocking_task = task
            if blocked_task and blocking_task:
                break

        # Validate task indices
        if not blocked_task:
            logger.warning(f"No task found with index {blocked_task_index}")
            return
        if not blocking_task:
            logger.warning(f"No task found with index {blocking_task_index}")
            return
        if blocked_task == blocking_task:
            logger.warning("A task cannot block itself")
            return

        # Convert insertion_index to 0-based for internal use
        if insertion_index is not None:
            insertion_index = insertion_index - 1

        # Add the blocking task as a subtask of the blocked task
        blocked_task.add_subtask(blocking_task, insertion_index)

    def complete_task(self, display_index: str, subtask_index: Optional[int] = None) -> None:
        """Mark a task as completed.
        
        Args:
            display_index: Index of the task (A-Z)
            subtask_index: Optional 1-based index of subtask to complete
        """
        # Convert display index to numeric (0-based)
        task_idx = ord(display_index.upper()) - ord('A')
        
        # Find the task with this display index and its ID
        target_task = None
        target_task_id = None
        for tid, task in self.top_level_tasks.items():
            if task.display_index == task_idx:
                target_task = task
                target_task_id = tid
                break
                
        if target_task is None:
            logger.warning(f"No task found with index {display_index}")
            return
            
        # At this point, we found a task so target_task_id must not be None
        assert target_task_id is not None, "Task ID cannot be None for top-level task"
            
        if subtask_index is not None:
            # Convert to 0-based index
            idx = subtask_index - 1
            if not target_task.subtasks or idx >= len(target_task.subtasks):
                logger.warning(f"No subtask found at index {subtask_index} for task {display_index}")
                return
            target_task.subtasks[idx].status = TaskStatus.COMPLETED
        else:
            target_task.status = TaskStatus.COMPLETED
            # Clear display index since it's no longer in the active list
            target_task.display_index = None
            # Move the task to completed_tasks and remove from top_level_tasks
            self.completed_tasks.append(target_task)
            del self.top_level_tasks[target_task_id]
            # Adjust display indices for remaining tasks
            self._cascade_tasks_down(task_idx)
            
    def _cascade_tasks_down(self, start_index: int) -> None:
        """Move tasks after start_index down by one to fill the gap."""
        for task in sorted(
            [t for t in self.top_level_tasks.values() if t.display_index is not None],
            key=lambda t: t.display_index  # type: ignore  # We filtered for non-None above
        ):
            if task.display_index > start_index:  # type: ignore  # We filtered for non-None above
                task.display_index -= 1

    def edit_task(
        self,
        display_index: str,
        subtask_index: Optional[int] = None,
        new_description: Optional[str] = None,
        new_metadata_tags: Optional[List[str]] = None,
        new_status: Optional[TaskStatus] = None,
        delete_task: bool = False
    ) -> None:
        """Edit a task's properties.
        
        Args:
            display_index: Index of the task (A-Z)
            subtask_index: Optional 1-based index of subtask to edit
            new_description: Optional new description for the task
            new_metadata_tags: Optional new metadata tags for the task
            new_status: Optional new status for the task
            delete_task: If True, delete the task instead of editing it
        """
        # Convert display index to numeric (0-based)
        task_idx = ord(display_index.upper()) - ord('A')
        
        # Find the task with this display index
        target_task = None
        parent_task = None
        for task in self.top_level_tasks.values():
            if task.display_index == task_idx:
                target_task = task
                break
                
        if target_task is None:
            logger.warning(f"No task found with index {display_index}")
            return
        
        if subtask_index is not None:
            # Convert to 0-based index
            idx = subtask_index - 1
            if not target_task.subtasks or idx >= len(target_task.subtasks):
                logger.warning(f"No subtask found at index {subtask_index} for task {display_index}")
                return
            parent_task = target_task
            target_task = target_task.subtasks[idx]

        if delete_task:
            if subtask_index is not None:
                assert parent_task is not None, "Parent task cannot be None if subtask_index was valid"
                if not parent_task.remove_subtask(target_task):
                    logger.warning(f"Failed to remove subtask {subtask_index} from task {display_index}")
            else:
                # Remove top-level task
                task_id = None
                for tid, task in self.top_level_tasks.items():
                    if task == target_task:
                        task_id = tid
                        break
                if task_id:
                    del self.top_level_tasks[task_id]
            return
        
        # Update task properties if new values provided
        if new_description is not None:
            target_task.description = new_description
        if new_metadata_tags is not None:
            target_task.metadata_tags = new_metadata_tags
        if new_status is not None:
            target_task.status = new_status
            # If this is a top-level task being marked as completed, handle it
            if new_status == TaskStatus.COMPLETED and subtask_index is None:
                self.complete_task(display_index)

    def fold_task(self, display_index: str) -> None:
        """Fold a task to hide its subtasks in display.
        
        Args:
            display_index: Index of the task (A-Z)
        """
        # Convert display index to numeric (0-based)
        task_idx = ord(display_index.upper()) - ord('A')
        
        # Find the task with this display index
        for task in self.top_level_tasks.values():
            if task.display_index == task_idx:
                task.folded = True
                return
                
        logger.warning(f"No task found with index {display_index}")
        
    def unfold_task(self, display_index: str) -> None:
        """Unfold a task to show its subtasks in display.
        
        Args:
            display_index: Index of the task (A-Z)
        """
        # Convert display index to numeric (0-based)
        task_idx = ord(display_index.upper()) - ord('A')
        
        # Find the task with this display index
        for task in self.top_level_tasks.values():
            if task.display_index == task_idx:
                task.folded = False
                return
                
        logger.warning(f"No task found with index {display_index}")
