import json
from json.decoder import JSONDecodeError
from typing import List, Optional

from shared_resources import logger, DEBUG_ENABLED
from constants import TAG_EXTRACTION_OPENAI_MODEL
from prompts import TAG_PROMPT, safe_format_prompt
from custom_dataclasses import Chunk, ChatMessage
from utils import log_performance
from api_queue import enqueue_api_call
from process_log import ProcessLog


@log_performance
async def extract_tags(
    chunk: Chunk, 
    process_log: ProcessLog,
    mock: bool = False,
    mock_content: str = ""
) -> None:
    """Extract relevant tags from a chunk of text."""
    try:
        tag_prompt = safe_format_prompt(TAG_PROMPT, text=chunk.text)
        process_log.prompt(f"Tag Extraction Prompt:\n{tag_prompt}")

        # Track expiration counter for retries
        expiration_counter = 0
        while expiration_counter < 3:  # Allow up to 3 total attempts
            future = enqueue_api_call(
                model=TAG_EXTRACTION_OPENAI_MODEL,
                messages=[ChatMessage(
                    role="user",
                    content=mock_content if mock else tag_prompt
                )],
                response_format={"type": "json_object"},
                mock=mock,
                mock_tokens=100,
                expiration_counter=expiration_counter,
                process_log=process_log
            )
            response = await future
            expiration_counter = response.get("expiration_counter", 5)  # Default to max if missing
            
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
            if tags is None or not tags:  # Check for empty tag list
                process_log.error(f"Failed to validate tag response or empty tags (attempt {expiration_counter})")
                if expiration_counter >= 2:
                    process_log.info(f"Final attempt count: {expiration_counter + 1}")
                    chunk.tags = []
                    return
                continue

            # Success case
            chunk.tags = tags
            chunk.metadata['tag_extraction_model'] = TAG_EXTRACTION_OPENAI_MODEL
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
        
        # New check for empty tag list
        if not tags:
            logger.warning("Tag list is empty")
            return None

        return tags

    except JSONDecodeError as e:
        logger.error(f"Invalid JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Validation failed: {str(e)}")
        return None