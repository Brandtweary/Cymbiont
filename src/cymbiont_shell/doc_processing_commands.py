from shared_resources import logger, token_logger, DATA_DIR
from documents import process_documents, create_data_snapshot
from text_parser import test_parse

async def do_process_documents(args: str) -> None:
    """Process documents in the data/input_documents directory.
    Usage: process_documents [document_name]
    - document_name: Optional. If provided, only this file or folder will be processed.
                    Otherwise, processes all .txt and .md files."""
    try:
        with token_logger.show_tokens():
            await process_documents(DATA_DIR, args if args else None)
    except Exception as e:
        logger.error(f"Document processing failed: {str(e)}")


async def do_create_data_snapshot(args: str) -> None:
    """Creates an isolated snapshot by processing documents in the data/input_documents directory.
    The snapshot contains all processing artifacts (chunks, indexes, etc.) as if you had
    only processed the specified documents.

    Usage: create_data_snapshot <snapshot_name> [document_name]
    - snapshot_name: Name for the new snapshot directory
    - document_name: Optional. If provided, only this file or folder will be processed.
                    Otherwise, processes all .txt and .md files."""
    arg_parts = args.split()
    if not arg_parts:
        logger.error("Error: Please provide a name for the snapshot")
        return
    
    try:
        with token_logger.show_tokens():
            snapshot_path = await create_data_snapshot(
                arg_parts[0], 
                arg_parts[1] if len(arg_parts) > 1 else None
            )
            logger.info(f"Created snapshot at {snapshot_path}")
    except Exception as e:
        logger.error(f"Snapshot creation failed: {str(e)}")


async def do_parse_documents(args: str) -> None:
    """Test document parsing without running LLM tag extraction.
    This command parses documents in data/input_documents into chunks and records the results to logs/parse_test_results.log.

    Usage: parse_documents [document_name]
    - document_name: Optional. If provided, only this file or folder will be tested.
                    Otherwise, tests all .txt and .md files."""
    try:
        test_parse(args if args else None)
    except Exception as e:
        logger.error(f"Parse testing failed: {str(e)}")
