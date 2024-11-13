from dataclasses import dataclass, field
from typing import List, Dict, Optional, NamedTuple
from pathlib import Path


@dataclass
class Document:
    """Represents a processed document"""
    doc_id: str
    filename: str
    processed_at: float
    metadata: Dict
    named_entities: List[str] = field(default_factory=list)

@dataclass
class Chunk:
    """A chunk of text with references"""
    chunk_id: str
    doc_id: str
    text: str
    position: int
    metadata: Dict
    named_entities: Optional[List[str]] = None
    triple_ids: Optional[List[str]] = None

@dataclass
class Triple:
    """An RDF triple with provenance"""
    triple_id: str
    chunk_id: str
    doc_id: str
    head: str
    relation: str
    tail: str
    metadata: Dict

class Paths(NamedTuple):
    """Paths for data storage"""
    base_dir: Path
    docs_dir: Path
    processed_dir: Path
    chunks_dir: Path
    triples_dir: Path
    index_dir: Path
    logs_dir: Path
    inert_docs_dir: Path