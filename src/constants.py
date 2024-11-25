from enum import IntEnum
import logging

class LogLevel(IntEnum):
    BENCHMARK = logging.INFO + 5
    PROMPT = logging.INFO + 6
    RESPONSE = logging.INFO + 7
    SHELL = logging.INFO + 8

    @property
    def name(self) -> str:
        return self._name_

# Models
TAG_EXTRACTION_OPENAI_MODEL = "gpt-4o-mini"
CHAT_AGENT_MODEL = "gpt-4o-mini"
PROGRESSIVE_SUMMARY_MODEL = "gpt-4o-mini"