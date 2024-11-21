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
        paths.index_dir / "chunks.json",
        paths.index_dir / "folders.json"  # Add folders index
    ]
    for index_file in index_files:
        save_index({}, index_file)

def move_processed_to_documents(paths: Paths) -> None:
    """Move processed files and folders back to documents directory in debug mode"""
    # Handle individual files
    for file_path in paths.processed_dir.glob("*.*"):
        if file_path.suffix.lower() in ['.txt', '.md']:
            try:
                shutil.move(str(file_path), str(paths.docs_dir / file_path.name))
                logger.debug(f"Moved file {file_path.name} back to documents directory")
            except Exception as e:
                logger.error(f"Failed to move file {file_path.name}: {str(e)}")
    
    # Handle folders
    for folder_path in paths.processed_dir.glob("*"):
        if folder_path.is_dir():
            try:
                # Move entire folder back to documents directory
                shutil.move(str(folder_path), str(paths.docs_dir / folder_path.name))
                logger.debug(f"Moved folder {folder_path.name} back to documents directory")
            except Exception as e:
                logger.error(f"Failed to move folder {folder_path.name}: {str(e)}")

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

async def get_processed_chunks(paths: Paths, doc_index: Dict, doc_name: str | None = None) -> List[Chunk]:
    """Process both individual documents and document folders."""
    all_chunks: List[Chunk] = []
    folder_index = load_index(paths.index_dir / "folders.json")
    
    if doc_name:
        filepath = paths.docs_dir / doc_name
        if not filepath.exists():
            logger.error(f"Document not found: {doc_name}")
            return []
        
        if filepath.is_dir():
            # Process as folder
            results = parse_document_folder(filepath, paths, doc_index, folder_index)
            for _, chunks in results:
                all_chunks.extend(chunks)
        else:
            # Process as single document
            doc, chunks = parse_document(filepath, paths, doc_index)
            all_chunks.extend(chunks)
    else:
        # Process all unprocessed folders first
        folders = find_unprocessed_doc_folders(paths)
        for folder in folders:
            logger.info(f"Processing folder: {folder.name}")
            results = parse_document_folder(folder, paths, doc_index, folder_index)
            for _, chunks in results:
                all_chunks.extend(chunks)
        
        # Then process remaining individual documents
        individual_docs = find_unprocessed_documents(paths)
        for filepath in individual_docs:
            logger.info(f"Processing document: {filepath.name}")
            doc, chunks = parse_document(filepath, paths, doc_index)
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
async def process_documents(base_dir: Path, doc_name: str | None = None) -> List[Chunk]:
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
        all_chunks = await get_processed_chunks(paths, doc_index, doc_name)
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

async def create_data_snapshot(name: str, doc_name: str | None = None) -> Path:
    """Create a snapshot of the current data directory structure and process selected documents."""
    try:
        paths = get_paths(DATA_DIR)
        snapshot_base = paths.snapshots_dir / f"{name}_snapshot"
        
        # Set up directories in snapshot
        snapshot_paths = Paths(
            base_dir=snapshot_base,
            docs_dir=snapshot_base / "input_documents",
            processed_dir=snapshot_base / "processed_documents",
            chunks_dir=snapshot_base / "chunks",
            index_dir=snapshot_base / "indexes",
            logs_dir=snapshot_base / "logs",
            inert_docs_dir=snapshot_base / "inert_documents",
            snapshots_dir=snapshot_base / "snapshots"
        )
        
        # Create all directories except snapshots and logs
        for dir_path in [p for p in snapshot_paths if p not in {snapshot_paths.snapshots_dir, snapshot_paths.logs_dir}]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Copy input documents to snapshot's input directory
        if doc_name:
            src_path = paths.docs_dir / doc_name
            if not src_path.exists():
                raise FileNotFoundError(f"Document not found: {doc_name}")
            if src_path.is_dir():
                # Copy entire folder
                shutil.copytree(src_path, snapshot_paths.docs_dir / doc_name)
            elif src_path.suffix.lower() in ['.txt', '.md']:
                shutil.copy2(src_path, snapshot_paths.docs_dir)
        else:
            # Copy all documents and folders
            for src_path in paths.docs_dir.iterdir():
                if src_path.is_dir():
                    shutil.copytree(src_path, snapshot_paths.docs_dir / src_path.name)
                elif src_path.suffix.lower() in ['.txt', '.md']:
                    shutil.copy2(src_path, snapshot_paths.docs_dir)
            
        await process_documents(snapshot_base)
        return snapshot_base
        
    except Exception as e:
        logger.error(f"Failed to create snapshot '{name}': {str(e)}")
        raise

def find_unprocessed_doc_folders(paths: Paths) -> List[Path]:
    """Find all unprocessed document folders in the docs directory"""
    return [p for p in paths.docs_dir.glob("*") if p.is_dir()]

def parse_document_folder(folder_path: Path, paths: Paths, doc_index: Dict, folder_index: Dict) -> List[tuple[Document, List[Chunk]]]:
    """Parse all documents in a folder and prepare for moving."""
    folder_id = generate_id(folder_path.name)
    results: List[tuple[Document, List[Chunk]]] = []
    
    # Create/update folder index entry
    folder_index[folder_id] = {
        "folder_name": folder_path.name,
        "processed_at": time.time(),
        "metadata": {}
    }
    
    # Process each document in the folder
    for filepath in folder_path.glob("*"):
        if filepath.suffix.lower() not in ['.txt', '.md']:
            continue
            
        content = filepath.read_text()
        doc_id = generate_id(content)
        
        doc = Document(
            doc_id=doc_id,
            filename=filepath.name,
            processed_at=time.time(),
            metadata={},
            tags=[],
            folder_id=folder_id
        )
        
        chunks = split_into_chunks(content, doc_id)
        doc_index[doc_id] = asdict(doc)
        results.append((doc, chunks))
    
    # Move folder to processed directory
    shutil.move(str(folder_path), str(paths.processed_dir))
    
    save_index(folder_index, paths.index_dir / "folders.json")
    save_index(doc_index, paths.index_dir / "documents.json")
    
    return results