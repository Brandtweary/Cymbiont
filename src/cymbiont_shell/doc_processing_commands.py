from shared_resources import logger, token_logger, DATA_DIR
from documents import process_documents, create_data_snapshot, find_unprocessed_documents
from text_parser import test_parse
from typing import List, Optional, Set
from chat_agent import get_response
from utils import get_paths
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from shared_resources import logger, DATA_DIR
from custom_dataclasses import ChatMessage
from api_queue import enqueue_api_call
from constants import REVISION_MODEL, LogLevel

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


async def do_revise_document(args: str) -> None:
    """
    Revise a document based on user instructions, running for a specified number of iterations.
    
    Usage: revise_document <document_name> [num_iterations]
    - document_name: Name of the document to revise
    - num_iterations: Optional. Number of iterations to run the revision process. Defaults to 1.
    """
    with token_logger.show_tokens():
        arg_parts = args.split()
        if not arg_parts:
            logger.error("Error: Please provide the document name and optionally the number of iterations")
            return
        
        doc_name = arg_parts[0]
        iterations = int(arg_parts[1]) if len(arg_parts) > 1 else 1
        
        paths = get_paths(DATA_DIR)
        input_docs = find_unprocessed_documents(paths)
        
        # Find the target document
        target_doc = None
        for doc in input_docs:
            if doc.name == doc_name:
                target_doc = doc
                break
        
        if not target_doc:
            logger.error(f"Document '{doc_name}' not found in input documents directory.")
            return

        # Create prompt session for getting revision instructions
        style = Style.from_dict({
            'prompt': '#00FFFF',  # Bright cyan
        })
        session = PromptSession(
            style=style,
            message=[('class:prompt', 'Enter revision instructions: ')]
        )
        
        # Get user instructions for revision
        instructions_text = await session.prompt_async()
        if not instructions_text.strip():
            logger.error("No revision instructions provided.")
            return

        # Read the original document
        doc_text = target_doc.read_text()
        
        # Create output document path
        output_name = f"{target_doc.stem}_revised{target_doc.suffix}"
        output_path = paths.docs_dir / output_name
        
        # Perform revisions
        current_text = doc_text
        for i in range(iterations):
            logger.info(f"Starting revision iteration {i+1}/{iterations}")
            
            # Create system message for this iteration
            system_message = (
                f"You are revising a document based on the following instructions:\n\n"
                f"{instructions_text}\n\n"
                f"Here is the current document text:\n\n{current_text}\n\n"
                f"Please output the complete revised document text. Do not include any meta remarks "
                f"about the revision process. Even if you only edit a small part, output the entire "
                f"document text. Your response will be saved directly as the new document content."
            )
            logger.log(LogLevel.PROMPT, system_message)
            
            # Get the revised text from the agent
            response = await enqueue_api_call(
                model=REVISION_MODEL,
                messages=[ChatMessage(role="system", content=system_message)],
                response_format={"type": "text"},
                temperature=0.7
            )
            
            revised_text = response.get("content", "")
            if not revised_text:
                logger.error(f"Error: Received empty response in iteration {i+1}")
                return
                
            current_text = revised_text

        # Save the final revision
        output_path.write_text(current_text)
        logger.info(f"Revised document saved as: {output_path.name}")
