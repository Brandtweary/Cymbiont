from dataclasses import asdict
from pathlib import Path
import shutil
from typing import List, Dict, Optional
import time
import asyncio
from shared_resources import logger, FILE_RESET, DATA_DIR, Paths
from .tag_extraction import extract_tags
from utils import log_performance, generate_id, load_index, save_index, get_paths
from .knowledge_graph_types import Document, Chunk
from cymbiont_logger.process_log import ProcessLog
from knowledge_graph.text_parser import split_into_chunks


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
            # Process folder contents
            results = parse_document_folder(filepath, paths, doc_index, folder_index)
            for _, chunks in results:
                all_chunks.extend(chunks)
            # Move folder after processing
            relative_path = filepath.relative_to(paths.docs_dir)
            dest_path = paths.processed_dir / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(filepath), str(dest_path))
        else:
            # Process and move single document
            doc, chunks = parse_document(filepath, paths, doc_index)
            all_chunks.extend(chunks)
            shutil.move(str(filepath), str(paths.processed_dir / filepath.name))
    else:
        # Process all unprocessed folders first
        folders = find_unprocessed_doc_folders(paths)
        for folder in folders:
            logger.info(f"Processing folder: {folder.name}")
            results = parse_document_folder(folder, paths, doc_index, folder_index)
            for _, chunks in results:
                all_chunks.extend(chunks)
            # Move folder after processing
            relative_path = folder.relative_to(paths.docs_dir)
            dest_path = paths.processed_dir / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(folder), str(dest_path))
        
        # Then process and move remaining individual documents
        individual_docs = find_unprocessed_documents(paths)
        for filepath in individual_docs:
            logger.info(f"Processing document: {filepath.name}")
            doc, chunks = parse_document(filepath, paths, doc_index)
            all_chunks.extend(chunks)
            shutil.move(str(filepath), str(paths.processed_dir / filepath.name))
    
    if not all_chunks:
        logger.warning("No chunks were created from any documents")
    
    return all_chunks

async def process_chunk_tags(
    chunks: List[Chunk], 
    doc_index: Dict,
    mock: bool = False,
    mock_content: str = ""
) -> set:
    """Process and aggregate tags for all chunks and their documents."""
    chunk_logs = [ProcessLog(f"Chunk {chunk.chunk_id}", logger) for chunk in chunks]
    tasks = [
        asyncio.create_task(
            extract_tags(chunk, process_log, mock, mock_content),
            name=f"extract_tags_{chunk.chunk_id}"
        )
        for chunk, process_log in zip(chunks, chunk_logs)
    ]
    
    await asyncio.gather(*tasks, return_exceptions=True)
    
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
        log.add_to_logger()
        
    return all_unique_tags

@log_performance
async def process_documents(
    base_dir: Path, 
    doc_name: str | None = None,
    mock: bool = False,
    mock_content: str = ""
) -> List[Chunk]:
    """Main document processing pipeline."""
    try:
        paths = get_paths(base_dir)
        logger.info("Starting document processing pipeline")
        
        # Load indices
        doc_index = load_index(paths.index_dir / "documents.json")
        chunk_index = load_index(paths.index_dir / "chunks.json")

        # Get chunks from documents
        all_chunks = await get_processed_chunks(paths, doc_index, doc_name)
        if not all_chunks:
            return []

        # Get tags
        all_unique_tags = await process_chunk_tags(all_chunks, doc_index, mock, mock_content)

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

async def create_data_snapshot(
    name: str, 
    doc_name: str | None = None,
    mock: bool = False,
    mock_content: str = ""
) -> Path:
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
            
        await process_documents(snapshot_base, doc_name, mock, mock_content)
        return snapshot_base
        
    except Exception as e:
        logger.error(f"Failed to create snapshot '{name}': {str(e)}")
        raise

def find_unprocessed_doc_folders(paths: Paths) -> List[Path]:
    """Find all unprocessed document folders in the docs directory"""
    return [p for p in paths.docs_dir.glob("*") if p.is_dir()]

def parse_document_folder(folder_path: Path, paths: Paths, doc_index: Dict, folder_index: Dict, parent_id: Optional[str] = None) -> List[tuple[Document, List[Chunk]]]:
    """Parse all documents in a folder and its subfolders."""
    folder_id = generate_id(folder_path.name)
    results: List[tuple[Document, List[Chunk]]] = []
    
    # Create/update folder index entry with parent relationship
    folder_index[folder_id] = {
        "folder_name": folder_path.name,
        "processed_at": time.time(),
        "metadata": {},
        "parent_folder_id": parent_id
    }
    
    # Process each item in the folder
    for filepath in folder_path.iterdir():
        if filepath.is_dir():
            subfolder_results = parse_document_folder(
                filepath, paths, doc_index, folder_index, parent_id=folder_id
            )
            results.extend(subfolder_results)
        elif filepath.suffix.lower() in ['.txt', '.md']:
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
    
    save_index(folder_index, paths.index_dir / "folders.json")
    save_index(doc_index, paths.index_dir / "documents.json")
    
    return results