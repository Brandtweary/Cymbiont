from dataclasses import dataclass, asdict, field
from pathlib import Path
import json
import shutil
from typing import List, Dict, Optional, NamedTuple
import time
import re
import asyncio
from shared_resources import logger, FILE_RESET
from triple_extraction import process_chunk
from utils import log_performance, generate_id, load_index, save_index


NER_OPENAI_MODEL = "gpt-4o-mini"

# Data structures
@dataclass
class Document:
    """Represents a processed document"""
    doc_id: str          # Unique identifier
    filename: str        # Original filename
    processed_at: float  # Unix timestamp
    metadata: Dict       # Any additional metadata
    named_entities: List[str] = field(default_factory=list)

@dataclass
class Chunk:
    """A chunk of text with references"""
    chunk_id: str        # Unique identifier
    doc_id: str         # Reference to parent document
    text: str           # Actual content
    position: int       # Order in document
    metadata: Dict      # Any additional metadata
    named_entities: Optional[List[str]] = None
    triple_ids: Optional[List[str]] = None

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
    logs_dir: Path
    inert_docs_dir: Path

# Add at top with other globals
_DIRS_INITIALIZED: bool = False
_PATHS: Optional[Paths] = None

# Utility functions
def setup_directories(base_dir: Path) -> Paths:
    """Create directory structure and return paths"""
    paths = Paths(
        base_dir=base_dir,
        docs_dir=base_dir / "input_documents",
        processed_dir=base_dir / "processed_documents",
        chunks_dir=base_dir / "chunks",
        triples_dir=base_dir / "triples",
        index_dir=base_dir / "indexes",
        logs_dir=base_dir / "logs",
        inert_docs_dir=base_dir / "inert_documents"
    )
    
    for dir_path in paths:
        dir_path.mkdir(parents=True, exist_ok=True)
        
    return paths

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
        
        # Update chunk index with all fields
        chunk_index[chunk.chunk_id] = {
            "doc_id": chunk.doc_id,
            "position": chunk.position,
            "metadata": chunk.metadata,
            "named_entities": chunk.named_entities or [],
            "triple_ids": chunk.triple_ids or []
        }
    
    save_index(chunk_index, paths.index_dir / "chunks.json")

async def get_triples(chunks: List[Chunk], base_dir: Path) -> List[Triple]:
    """Extract triples from text chunks using NER + OpenIE pipeline."""
    paths = get_paths(base_dir)
    # Process all chunks concurrently
    results = await asyncio.gather(
        *[process_chunk(chunk, paths) for chunk in chunks]
    )
    
    # Filter out None results and flatten
    all_triples = [
        triple 
        for result in results 
        if result is not None 
        for triple in result
    ]
    
    # Save triples using existing function
    save_triples(all_triples, base_dir)
    
    return all_triples

def get_paths(base_dir: Path) -> Paths:
    """Get or initialize directory paths"""
    global _DIRS_INITIALIZED, _PATHS
    
    if not _DIRS_INITIALIZED:
        _PATHS = setup_directories(base_dir)
        _DIRS_INITIALIZED = True
    
    assert _PATHS is not None  # Tell type checker _PATHS is initialized
    return _PATHS

def save_triples(triples: List[Triple], base_dir: Path) -> None:
    """Store triples from OpenIE"""
    paths = get_paths(base_dir)
    triple_index = load_index(paths.index_dir / "triples.json")
    
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

def clear_indices(paths: Paths) -> None:
    """Clear all index files when in debug mode"""
    index_files = [
        paths.index_dir / "documents.json",
        paths.index_dir / "chunks.json",
        paths.index_dir / "triples.json"
    ]
    for index_file in index_files:
        save_index({}, index_file)

def move_processed_to_documents(paths: Paths) -> None:
    """Move processed files back to documents directory in debug mode"""
    for file_path in paths.processed_dir.glob("*.*"):
        if file_path.suffix.lower() in ['.txt', '.md']:
            try:
                shutil.move(str(file_path), str(paths.docs_dir / file_path.name))
                logger.debug(f"Moved {file_path.name} back to documents directory")
            except Exception as e:
                logger.error(f"Failed to move {file_path.name}: {str(e)}")

def clean_directories(paths: Paths) -> None:
    """Remove all files from triples and chunks directories"""
    # Clean triples directory
    for triple_file in paths.triples_dir.glob("*.json"):
        triple_file.unlink()
    
    # Clean chunks directory
    for chunk_file in paths.chunks_dir.glob("*.txt"):
        chunk_file.unlink()

def reset_files(paths: Paths) -> None:
    """Clear indices, move processed documents back, and clean generated files"""
    clear_indices(paths)
    move_processed_to_documents(paths)
    clean_directories(paths)

@log_performance
def process_documents(base_dir: Path) -> List[Chunk]:
    """Main document processing pipeline"""
    paths = get_paths(base_dir)
    
    logger.info("Starting document processing pipeline")
    
    if FILE_RESET:
        logger.info("File reset mode on: processed documents will be re-processed")
        reset_files(paths)
        
    # Load indices
    doc_index = load_index(paths.index_dir / "documents.json")
    chunk_index = load_index(paths.index_dir / "chunks.json")
    
    # Find documents to process
    unprocessed = find_unprocessed_documents(paths)
    logger.info(f"Found {len(unprocessed)} documents to process")
    
    if not unprocessed:
        logger.warning("No documents to process")
        return []
    
    # Process each document
    all_chunks = []
    for filepath in unprocessed:
        logger.info(f"Processing {filepath.name}")
        doc, chunks = process_document(filepath, paths, doc_index)
        all_chunks.extend(chunks)
    
    # Extract triples if chunks were processed
    if all_chunks:
        logger.debug(f"Extracting triples from {len(all_chunks)} chunks")
        asyncio.run(get_triples(all_chunks, base_dir))
        
        # Save chunks after all processing is complete
        save_chunks(all_chunks, paths, chunk_index)
        
    logger.info(f"Processing complete - {len(all_chunks)} chunks processed")
    return all_chunks

# Retrieval functions (for when OpenIE needs them)
def get_chunk(chunk_id: str, paths: Paths, chunk_index: Dict) -> Optional[Chunk]:
    """Retrieve a chunk by ID"""
    if chunk_id in chunk_index:
        chunk_file = paths.chunks_dir / f"{chunk_id}.txt"
        if chunk_file.exists():
            index_data = chunk_index[chunk_id]
            return Chunk(
                chunk_id=chunk_id,
                text=chunk_file.read_text(),
                doc_id=index_data["doc_id"],
                position=index_data["position"],
                metadata=index_data["metadata"],
                named_entities=index_data.get("named_entities"),
                triple_ids=index_data.get("triple_ids")
            )
    return None
