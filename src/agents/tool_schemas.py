from llms.llm_types import ToolName


TOOL_SCHEMAS = {
    ToolName.MESSAGE_SELF: {
        "type": "function",
        "function": {
            "name": "message_self",
            "description": "Record a message to yourself. It will be automatically prefixed with [SELF-ONLY].",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to record."
                    }
                },
                "required": ["message"]
            }
        }
    },
    ToolName.EXECUTE_SHELL_COMMAND: {
        "type": "function",
        "function": {
            "name": "execute_shell_command",
            "description": "Execute a shell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to execute. Commands marked with * accept arguments.",
                        "enum": []  # Will be populated at runtime
                    },
                    "args": {
                        "type": "array",
                        "description": "Arguments to pass to the command.",
                        "items": {
                            "type": "string"
                        }
                    }
                },
                "required": ["command"]
            }
        }
    },
    ToolName.TOGGLE_PROMPT_PART: {
        "type": "function",
        "function": {
            "name": "toggle_prompt_part",
            "description": "Toggle a system prompt part on or off manually. Note that prompt parts will get automatically toggled on by the system when relevant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "part_name": {
                        "type": "string",
                        "description": "Name of the system prompt part to toggle. Parts marked with * are currently toggled on.",
                        "enum": []  # Placeholder for available prompt parts
                    }
                },
                "required": ["part_name"]
            }
        }
    },
    ToolName.MEDITATE: {
        "type": "function",
        "function": {
            "name": "meditate",
            "description": "Signal to the system that you have completed all tasks and have nothing else to do.",
            "parameters": {
                "type": "object",
                "properties": {
                    "wait_time": {
                        "type": "integer",
                        "description": "Optional number of seconds to wait.",
                        "default": 0
                    }
                },
                "required": []
            }
        }
    },
    ToolName.TOGGLE_TOOL: {
        "type": "function",
        "function": {
            "name": "toggle_tool",
            "description": "Toggle the availability of a specified tool on or off.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "The name of the tool to toggle. Tools marked with * are currently toggled on.",
                        "enum": []  # Placeholder for available tools
                    },
                },
                "required": ["tool_name"]
            }
        }
    },
    ToolName.ADD_TASK: {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Add a task to the taskpad. Tasks can be added as top-level tasks or as subtasks under an existing task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Description of the task"
                    },
                    "parent_task_index": {
                        "type": "string",
                        "description": "Optional index of the parent task (A-Z). Only provide this if adding a subtask to an existing task.",
                        "pattern": "^[A-Z]$"
                    },
                    "insertion_index": {
                        "oneOf": [
                            {
                                "type": "string",
                                "pattern": "^([A-Z]|[1-9][0-9]*)$"
                            },
                            {
                                "type": "integer",
                                "minimum": 1
                            }
                        ],
                        "description": "Optional insertion index. For top-level tasks, must be A-Z. For subtasks, must be a number (1-based)."
                    },
                    "metadata_tags": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Optional list of metadata tags to associate with the task"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["ready", "in-progress", "tentative", "postponed", "ongoing"],
                        "description": "Optional task status. Defaults to 'ready'."
                    }
                },
                "required": ["description"]
            }
        }
    },
    ToolName.ADD_TASK_DEPENDENCY: {
        "type": "function",
        "function": {
            "name": "add_task_dependency",
            "description": "Add a dependency between two tasks, making one task block another. The blocking task will appear as a subtask of the blocked task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "blocked_task_index": {
                        "type": "string",
                        "description": "Index of the task that is blocked (A-Z)",
                        "pattern": "^[A-Z]$"
                    },
                    "blocking_task_index": {
                        "type": "string",
                        "description": "Index of the task that is blocking (A-Z)",
                        "pattern": "^[A-Z]$"
                    },
                    "insertion_index": {
                        "type": "integer",
                        "description": "Optional 1-based index for where to insert the blocking task in the blocked task's subtask list",
                        "minimum": 1
                    }
                },
                "required": ["blocked_task_index", "blocking_task_index"]
            }
        }
    },
    ToolName.COMPLETE_TASK: {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task or subtask as completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "display_index": {
                        "type": "string",
                        "description": "Index of the task to complete (A-Z)",
                        "pattern": "^[A-Z]$"
                    },
                    "subtask_index": {
                        "type": "integer",
                        "description": "Optional 1-based index of the subtask to complete. If not provided, the main task will be completed.",
                        "minimum": 1
                    }
                },
                "required": ["display_index"]
            }
        }
    },
    ToolName.EDIT_TASK: {
        "type": "function",
        "function": {
            "name": "edit_task",
            "description": "Edit a task's properties, such as its description, status, or metadata tags. Can also delete a task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "display_index": {
                        "type": "string",
                        "description": "Index of the task to edit (A-Z)",
                        "pattern": "^[A-Z]$"
                    },
                    "subtask_index": {
                        "type": "integer",
                        "description": "Optional 1-based index of the subtask to edit. If not provided, the main task will be edited.",
                        "minimum": 1
                    },
                    "new_description": {
                        "type": "string",
                        "description": "Optional new description for the task"
                    },
                    "new_metadata_tags": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Optional new list of metadata tags for the task"
                    },
                    "new_status": {
                        "type": "string",
                        "enum": ["ready", "in-progress", "tentative", "postponed", "ongoing", "completed"],
                        "description": "Optional new status for the task"
                    },
                    "delete_task": {
                        "type": "boolean",
                        "description": "If true, delete the task instead of editing it",
                        "default": False}
                },
                "required": ["display_index"]
            }
        }
    },
    ToolName.FOLD_TASK: {
        "type": "function",
        "function": {
            "name": "fold_task",
            "description": "Hide a task's subtasks in the taskpad.",
            "parameters": {
                "type": "object",
                "properties": {
                    "display_index": {
                        "type": "string",
                        "description": "Index of the task to fold (A-Z)",
                        "pattern": "^[A-Z]$"
                    }
                },
                "required": ["display_index"]
            }
        }
    },
    ToolName.UNFOLD_TASK: {
        "type": "function",
        "function": {
            "name": "unfold_task",
            "description": "Show a task's subtasks in the taskpad.",
            "parameters": {
                "type": "object",
                "properties": {
                    "display_index": {
                        "type": "string",
                        "description": "Index of the task to unfold (A-Z)",
                        "pattern": "^[A-Z]$"
                    }
                },
                "required": ["display_index"]
            }
        }
    }
}