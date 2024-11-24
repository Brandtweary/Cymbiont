import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Dict, Literal, Optional, NamedTuple, Tuple
from pathlib import Path
import logging
from constants import BENCHMARK, PROMPT, RESPONSE


MessageRole = Literal["user", "assistant", "system"]

@dataclass
class ChatMessage:
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class ChatHistory:
    messages: List[ChatMessage] = field(default_factory=list)
    
    def add_message(self, role: MessageRole, content: str) -> None:
        self.messages.append(ChatMessage(role=role, content=content))
    
    def get_recent_messages(self, limit: int = 10) -> List[ChatMessage]:
        """Get the most recent messages"""
        return self.messages[-limit:]

@dataclass
class Document:
    """Represents a processed document"""
    doc_id: str
    filename: str
    processed_at: float
    metadata: Dict
    tags: Optional[List[str]] = None
    folder_id: Optional[str] = None

@dataclass
class Chunk:
    """A chunk of text with references"""
    chunk_id: str
    doc_id: str
    text: str
    position: int
    metadata: Dict
    tags: Optional[List[str]] = None

class Paths(NamedTuple):
    """Paths for data storage"""
    base_dir: Path
    docs_dir: Path
    processed_dir: Path
    chunks_dir: Path
    index_dir: Path
    logs_dir: Path
    inert_docs_dir: Path
    snapshots_dir: Path

class ProcessLog:
    """Collects logs for a specific process/task"""
    def __init__(self, name: str, logger: logging.Logger):
        self.name = name
        self.logger = logger
        self.messages: List[Tuple[int, str]] = []
    
    def debug(self, message: str) -> None:
        self.messages.append((logging.DEBUG, message))
    
    def info(self, message: str) -> None:
        self.messages.append((logging.INFO, message))
        
    def warning(self, message: str) -> None:
        self.messages.append((logging.WARNING, message))
        
    def error(self, message: str) -> None:
        self.messages.append((logging.ERROR, message))
        
    def benchmark(self, message: str) -> None:
        self.messages.append((BENCHMARK, message))
        
    def prompt(self, message: str) -> None:
        self.messages.append((PROMPT, message))
        
    def response(self, message: str) -> None:
        self.messages.append((RESPONSE, message))
    
    def add_to_logger(self) -> None:
        """Add all collected messages to the main logger"""
        # Print header
        self.logger.info(f"{'='*10} Process: {self.name} {'='*10}")
        
        # Print messages in sequence
        for level, message in self.messages:
            self.logger.log(level, f"  {message}")
        
        # Print footer
        self.logger.info(f"{'='*10} END {'='*10}")

@dataclass
class APICall:
    model: str
    messages: List[ChatMessage]
    response_format: Dict[str, str]
    timestamp: float
    mock: bool
    mock_tokens: Optional[int]
    expiration_counter: int
    future: asyncio.Future[Dict[str, Any]]
    temperature: float = 0.7
    process_log: Optional[ProcessLog] = None

@dataclass
class TokenUsage:
    tokens: int
    timestamp: float
