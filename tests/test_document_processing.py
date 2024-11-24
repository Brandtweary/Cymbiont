from pathlib import Path
from documents import process_documents, create_data_snapshot
from utils import get_paths, load_index, save_index
import shutil
from shared_resources import logger


async def test_process_documents() -> None:
    """Test the document processing pipeline with a mock document."""
    paths = get_paths(Path("data"))
    test_file = paths.docs_dir / "test.txt"
    test_content = "testing..."

    try:
        # Create test document
        test_file.write_text(test_content)

        # Process with mocked API calls
        chunks = await process_documents(
            paths.base_dir,
            "test.txt",
            mock=True,
            mock_content='{"tags": ["test tag"]}'  # Mock API response in correct JSON format
        )

        # Verify document was processed
        assert len(chunks) == 1, "Expected exactly one chunk"
        chunk = chunks[0]
        
        # Verify the mock tag was applied
        assert chunk.tags == ["test tag"], "Mock tag was not correctly applied to chunk"
        
        # Load indices
        doc_index = load_index(paths.index_dir / "documents.json")
        chunk_index = load_index(paths.index_dir / "chunks.json")
        
        # Check document was added to index using the specific doc_id
        assert chunk.doc_id in doc_index, "Document not found in index"
        
        # Verify chunk in index
        assert chunk.chunk_id in chunk_index, "Chunk not found in index"
        
        # Verify chunk file exists
        chunk_file = paths.chunks_dir / f"{chunk.chunk_id}.txt"
        assert chunk_file.exists(), "Chunk file not created"
        assert chunk_file.read_text() == test_content, "Chunk content doesn't match"
        
        # Verify document moved to processed
        processed_file = paths.processed_dir / "test.txt"
        assert processed_file.exists(), "Document not moved to processed directory"
        
        # Clean up exactly what we created
        del doc_index[chunk.doc_id]
        save_index(doc_index, paths.index_dir / "documents.json")
        
        del chunk_index[chunk.chunk_id]
        save_index(chunk_index, paths.index_dir / "chunks.json")
        
        # Remove files
        chunk_file.unlink()
        processed_file.unlink()

    except Exception as e:
        # Clean up on failure
        if test_file.exists():
            test_file.unlink()
        raise e


async def test_create_data_snapshot() -> None:
    """Test creating a data snapshot with a mock document."""
    paths = get_paths(Path("data"))
    test_file = paths.docs_dir / "test.txt"
    test_content = "testing..."
    snapshot_name = "test"

    try:
        # Create test document
        test_file.write_text(test_content)

        # Create snapshot with mocked API calls
        snapshot_base = await create_data_snapshot(
            snapshot_name,
            "test.txt",
            mock=True,
            mock_content='{"tags": ["test tag"]}'
        )

        # Get paths for the snapshot
        snapshot_paths = get_paths(snapshot_base)

        # Verify snapshot structure
        assert snapshot_paths.docs_dir.exists(), "Snapshot input_documents directory not created"
        assert snapshot_paths.processed_dir.exists(), "Snapshot processed_documents directory not created"
        assert snapshot_paths.chunks_dir.exists(), "Snapshot chunks directory not created"
        assert snapshot_paths.index_dir.exists(), "Snapshot indexes directory not created"

        # Load snapshot indices
        doc_index = load_index(snapshot_paths.index_dir / "documents.json")
        chunk_index = load_index(snapshot_paths.index_dir / "chunks.json")

        # Find the processed document and chunk
        processed_docs = list(snapshot_paths.processed_dir.glob("*.txt"))
        assert len(processed_docs) == 1, "Expected exactly one processed document"
        assert processed_docs[0].name == "test.txt", "Processed document has wrong name"

        chunks = list(snapshot_paths.chunks_dir.glob("*.txt"))
        assert len(chunks) == 1, "Expected exactly one chunk"
        assert chunks[0].read_text() == test_content, "Chunk content doesn't match"

        # Verify document and chunk indices have entries
        assert len(doc_index) == 1, "Expected one document in index"
        assert len(chunk_index) == 1, "Expected one chunk in index"
        
        # Get the first (and only) chunk from the index
        chunk_id = next(iter(chunk_index))
        chunk_data = chunk_index[chunk_id]
        
        # Verify the mock tag was applied
        assert chunk_data["tags"] == ["test tag"], "Mock tag was not correctly applied to chunk"

        # Clean up
        shutil.rmtree(snapshot_base)  # Remove entire snapshot
        test_file.unlink()  # Remove test file from input_documents

    except Exception as e:
        # Clean up on failure
        if test_file.exists():
            test_file.unlink()
        
        # Clean up snapshot directory if it exists
        # We can construct the expected path even if snapshot_base wasn't set
        expected_snapshot_dir = paths.snapshots_dir / f"{snapshot_name}_snapshot"
        if expected_snapshot_dir.exists():
            shutil.rmtree(expected_snapshot_dir)
        raise e

async def run_document_processing_tests() -> tuple[int, int]:
    """Run all document processing tests.
    Returns: Tuple of (passed_tests, failed_tests)"""
    logger.info("Starting document processing test suite...")
    passed = 0
    failed = 0
    
    for test in [test_process_documents, test_create_data_snapshot]:
        logger.info(f"Running {test.__name__}...")
        try:
            await test()
            logger.info(f"✓ {test.__name__} passed\n")
            passed += 1
        except Exception as e:
            logger.error(f"✗ {test.__name__} failed: {str(e)}\n")
            failed += 1
    
    return passed, failed
    