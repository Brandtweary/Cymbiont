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
    CONTEMPLATE = "contemplate"
    EXIT_LOOP = "exit_loop"
    MESSAGE_SELF = "message_self"
    EXECUTE_SHELL_COMMAND = "execute_shell_command"

class LLM(Enum):
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"
    O1_PREVIEW = "o1-preview"
    SONNET_3_5 = "claude-3-5-sonnet-latest"
    HAIKU_3_5 = "claude-3-5-haiku-latest"

# Map models to their providers
MODEL_PROVIDERS = {
    LLM.GPT_4O.value: "openai",
    LLM.GPT_4O_MINI.value: "openai",
    LLM.O1_PREVIEW.value: "openai",
    LLM.SONNET_3_5.value: "anthropic",
    LLM.HAIKU_3_5.value: "anthropic",
}