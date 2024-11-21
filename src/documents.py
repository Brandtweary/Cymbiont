from dataclasses import asdict
from pathlib import Path
import shutil
from typing import List, Dict, Optional
import time
import asyncio
from shared_resources import logger, FILE_RESET, DATA_DIR
from tag_extraction import extract_tags
from utils import log_performance, generate_id, load_index, save_index, get_paths
from custom_dataclasses import Document, Chunk, Paths
from logging_config import ProcessLog
from text_parser import split_into_chunks


# Document processing
def find_unprocessed_documents(paths: Paths) -> List[Path]:
    """Find all unprocessed documents in the docs directory"""
    return list(paths.docs_dir.glob("*.txt")) + list(paths.docs_dir.glob("*.md"))

def parse_document(filepath: Path, paths: Paths, doc_index: Dict) -> tuple[Document, List[Chunk]]:
    """Parse a document into chunks and update the document index."""
    # Validate file extension
    if filepath.suffix.lower() not in ['.txt', '.md']:
        raise ValueError(f"Unsupported file type: {filepath.suffix}. Only .txt and .md files are supported.")
    
    # Read and generate IDs
    content = filepath.read_text()
    doc_id = generate_id(content)
    timestamp = time.time()
    
    # Create document record with empty tags initially
    doc = Document(
        doc_id=doc_id,
        filename=filepath.name,
        processed_at=timestamp,
        metadata={},
        tags=[]
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
            "tags": chunk.tags or []
        }
    
    save_index(chunk_index, paths.index_dir / "chunks.json")

def clear_indices(paths: Paths) -> None:
    """Clear all index files when in file reset mode"""
    index_files = [
        paths.index_dir / "documents.json",
        paths.index_dir / "chunks.json"
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
    """Remove all files from chunks directory"""
    # Clean chunks directory
    for chunk_file in paths.chunks_dir.glob("*.txt"):
        chunk_file.unlink()

def reset_files(paths: Paths) -> None:
    """Clear indices, move processed documents back, and clean generated files"""
    clear_indices(paths)
    move_processed_to_documents(paths)
    clean_directories(paths)

async def get_processed_chunks(paths: Paths, doc_index: Dict) -> List[Chunk]:
    """Get chunks from all unprocessed documents."""
    unprocessed = find_unprocessed_documents(paths)
    logger.info(f"Found {len(unprocessed)} documents to process")

    if not unprocessed:
        logger.warning("No documents to process")
        return []

    all_chunks: List[Chunk] = []
    for filepath in unprocessed:
        logger.info(f"Processing {filepath.name}")
        doc, chunks = parse_document(filepath, paths, doc_index)
        if not chunks:
            logger.warning(f"No chunks were created for document {filepath.name}")
            continue
        all_chunks.extend(chunks)

    if not all_chunks:
        logger.warning("No chunks were created from any documents")
        
    return all_chunks

async def process_chunk_tags(chunks: List[Chunk], doc_index: Dict) -> set:
    """Process and aggregate tags for all chunks and their documents."""
    # Create process logs and extract tags
    chunk_logs = [ProcessLog(f"Chunk {chunk.chunk_id}") for chunk in chunks]
    tag_extraction_coros = [
        extract_tags(chunk, process_log) 
        for chunk, process_log in zip(chunks, chunk_logs)
    ]
    
    # Extract tags from all chunks concurrently
    await asyncio.gather(*tag_extraction_coros, return_exceptions=True)
    
    # Aggregate tags by document using sets temporarily for deduplication
    doc_tags = {}
    all_unique_tags = set()
    for chunk in chunks:
        if chunk.tags:
            if chunk.doc_id not in doc_tags:
                doc_tags[chunk.doc_id] = set()
            doc_tags[chunk.doc_id].update(chunk.tags)
            all_unique_tags.update(chunk.tags)
    
    # Update document index with aggregated tags as lists
    for doc_id, tags in doc_tags.items():
        if doc_id in doc_index:
            doc_index[doc_id]["tags"] = list(tags)  # Convert set to list before storing

    # Add all logs to the logger
    for log in chunk_logs:
        log.add_to_logger(logger)
        
    return all_unique_tags

@log_performance
async def process_documents(base_dir: Path) -> List[Chunk]:
    """Main document processing pipeline."""
    try:
        paths = get_paths(base_dir)
        logger.info("Starting document processing pipeline")
        
        if FILE_RESET:
            logger.info("File reset mode on: processed documents will be re-processed")
            reset_files(paths)

        # Load indices
        doc_index = load_index(paths.index_dir / "documents.json")
        chunk_index = load_index(paths.index_dir / "chunks.json")

        # Get chunks from documents
        all_chunks = await get_processed_chunks(paths, doc_index)
        if not all_chunks:
            return []

        # Process tags
        all_unique_tags = await process_chunk_tags(all_chunks, doc_index)

        # Save final state
        save_index(doc_index, paths.index_dir / "documents.json")
        save_chunks(all_chunks, paths, chunk_index)
        
        logger.info(f"Processing complete - {len(all_chunks)} chunks from {len(set(c.doc_id for c in all_chunks))} documents, {len(all_unique_tags)} unique tags")
        return all_chunks

    except Exception as e:
        logger.error(f"Document processing pipeline failed: {str(e)}")
        raise

# Retrieval functions
def get_chunk(chunk_id: str, paths: Paths, chunk_index: Dict) -> Optional[Chunk]:  # not used yet
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
                tags=index_data.get("tags")
            )
    return None

async def create_data_snapshot(name: str) -> Path:
    """
    Create a snapshot of the current data directory structure.
    Returns the path to the new snapshot directory.
    """
    try:
        # Get existing paths
        paths = get_paths(DATA_DIR)
        
        # Create snapshot directory
        snapshot_base = paths.snapshots_dir / f"{name}_snapshot"
        
        # Set up directories in snapshot
        snapshot_paths = Paths(
            base_dir=snapshot_base,
            docs_dir=snapshot_base / "input_documents",
            processed_dir=snapshot_base / "processed_documents",
            chunks_dir=snapshot_base / "chunks",
            index_dir=snapshot_base / "indexes",
            logs_dir=snapshot_base / "logs",  # This won't be used
            inert_docs_dir=snapshot_base / "inert_documents",
            snapshots_dir=snapshot_base / "snapshots"  # This won't be used
        )
        
        # Create all directories except snapshots and logs
        for dir_path in [p for p in snapshot_paths if p not in {snapshot_paths.snapshots_dir, snapshot_paths.logs_dir}]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Copy input documents to snapshot's input directory
        for src_path in paths.docs_dir.glob("*.*"):
            if src_path.suffix.lower() in ['.txt', '.md']:
                shutil.copy2(src_path, snapshot_paths.docs_dir)
            
        # Process documents in the snapshot directory
        await process_documents(snapshot_base)
        
        return snapshot_base
        
    except Exception as e:
        logger.error(f"Failed to create snapshot '{name}': {str(e)}")
        raise