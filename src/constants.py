from enum import IntEnum, Enum
import logging

class LogLevel(IntEnum):
    BENCHMARK = logging.INFO + 5
    PROMPT = logging.INFO + 6
    RESPONSE = logging.INFO + 7
    SHELL = logging.INFO + 8
    TOOL = logging.INFO + 9

    @property
    def name(self) -> str:
        return self._name_

class ToolName(Enum):
    CONTEMPLATE_LOOP = "contemplate_loop"
    EXIT_LOOP = "exit_loop"
    MESSAGE_SELF = "message_self"
    EXECUTE_SHELL_COMMAND = "execute_shell_command"
    TOGGLE_PROMPT_PART = "toggle_prompt_part"
    INTRODUCE_SELF = "introduce_self"
    SHELL_LOOP = "shell_loop"

class LLM(Enum):
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"
    O1_PREVIEW = "o1-preview"
    SONNET_3_5 = "claude-3-5-sonnet-latest"
    HAIKU_3_5 = "claude-3-5-haiku-latest"

class CommandArgType(Enum):
    """Types of arguments that shell commands can accept"""
    FILENAME = "filename"      # File name
    ENTRY = "entry"       # File or folder name
    TEXT = "text"             # Free-form text
    FLAG = "flag"             # Command flag (e.g., -v)
    COMMAND = "command"       # Command name (for help command)

# Rate limits are assuming tier 2 API access for both OpenAI and Anthropic
model_data = {
    LLM.SONNET_3_5.value: {
        "provider": "anthropic",
        "max_output_tokens": 200000,
        "requests_per_minute": 1000,
        "input_tokens_per_minute": 80000,
        "output_tokens_per_minute": 16000
    },
    LLM.HAIKU_3_5.value: {
        "provider": "anthropic",
        "max_output_tokens": 200000,
        "requests_per_minute": 1000,
        "input_tokens_per_minute": 100000,
        "output_tokens_per_minute": 20000
    },
    LLM.GPT_4O.value: {
        "provider": "openai",
        "max_output_tokens": 16384,
        "requests_per_minute": 5000,
        "total_tokens_per_minute": 450000
    },
    LLM.GPT_4O_MINI.value: {
        "provider": "openai",
        "max_output_tokens": 16384,
        "requests_per_minute": 5000,
        "total_tokens_per_minute": 2000000
    },
    LLM.O1_PREVIEW.value: {
        "provider": "openai",
        "max_output_tokens": 16384,
        "requests_per_minute": 5000,
        "total_tokens_per_minute": 450000
    }
}

MAX_LOOP_ITERATIONS = 5