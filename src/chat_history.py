from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, List, Set
import asyncio
import logging
import re
from api_queue import enqueue_api_call
from constants import PROGRESSIVE_SUMMARY_MODEL, LogLevel
from prompts import PROGRESSIVE_SUMMARY_PROMPT
from utils import convert_messages_to_string
from custom_dataclasses import ChatMessage, MessageRole


@dataclass
class ChatHistory:
    def __init__(self) -> None:
        from shared_resources import logger  # avoiding a circular import
        self.logger = logger
        self.all_messages: List[ChatMessage] = []
        self.buffer_messages: List[ChatMessage] = []
        self.message_word_limit: int = 300
        self.buffer_word_limit: int = 3000
        self.keep_words_limit: int = 1000
        self.progressive_summary: Optional[str] = None
        self._pending_summaries: Set[asyncio.Task] = set()
        self.is_summarizing: bool = False
        self.mock: bool = False
        self.progressive_summary_token_limit: int = 1000
    
    def truncate_message(self, text: str, limit: Optional[int]) -> str:
        if not limit:
            return text
        words = text.split()
        return ' '.join(words[:limit]) + ('...' if len(words) > limit else '')

    def calculate_word_count(self, messages: List[ChatMessage], truncate: bool = True) -> int:
        """Calculate total word count of messages, optionally applying truncation"""
        total = 0
        for i, msg in enumerate(messages):
            # Only truncate if requested and not the last message
            should_truncate = truncate and i < len(messages) - 1
            content = self.truncate_message(msg.content, self.message_word_limit) if should_truncate else msg.content
            total += len(content.split())
        return total

    def get_new_buffer_messages(self, new_message: ChatMessage) -> List[ChatMessage]:
        """Calculate which messages should remain in buffer after adding new message"""
        # Start with just the new message (untruncated)
        new_buffer_words = len(new_message.content.split())
        new_buffer = [new_message]
        
        # Add recent messages until we approach keep_words_limit
        for msg in reversed(self.buffer_messages):
            msg_words = len(self.truncate_message(msg.content, self.message_word_limit).split())
            if new_buffer_words + msg_words > self.keep_words_limit:
                break
            new_buffer.insert(0, msg)
            new_buffer_words += msg_words
            
        return new_buffer

    def add_message(self, role: MessageRole, content: str, name: str = '') -> None:
        """Add a message to the history with an explicit name"""
        new_message = ChatMessage(role=role, content=content, name=name)
        self.all_messages.append(new_message)
        
        # Calculate new buffer size including the new message
        potential_buffer = self.buffer_messages + [new_message]
        total_words = self.calculate_word_count(potential_buffer)
        
        if total_words > self.buffer_word_limit:
            # Calculate new buffer once
            new_buffer = self.get_new_buffer_messages(new_message)
            
            # Need to summarize older messages
            messages_to_summarize = self.buffer_messages  # Summarize all current buffer messages
            if messages_to_summarize:
                # Spawn background task for summarization
                self.is_summarizing = True
                task = asyncio.create_task(self._background_summarize(messages_to_summarize))
                self._pending_summaries.add(task)
                task.add_done_callback(self._pending_summaries.discard)
                        
            # Update buffer with recent messages only
            self.buffer_messages = new_buffer
        else:
            self.buffer_messages = potential_buffer

    async def wait_for_summary(self) -> None:
        """Wait for any ongoing summarization to complete"""
        while self.is_summarizing:
            await asyncio.sleep(0.1)

    async def _background_summarize(self, messages: List[ChatMessage]) -> None:
        """Background task to handle progressive summarization"""
        try:
            self.progressive_summary = await self.create_progressive_summary(messages)
        except Exception as e:
            self.logger.error(f"Progressive summarization failed: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            self.is_summarizing = False

    async def create_progressive_summary(self, messages: List[ChatMessage]) -> str:
        """Create a summary of the specified messages, including previous summary context"""
        conversation_parts = []
        
        # Include previous summary if it exists
        if self.progressive_summary:
            conversation_parts.append(f"Previous summary: {self.progressive_summary}")
        
        # Add messages to be summarized
        conversation = convert_messages_to_string(
            messages,
            word_limit=self.message_word_limit,
            truncate_last=True
        )
        conversation_parts.append(conversation)
        
        full_conversation = "\n\n".join(conversation_parts)
        
        messages = [
            ChatMessage(
                role="system",
                content=PROGRESSIVE_SUMMARY_PROMPT.format(conversation=full_conversation)
            )
        ]
        
        response = await enqueue_api_call(
            model=PROGRESSIVE_SUMMARY_MODEL,
            messages=messages,
            response_format={"type": "text"},
            temperature=0.3,
            max_completion_tokens=self.progressive_summary_token_limit,
            mock=self.mock
        )
        
        return response["content"]

    def get_recent_messages(self) -> tuple[List[ChatMessage], Optional[str]]:
        """Get recent messages and progressive summary if available
        
        Returns:
            Tuple of (buffer messages, formatted summary string if available)
        """
        # Add buffer messages with truncation (except last)
        messages = []
        for i, msg in enumerate(self.buffer_messages):
            content = msg.content
            if i < len(self.buffer_messages) - 1:  # Truncate all except last message
                content = self.truncate_message(content, self.message_word_limit)
            messages.append(ChatMessage(
                role=msg.role,
                content=content,
                name=msg.name
            ))
        
        # Format summary if available
        formatted_summary = None
        if self.progressive_summary:
            formatted_summary = f"Previous conversation context: {self.progressive_summary}"
        
        return messages, formatted_summary

class ChatHistoryHandler(logging.Handler):
    """Handler that adds log messages to chat history"""
    def __init__(
        self, 
        chat_history: Optional[ChatHistory] = None,
        console_filter: Optional[logging.Filter] = None
    ):
        super().__init__()
        self.chat_history = chat_history
        self.console_filter = console_filter
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def emit(self, record: logging.LogRecord) -> None:
        if (self.chat_history is not None 
            and record.levelno not in (LogLevel.PROMPT, LogLevel.RESPONSE)
            and (record.levelno == LogLevel.SHELL  # Always include SHELL messages
                or (self.console_filter is None or self.console_filter.filter(record)))
        ):
            clean_message = self.ansi_escape.sub('', self.format(record))
            prefixed_message = f"{record.levelname} - {clean_message}"
            self.chat_history.add_message("system", prefixed_message)

def setup_chat_history_handler(logger: logging.Logger, chat_history: ChatHistory, console_filter: Optional[logging.Filter] = None) -> None:
    """Set up chat history handler for logger"""
    handler = ChatHistoryHandler(chat_history, console_filter)
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)