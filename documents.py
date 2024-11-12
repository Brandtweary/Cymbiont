from dataclasses import dataclass, asdict
from pathlib import Path
import json
import shutil
import hashlib
from typing import List, Dict, Optional, NamedTuple
import time
import re

# Data structures
@dataclass
class Document:
    """Represents a processed document"""
    doc_id: str          # Unique identifier
    filename: str        # Original filename
    processed_at: float  # Unix timestamp
    metadata: Dict       # Any additional metadata

@dataclass
class Chunk:
    """A chunk of text with references"""
    chunk_id: str        # Unique identifier
    doc_id: str         # Reference to parent document
    text: str           # Actual content
    position: int       # Order in document
    metadata: Dict      # Any additional metadata

@dataclass
class Triple:
    """An RDF triple with provenance"""
    triple_id: str      # Unique identifier
    chunk_id: str       # Reference to source chunk
    doc_id: str         # Reference to source document
    head: str
    relation: str
    tail: str
    metadata: Dict      # Any additional metadata

class Paths(NamedTuple):
    """Paths for data storage"""
    base_dir: Path
    docs_dir: Path
    processed_dir: Path
    chunks_dir: Path
    triples_dir: Path
    index_dir: Path

# Utility functions
def setup_directories(base_dir: Path) -> Paths:
    """Create directory structure and return paths"""
    paths = Paths(
        base_dir=base_dir,
        docs_dir=base_dir / "documents",
        processed_dir=base_dir / "processed",
        chunks_dir=base_dir / "chunks",
        triples_dir=base_dir / "triples",
        index_dir=base_dir / "indexes"
    )
    
    for dir_path in paths:
        dir_path.mkdir(parents=True, exist_ok=True)
        
    return paths

def generate_id(content: str) -> str:
    """Generate a stable ID from content"""
    return hashlib.sha256(content.encode()).hexdigest()[:12]

# Index management
def load_index(index_path: Path) -> Dict:
    """Load an index file or create if doesn't exist"""
    if index_path.exists():
        return json.loads(index_path.read_text())
    return {}

def save_index(data: Dict, index_path: Path):
    """Save an index to disk"""
    index_path.write_text(json.dumps(data, indent=2))

# Document processing
def find_unprocessed_documents(paths: Paths) -> List[Path]:
    """Find all unprocessed documents in the docs directory"""
    return list(paths.docs_dir.glob("*.txt")) + list(paths.docs_dir.glob("*.md"))

def split_into_chunks(text: str, doc_id: str) -> List[Chunk]:
    """Split document text into chunks based on paragraphs"""
    # Split on blank lines and filter empty chunks
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    
    return [
        Chunk(
            chunk_id=f"{doc_id}-{i}",
            doc_id=doc_id,
            text=para,
            position=i,
            metadata={}
        )
        for i, para in enumerate(paragraphs)
    ]

def process_document(filepath: Path, paths: Paths, doc_index: Dict) -> tuple[Document, List[Chunk]]:
    """Process a single document into chunks"""
    # Validate file extension
    if filepath.suffix.lower() not in ['.txt', '.md']:
        raise ValueError(f"Unsupported file type: {filepath.suffix}. Only .txt and .md files are supported.")
    
    # Read and generate IDs
    content = filepath.read_text()
    doc_id = generate_id(content)
    timestamp = time.time()
    
    # Create document record
    doc = Document(
        doc_id=doc_id,
        filename=filepath.name,
        processed_at=timestamp,
        metadata={}
    )
    
    # Split into chunks
    chunks = split_into_chunks(content, doc_id)
    
    # Move original file to processed directory
    shutil.move(str(filepath), str(paths.processed_dir / filepath.name))
    
    # Update document index
    doc_index[doc_id] = asdict(doc)
    save_index(doc_index, paths.index_dir / "documents.json")
    
    return doc, chunks

def save_chunks(chunks: List[Chunk], paths: Paths, chunk_index: Dict):
    """Save chunks to disk and update index"""
    for chunk in chunks:
        # Save chunk content
        chunk_file = paths.chunks_dir / f"{chunk.chunk_id}.txt"
        chunk_file.write_text(chunk.text)
        
        # Update chunk index
        chunk_index[chunk.chunk_id] = {
            "doc_id": chunk.doc_id,
            "position": chunk.position,
            "metadata": chunk.metadata
        }
    
    save_index(chunk_index, paths.index_dir / "chunks.json")

def process_documents(base_dir: Path) -> List[Chunk]:
    """Main document processing pipeline"""
    # Setup
    paths = setup_directories(base_dir)
    doc_index = load_index(paths.index_dir / "documents.json")
    chunk_index = load_index(paths.index_dir / "chunks.json")
    
    # Find documents to process
    unprocessed = find_unprocessed_documents(paths)
    if not unprocessed:
        print("No documents to process")
        return []
    
    # Process each document
    all_chunks = []
    for filepath in unprocessed:
        print(f"Processing {filepath.name}...")
        doc, chunks = process_document(filepath, paths, doc_index)
        save_chunks(chunks, paths, chunk_index)
        all_chunks.extend(chunks)
        
    return all_chunks

# Retrieval functions (for when OpenIE needs them)
def get_chunk(chunk_id: str, paths: Paths, chunk_index: Dict) -> Optional[Chunk]:
    """Retrieve a chunk by ID"""
    if chunk_id in chunk_index:
        chunk_file = paths.chunks_dir / f"{chunk_id}.txt"
        if chunk_file.exists():
            return Chunk(
                chunk_id=chunk_id,
                text=chunk_file.read_text(),
                **chunk_index[chunk_id]
            )
    return None

def save_triples(triples: List[Triple], paths: Paths, triple_index: Dict):
    """Store triples from OpenIE"""
    for triple in triples:
        # Save triple
        triple_file = paths.triples_dir / f"{triple.triple_id}.json"
        triple_file.write_text(json.dumps(asdict(triple), indent=2))
        
        # Update triple index
        triple_index[triple.triple_id] = {
            "chunk_id": triple.chunk_id,
            "doc_id": triple.doc_id,
            "metadata": triple.metadata
        }
    save_index(triple_index, paths.index_dir / "triples.json")
