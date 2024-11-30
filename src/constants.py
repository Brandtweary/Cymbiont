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

# Models
TAG_EXTRACTION_OPENAI_MODEL = "gpt-4o-mini"
CHAT_AGENT_MODEL = "gpt-4o-mini"
PROGRESSIVE_SUMMARY_MODEL = "gpt-4o-mini"
REVISION_MODEL = "o1-preview"
