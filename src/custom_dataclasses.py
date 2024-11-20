import asyncio
from dataclasses import dataclass
from typing import Any, List, Dict, Optional, NamedTuple, Set
from pathlib import Path


@dataclass
class Document:
    """Represents a processed document"""
    doc_id: str
    filename: str
    processed_at: float
    metadata: Dict
    tags: Optional[List[str]] = None

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
    messages: List[Dict[str, Any]]
    response_format: Dict[str, str]
    future: asyncio.Future
    timestamp: float
    mock: bool = False
    mock_tokens: Optional[int] = None
    expiration_counter: int = 0

@dataclass
class TokenUsage:
    tokens: int
    timestamp: float