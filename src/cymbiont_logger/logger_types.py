from enum import IntEnum
import logging


class LogLevel(IntEnum):
    """Log levels for the Cymbiont logger."""
    BENCHMARK = logging.INFO + 5
    PROMPT = logging.INFO + 6
    RESPONSE = logging.INFO + 7
    SHELL = logging.INFO + 8
    TOOL = logging.INFO + 9
    CHAT_RESPONSE = logging.INFO + 4  # For chat responses from agents
    BASH = logging.INFO + 3  # For bash command output with original formatting
    @property
    def name(self) -> str:
        return self._name_