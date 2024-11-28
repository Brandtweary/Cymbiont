from constants import ToolName
from typing import Dict, Any


TOOL_SCHEMAS: Dict[ToolName, Dict[str, Any]] = {
    ToolName.CONTEMPLATE: {
        "type": "function",
        "function": {
            "name": "contemplate",
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
    }
}