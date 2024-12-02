from constants import ToolName
from typing import Dict, Any, List, Set, Optional, Union
from copy import deepcopy
from shared_resources import logger

def format_tool_schema(schema: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """Format a single tool schema, handling any dynamic content based on runtime state.
    
    Args:
        schema: The base schema to format
        **kwargs: Dynamic parameters that may be required by different schemas
    """
    schema = deepcopy(schema)
    schema_name = schema.get("function", {}).get("name")
    
    if schema_name == "toggle_prompt_part":
        if "system_prompt_parts" not in kwargs:
            logger.warning("system_prompt_parts required for toggle_prompt_part schema formatting")
            return schema
            
        part_names = list(kwargs["system_prompt_parts"].parts.keys())
        schema["function"]["parameters"]["properties"]["part_name"]["enum"] = part_names
    
    elif schema_name == "execute_shell_command":
        if "commands" not in kwargs:
            logger.warning("commands required for execute_shell_command schema formatting")
            return schema
            
        schema["function"]["parameters"]["properties"]["command"]["enum"] = kwargs["commands"]
    
    return schema

def format_all_tool_schemas(tools: Set[ToolName], **kwargs) -> None:
    """Format all tool schemas for the specified tools, handling any dynamic content.
    Modifies TOOL_SCHEMAS in place.
    
    Args:
        tools: Set of tools to format schemas for
        **kwargs: Parameters required by different schema types:
            - system_prompt_parts: Required for toggle_prompt_part schema
            - commands: Required for execute_shell_command schema
    """
    for tool in tools:
        if tool in TOOL_SCHEMAS:
            TOOL_SCHEMAS[tool] = format_tool_schema(TOOL_SCHEMAS[tool], **kwargs)

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
            "description": "Execute a shell command with given arguments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                        "enum": []  # Placeholder for available commands
                    },
                    "args": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "List of arguments for the command."
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
    }
}