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
    ToolName.REQUEST_TOOL_USE: {
        "type": "function",
        "function": {
            "name": "request_tool_use",
            "description": "Request the tool agent to use a specific tool. This triggers a tool response from the tool agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "The name of the tool to use. Only include if you know which tool. Otherwise, let the tool agent decide.",
                    }
                },
                "required": []
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
    ToolName.RESOLVE_TOOL_REQUEST: {
        "type": "function",
        "function": {
            "name": "resolve_tool_request",
            "description": "Resolve a specific tool request by its letter label (A, B, C, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_letter": {
                        "type": "string",
                        "description": "The letter label of the request to resolve (A, B, C, etc.)",
                        "pattern": "^[A-Z]$"
                    }
                },
                "required": ["request_letter"]
            }
        }
    }
}