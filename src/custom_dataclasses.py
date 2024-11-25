import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Dict, Literal, Optional, NamedTuple, Tuple
from pathlib import Path
from process_log import ProcessLog


MessageRole = Literal["user", "assistant", "system"]

@dataclass
class ChatMessage:
    role: MessageRole
    content: str
    name: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

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
    max_completion_tokens: Optional[int] = None

@dataclass
class TokenUsage:
    tokens: int
    timestamp: float
