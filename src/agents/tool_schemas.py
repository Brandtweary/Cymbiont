from constants import ToolName
from typing import Dict, Any, List, Set, Optional, Union
from copy import deepcopy
from shared_resources import logger
from custom_dataclasses import CommandData

def format_tool_schema(schema: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """Format a single tool schema, handling any dynamic content based on runtime state.
    
    Some schemas require specific kwargs for initial formatting in CymbiontShell.__init__:
    - toggle_prompt_part: Requires 'system_prompt_parts' for available prompt parts
    - execute_shell_command: Requires 'command_metadata' for available shell commands
    
    These kwargs should be provided when calling format_all_tool_schemas in CymbiontShell.__init__.
    Other dynamic formatting (like toggle_prompt_part's current system_prompt_parts) happens at runtime.
    
    Args:
        schema: The base schema to format
        **kwargs: Dynamic parameters for initial schema formatting:
            - system_prompt_parts: Required for toggle_prompt_part schema
            - command_metadata: Required for execute_shell_command schema
    """
    schema = deepcopy(schema)
    schema_name = schema.get("function", {}).get("name")
    
    if schema_name == "toggle_prompt_part":
        if "system_prompt_parts" not in kwargs:
            logger.warning("Missing 'system_prompt_parts' kwarg required for toggle_prompt_part schema. "
                         "This should be added to the format_all_tool_schemas call in CymbiontShell.__init__")
            return schema
            
        part_names = list(kwargs["system_prompt_parts"].parts.keys())
        schema["function"]["parameters"]["properties"]["part_name"]["enum"] = part_names
    
    elif schema_name == "execute_shell_command":  
        if "command_metadata" not in kwargs:
            logger.warning("Missing 'command_metadata' kwarg required for execute_shell_command schema. "
                         "This should be added to the format_all_tool_schemas call in CymbiontShell.__init__")
            return schema
            
        # Mark commands that take args with an asterisk
        marked_commands = []
        for cmd, cmd_data in kwargs["command_metadata"].items():
            if cmd_data.takes_args:
                marked_commands.append(f"{cmd}*")
            else:
                marked_commands.append(cmd)
                
        schema["function"]["parameters"]["properties"]["command"]["enum"] = marked_commands
    
    elif schema_name == "use_tool":
        # For use_tool, provide a list of all available tool names
        tool_names = [tool.value for tool in ToolName]
        schema["function"]["parameters"]["properties"]["tool_name"]["enum"] = tool_names
    
    return schema

def format_all_tool_schemas(**kwargs) -> None:
    """Format all tool schemas with dynamic content.
    
    Args:
        **kwargs: Dynamic parameters that may be required by different schemas:
            - system_prompt_parts: Required for toggle_prompt_part schema
            - command_metadata: Required for execute_shell_command schema
    """
    # Format each schema
    for tool_name, schema in TOOL_SCHEMAS.items():
        TOOL_SCHEMAS[tool_name] = format_tool_schema(schema, **kwargs)

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
    ToolName.USE_TOOL: {
        "type": "function",
        "function": {
            "name": "use_tool",
            "description": "Request the tool agent to use a specific tool. This triggers a tool response from the tool agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "The name of the tool to use."
                    }
                },
                "required": ["tool_name"]
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
                "required": ["command", "args"]
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
    }
}