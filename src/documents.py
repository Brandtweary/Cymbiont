from dataclasses import asdict
from pathlib import Path
import json
import shutil
from typing import List, Dict, Optional
import time
import asyncio
from shared_resources import logger, FILE_RESET, DATA_DIR
from triple_extraction import process_chunk_with_ner, extract_triples_from_ner
from utils import log_performance, generate_id, load_index, save_index, setup_directories
from custom_dataclasses import Document, Chunk, Paths, Triple
from logging_config import ProcessLog
from text_parser import split_into_chunks

# Initialize the main data directory at module load
try:
    setup_directories(DATA_DIR)
except Exception as e:
    logger.error(f"Failed to initialize data directory: {str(e)}")
    raise

def get_paths(base_dir: Path) -> Paths:
    """Get directory paths for the specified base directory"""
    try:
        return Paths(
            base_dir=base_dir,
            docs_dir=base_dir / "input_documents",
            processed_dir=base_dir / "processed_documents",
            chunks_dir=base_dir / "chunks",
            triples_dir=base_dir / "triples",
            index_dir=base_dir / "indexes",
            logs_dir=base_dir / "logs",
            inert_docs_dir=base_dir / "inert_documents",
            snapshots_dir=base_dir / "snapshots"
        )
    except Exception as e:
        logger.error(f"Failed to get paths for {base_dir}: {str(e)}")
        raise

# Document processing
def find_unprocessed_documents(paths: Paths) -> List[Path]:
    """Find all unprocessed documents in the docs directory"""
    return list(paths.docs_dir.glob("*.txt")) + list(paths.docs_dir.glob("*.md"))

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

def save_triples(triples: List[Triple], base_dir: Path) -> None:
    """Store triples from OpenAI"""
    paths = get_paths(base_dir)
    triple_index = load_index(paths.index_dir / "triples.json")
    
    for triple in triples:
        # Save triple content
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

        # Find documents to process
        unprocessed = find_unprocessed_documents(paths)
        logger.info(f"Found {len(unprocessed)} documents to process")

        if not unprocessed:
            logger.warning("No documents to process")
            return []

        # Process each document into chunks
        all_chunks: List[Chunk] = []
        for filepath in unprocessed:
            logger.info(f"Processing {filepath.name}")
            doc, chunks = process_document(filepath, paths, doc_index)
            if not chunks:
                logger.warning(f"No chunks were created for document {filepath.name}")
                continue
            all_chunks.extend(chunks)

        if not all_chunks:
            logger.warning("No chunks were created from any documents")
            return []

        # Create process logs for each chunk and prepare NER coroutines
        chunk_logs = [ProcessLog(f"Chunk {chunk.chunk_id}") for chunk in all_chunks]
        named_entities_coros = [
            process_chunk_with_ner(chunk, paths, process_log) 
            for chunk, process_log in zip(all_chunks, chunk_logs)
        ]

        # Process NER on all chunks concurrently
        try:
            ner_results = await asyncio.gather(*named_entities_coros, return_exceptions=True)
            # Check for exceptions in results
            for i, result in enumerate(ner_results):
                if isinstance(result, Exception):
                    logger.error(f"Result {i} was an exception: {result}")
                    raise result
            named_entities_results, ner_logs = zip(*ner_results)
        except Exception as e:
            logger.error(f"NER processing failed: {str(e)}")
            raise

        # Prepare chunks with named entities for triple extraction
        chunks_with_entities: List[Chunk] = []
        valid_chunk_logs: List[ProcessLog] = []
        for chunk, entities, chunk_log in zip(all_chunks, named_entities_results, chunk_logs):
            if entities is not None:
                chunks_with_entities.append(chunk)
                valid_chunk_logs.append(chunk_log)

        # Extract triples from chunks concurrently
        triples_coros = [
            extract_triples_from_ner(chunk, chunk.named_entities, paths, chunk_log)
            for chunk, chunk_log in zip(chunks_with_entities, valid_chunk_logs)
        ]
        try:
            triples_results = await asyncio.gather(*triples_coros, return_exceptions=True)
            # Check for exceptions in results
            for result in triples_results:
                if isinstance(result, Exception):
                    raise result
            triples_list, triples_logs = zip(*triples_results)
        except Exception as e:
            logger.error(f"Triple extraction failed: {str(e)}")
            raise

        # Flatten triples and filter out None
        all_triples: List[Triple] = [
            triple
            for triples in triples_list
            if triples is not None
            for triple in triples
        ]

        # Save triples and chunks
        save_triples(all_triples, base_dir)
        save_chunks(all_chunks, paths, chunk_index)

        # Add all logs to the logger in order
        for log in chunk_logs:
            log.add_to_logger(logger)
        
        logger.info(f"Processing complete - {len(unprocessed)} documents, {len(all_chunks)} chunks, {len(all_triples)} triples")
        return all_chunks

    except Exception as e:
        logger.error(f"Document processing pipeline failed: {str(e)}")
        raise  # Re-raise to propagate to main

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
            triples_dir=snapshot_base / "triples",
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