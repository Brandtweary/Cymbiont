from dataclasses import dataclass, asdict
from pathlib import Path
import json
import shutil
import hashlib
from typing import List, Dict, Optional, NamedTuple
import time
import re
import asyncio
from json.decoder import JSONDecodeError
from prompts import create_safe_prompt, NER_PROMPT, TRIPLE_PROMPT
from shared_resources import openai_client, logger, DEBUG
from utils import log_performance


NER_OPENAI_MODEL = "gpt-4o-mini"

# Data structures
@dataclass
class Document:
    """Represents a processed document"""
    doc_id: str          # Unique identifier
    filename: str        # Original filename
    processed_at: float  # Unix timestamp
    metadata: Dict       # Any additional metadata
    named_entities: Optional[List[str]] = None

@dataclass
class Chunk:
    """A chunk of text with references"""
    chunk_id: str        # Unique identifier
    doc_id: str         # Reference to parent document
    text: str           # Actual content
    position: int       # Order in document
    metadata: Dict      # Any additional metadata
    named_entities: Optional[List[str]] = None

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

# Add at top with other globals
_DIRS_INITIALIZED: bool = False
_PATHS: Optional[Paths] = None

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

@log_performance
async def extract_triples_from_ner(chunk: Chunk, entities: List[str]) -> Optional[List[Triple]]:
    """Extract triples from a chunk using the identified entities."""
    try:
        logger.info(f"Attempting triple extraction for chunk {chunk.chunk_id}")
        logger.info(f"Working with entities: {entities}")
        
        # Safely format triple prompt with validation
        try:
            triple_prompt = create_safe_prompt(
                TRIPLE_PROMPT,
                text=chunk.text,
                entities=entities
            )
            logger.debug(f"Created triple prompt: {triple_prompt[:200]}...")
        except ValueError as e:
            logger.error(f"Failed to format triple prompt: {e}")
            return None
            
        # OpenAI API call with error handling
        try:
            triple_response = await openai_client.chat.completions.create(
                model=NER_OPENAI_MODEL,
                response_format={"type": "json_object"},
                messages=[{
                    "role": "user",
                    "content": triple_prompt
                }]
            )
            logger.debug(f"Raw API response: {triple_response.choices[0].message.content}")
        except Exception as e:
            logger.error(f"OpenAI API call failed: {str(e)}")
            return None
            
        # Super defensive triple extraction
        try:
            content = triple_response.choices[0].message.content
            if not content:
                logger.error("Empty response from OpenAI")
                return None
                
            logger.debug(f"Parsing JSON content: {content}")
            triples_data = json.loads(content).get("triples", [])
            
            logger.debug(f"Extracted triples data: {triples_data}")
            
            if not isinstance(triples_data, list):
                logger.error(f"Expected list of triples, got {type(triples_data)}")
                return None
            
            valid_triples = []
            for t in triples_data:
                if not isinstance(t, list) or len(t) != 3:
                    continue
                    
                head, relation, tail = t  # Simple list unpacking
                valid_triples.append(
                    Triple(
                        triple_id=generate_id(f"{head}{relation}{tail}"),
                        chunk_id=chunk.chunk_id,
                        doc_id=chunk.doc_id,
                        head=str(head),
                        relation=str(relation),
                        tail=str(tail),
                        metadata={"source": "openai_extraction"}
                    )
                )
            
            if valid_triples:
                logger.info(f"Successfully extracted {len(valid_triples)} triples")
                logger.debug(f"Valid triples: {valid_triples}")
            else:
                logger.warning("No valid triples extracted")
                logger.debug("Triple extraction failed at validation stage")
            
            return valid_triples
            
        except Exception as e:
            logger.error(f"Failed to process response: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to process chunk {chunk.chunk_id}: {str(e)}")
        if DEBUG:
            raise  # Re-raise the exception in debug mode
        return None

