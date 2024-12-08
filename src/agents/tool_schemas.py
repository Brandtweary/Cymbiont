from llms.llm_types import ToolName


TOOL_SCHEMAS = {
    ToolName.MESSAGE_SELF: {
        "type": "function",
        "function": {
            "name": "message_self",
            "description": "Record a message to yourself. Useful for thinking through a problem before responding.",
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
    }
}