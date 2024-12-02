"""Default values for system prompt parts."""

DEFAULT_SYSTEM_PROMPT_PARTS = {
    "tool_calling": {
        "toggled": True,
        "order": 1
    },
    "making_code_changes": {
        "toggled": True,
        "order": 2
    },
    "debugging": {
        "toggled": True,
        "order": 3
    },
    "calling_external_apis": {
        "toggled": True,
        "order": 4
    },
    "communication": {
        "toggled": True,
        "order": 5
    },
    "progressive_summary": {
        "toggled": True,
        "order": 6
    }
}