@log_performance
async def process_chunk(chunk: Chunk) -> Optional[List[Triple]]:
    """Process a single chunk through NER and triple extraction."""
    try:
        logger.info(f"Starting processing of chunk: {chunk.chunk_id}")
        logger.debug(f"Chunk text: {chunk.text[:100]}...")
        
        # Safely format NER prompt with validation
        try:
            ner_prompt = create_safe_prompt(
                NER_PROMPT,
                text=chunk.text
            )
            logger.debug("NER prompt created successfully")
        except ValueError as e:
            logger.error(f"Failed to format NER prompt: {e}")
            return None
            
        # Log the actual prompt for debugging
        logger.debug(f"NER Prompt: {ner_prompt[:200]}...")
            
        ner_response = await openai_client.chat.completions.create(
            model=NER_OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": ner_prompt
            }]
        )
        
        logger.info("Received response from OpenAI")
        logger.debug(f"Raw response: {ner_response.choices[0].message.content}")
        
        # Super defensive entity extraction
        content: Optional[str] = None  # Define content at the start of the scope
        try:
            content = ner_response.choices[0].message.content
            if not content:
                logger.warning("Empty content received from OpenAI, using empty entities list")
                entities = []
            else:
                # Try to parse as JSON, with multiple fallback options
                try:
                    response_data = json.loads(content)
                    
                    # Try multiple possible response formats
                    entities = (
                        response_data.get("entities") or
                        response_data.get("named_entities") or
                        response_data.get("extracted_entities") or
                        response_data.get("results") or
                        []
                    )
                    
                    # If we got a string instead of a list, try to parse it
                    if isinstance(entities, str):
                        try:
                            entities = json.loads(entities)
                        except JSONDecodeError:
                            entities = [entities]  # Single entity as string
                    
                    # Ensure we have a list
                    if not isinstance(entities, list):
                        logger.warning(f"Unexpected entities format: {type(entities)}, converting to list")
                        entities = [str(entities)]
                    
                    # Filter out any non-string entities
                    entities = [str(e) for e in entities if e]
                    
                except JSONDecodeError:
                    logger.warning("Failed to parse JSON response, attempting to extract entities directly")
                    # Last resort: try to extract anything that looks like an entity
                    import re
                    entities = re.findall(r'"([^"]+)"', content)  # Extract quoted strings
                    if not entities:
                        entities = []
            
            logger.debug(f"Extracted entities: {entities}")
            
            # Store entities in chunk regardless of what we got
            chunk.named_entities = entities
            
            # Proceed with triple extraction even if entities list is empty
            return await extract_triples_from_ner(chunk, entities)
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {str(e)}")
            logger.debug(f"Raw response content: {content}")  # Now content is always defined
            # Don't fail completely, try with empty entities list
            return await extract_triples_from_ner(chunk, [])
        
    except Exception as e:
        logger.error(f"Failed to process chunk {chunk.chunk_id}: {str(e)}")
        if DEBUG:
            raise
        return None

async def get_triples(chunks: List[Chunk], base_dir: Path) -> List[Triple]:
    """Extract triples from text chunks using NER + OpenIE pipeline."""
    # Process all chunks concurrently
    results = await asyncio.gather(
        *[process_chunk(chunk) for chunk in chunks]
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

@log_performance
def process_documents(base_dir: Path) -> List[Chunk]:
    """Main document processing pipeline"""
    paths = get_paths(base_dir)
    
    logger.info("🏰 Starting document processing pipeline")
    
    if DEBUG:
        logger.info("🐛 Debug mode: Clearing indices and recycling processed documents")
        clear_indices(paths)
        move_processed_to_documents(paths)
    
    # Load indices
    doc_index = load_index(paths.index_dir / "documents.json")
    chunk_index = load_index(paths.index_dir / "chunks.json")
    
    # Find documents to process
    unprocessed = find_unprocessed_documents(paths)
    logger.info(f"📄 Found {len(unprocessed)} documents to process")
    
    if not unprocessed:
        logger.warning("⚠️ No documents to process")
        return []
    
    # Process each document
    all_chunks = []
    for filepath in unprocessed:
        logger.info(f"🔄 Processing {filepath.name}")
        doc, chunks = process_document(filepath, paths, doc_index)
        save_chunks(chunks, paths, chunk_index)
        all_chunks.extend(chunks)
    
    # Extract triples if chunks were processed
    if all_chunks:
        logger.info(f"🎯 Extracting triples from {len(all_chunks)} chunks")
        asyncio.run(get_triples(all_chunks, base_dir))
        
    logger.info(f"✅ Processing complete - {len(all_chunks)} chunks processed")
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
