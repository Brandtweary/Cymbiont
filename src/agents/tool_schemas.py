from constants import ToolName


TOOL_SCHEMAS = {
    ToolName.CONTEMPLATE_LOOP: {
        "type": "function",
        "function": {
            "name": "contemplate_loop",
            "description": "Enter a tool loop to ponder a given question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ponder during the contemplation loop."
                    }
                },
                "required": ["question"]
            }
        }
    },

    ToolName.MESSAGE_SELF: {
        "type": "function",
        "function": {
            "name": "message_self",
            "description": "Send a message to self within the tool loop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to send to self."
                    }
                },
                "required": ["message"]
            }
        }
    },
    ToolName.EXIT_LOOP: {
        "type": "function",
        "function": {
            "name": "exit_loop",
            "description": "Exits the current tool loop and returns a final message to the conversation partner.",
            "parameters": {
                "type": "object",
                "properties": {
                    "exit_message": {
                        "type": "string",
                        "description": "The final message to return to the conversation partner."
                    }
                },
                "required": ["exit_message"]
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
    ToolName.EXECUTE_TOOL_CALL: {
        "type": "function",
        "function": {
            "name": "execute_tool_call",
            "description": "Execute a tool operation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "The category of operation to perform",
                        "enum": ["shell_command", "file", "test", "search", "system"]
                    }
                },
                "required": ["category"]
            }
        }
    },
    ToolName.TOGGLE_PROMPT_PART: {
        "type": "function",
        "function": {
            "name": "toggle_prompt_part",
            "description": "Toggle a system prompt part on or off. The prompt parts will be assembled in order based on their index.",
            "parameters": {
                "type": "object",
                "properties": {
                    "part_name": {
                        "type": "string",
                        "description": "Name of the system prompt part to toggle",
                        "enum": []  # Placeholder for available prompt parts
                    }
                },
                "required": ["part_name"]
            }
        }
    },
    ToolName.INTRODUCE_SELF: {
        "type": "function",
        "function": {
            "name": "introduce_self",
            "description": "Introduce yourself to the user in a natural way, considering the current conversation context.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    ToolName.SHELL_LOOP: {
        "type": "function",
        "function": {
            "name": "shell_loop",
            "description": "Enter a shell loop where you can chain together shell commands. Automatically toggles shell_command_info on.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    ToolName.RESOLVE_PENDING_OPERATION: {
        "type": "function",
        "function": {
            "name": "resolve_pending_operation",
            "description": "Complete a pending operation identified by its letter label (A, B, C, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "letter": {
                        "type": "string",
                        "description": "The letter label of the operation to resolve."
                    }
                },
                "required": ["letter"]
            }
        }
    }
}