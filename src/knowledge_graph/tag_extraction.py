from typing import Optional, List
from shared_resources import logger, DEBUG_ENABLED
from custom_dataclasses import Chunk, ProcessLog, ChatMessage
from api_queue import enqueue_api_call
from model_configuration import TAG_EXTRACTION_MODEL
from prompts import get_system_message
from utils import log_performance
import json


@log_performance
async def extract_tags(
    chunk: Chunk, 
    process_log: ProcessLog,
    mock: bool = False,
    mock_content: str = ""
) -> None:
    """Extract relevant tags from a chunk of text."""
    try:
        system_content = get_system_message(["tag_extraction_system"], text=chunk.text)
        process_log.prompt(f"Tag Extraction Prompt:\n{system_content}")

        expiration_counter = 0
        while expiration_counter < 3:  
            messages_to_send = [
                ChatMessage(
                    role="user",
                    content="Please extract tags from the text.",
                    name=None
                )
            ]
            
            future = enqueue_api_call(
                model=TAG_EXTRACTION_MODEL,
                messages=messages_to_send,
                system_message=mock_content if mock else system_content,
                mock=mock,
                mock_tokens=100,
                expiration_counter=expiration_counter,
                process_log=process_log
            )
            response = await future
            expiration_counter = response.get("expiration_counter", 5)  
            
            process_log.debug(f"Tag extraction API call used {response['token_usage']['total_tokens']} tokens")
            process_log.response(f"Tag Extraction Response:\n{response['content']}")
            
            if not response["content"]:
                process_log.warning(f"Empty tag extraction response (attempt {expiration_counter})")
                if expiration_counter >= 2:
                    process_log.info(f"Final attempt count: {expiration_counter + 1}")
                    chunk.tags = []
                    return
                continue

            tags = validate_tag_response(response["content"])
            if tags is None or not tags:  
                process_log.error(f"Failed to validate tag response or empty tags (attempt {expiration_counter})")
                if expiration_counter >= 2:
                    process_log.info(f"Final attempt count: {expiration_counter + 1}")
                    chunk.tags = []
                    return
                continue

            chunk.tags = tags
            chunk.metadata['tag_extraction_model'] = TAG_EXTRACTION_MODEL
            process_log.debug(f"Extracted tags: {tags}")
            process_log.info(f"Final attempt count: {expiration_counter}")
            return

    except Exception as e:
        process_log.error(f"Failed to process chunk {chunk.chunk_id}: {str(e)}")
        chunk.tags = []
        if DEBUG_ENABLED:
            raise


def validate_tag_response(content: str) -> Optional[List[str]]:
    """Validate tag response and extract tags list."""
    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            logger.error(f"Expected JSON object, got {type(data)}")
            return None

        if len(data) != 1:
            logger.error(f"Expected exactly one field, got {len(data)}")
            return None

        _, tags = next(iter(data.items()))

        if not isinstance(tags, list):
            logger.error(f"Expected list of tags, got {type(tags)}")
            return None

        tags = [str(tag) for tag in tags]
        
        if not tags:
            logger.warning("Tag list is empty")
            return None

        return tags

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Error validating tag response: {e}")
        return None