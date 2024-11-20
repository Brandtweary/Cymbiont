import json
from json.decoder import JSONDecodeError
from typing import List, Optional

from shared_resources import logger, DEBUG, NER_OPENAI_MODEL
from prompts import TAG_PROMPT, safe_format_prompt
from custom_dataclasses import Chunk
from utils import log_performance
from api_queue import enqueue_api_call
from logging_config import ProcessLog


@log_performance
async def extract_tags(
    chunk: Chunk, 
    process_log: ProcessLog
) -> None:
    """Extract relevant tags from a chunk of text."""
    try:
        # Prepare prompt (we'll define TAG_PROMPT later)
        tag_prompt = safe_format_prompt(TAG_PROMPT, text=chunk.text)
        process_log.prompt(f"Tag Extraction Prompt:\n{tag_prompt}")

        # API call section
        future = enqueue_api_call(
            model=NER_OPENAI_MODEL,  # We can rename this constant later
            messages=[{"role": "user", "content": tag_prompt}],
            response_format={"type": "json_object"}
        )
        response = await future
        process_log.debug(f"Tag extraction API call used {response['token_usage']['total_tokens']} tokens")
        process_log.response(f"Tag Extraction Response:\n{response['content']}")
        
        if not response["content"]:
            process_log.warning("Empty tag extraction response")
            chunk.tags = []
            return

        tags = validate_tag_response(response["content"])
        if tags is None:
            process_log.error("Failed to validate tag response")
            chunk.tags = []
            return

        chunk.tags = tags
        process_log.debug(f"Extracted tags: {tags}")

    except Exception as e:
        process_log.error(f"Failed to process chunk {chunk.chunk_id}: {str(e)}")
        chunk.tags = []
        if DEBUG:
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
        return tags

    except JSONDecodeError as e:
        logger.error(f"Invalid JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Validation failed: {str(e)}")
        return None