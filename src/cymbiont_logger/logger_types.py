from enum import IntEnum
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