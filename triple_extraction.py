import asyncio
import json
from json.decoder import JSONDecodeError
from typing import List, Optional, Any

from shared_resources import logger, openai_client, DEBUG
from prompts import NER_PROMPT, TRIPLE_PROMPT, safe_format_prompt
from custom_dataclasses import Chunk, Triple, Paths
from utils import (
    generate_id,
    load_index,
    save_index,
    log_performance,
    async_timing_section
)
from api_queue import enqueue_api_call

NER_OPENAI_MODEL = "gpt-4o-mini"


def validate_ner_response(content: str) -> Optional[List[str]]:
    """Validate NER response and extract entities list."""
    try:
        # Parse JSON
        data = json.loads(content)
        if not isinstance(data, dict):
            logger.error(f"Expected JSON object, got {type(data)}")
            return None

        # Ensure only one field
        if len(data) != 1:
            logger.error(f"Expected exactly one field, got {len(data)}")
            return None

        # Get the entities list (regardless of field name)
        _, entities = next(iter(data.items()))

        if not isinstance(entities, list):
            logger.error(f"Expected list of entities, got {type(entities)}")
            return None

        # Ensure all entities are strings
        entities = [str(entity) for entity in entities]
        return entities

    except JSONDecodeError as e:
        logger.error(f"Invalid JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Validation failed: {str(e)}")
        return None


def validate_triple_extraction_response(content: str) -> Optional[List[List[str]]]:
    """Validate triple extraction response and normalize format."""
    try:
        # Parse JSON
        data = json.loads(content)
        if not isinstance(data, dict):
            logger.error(f"Expected JSON object, got {type(data)}")
            return None

        # Ensure only one field
        if len(data) != 1:
            logger.error(f"Expected exactly one field, got {len(data)}")
            return None

        # Get the triples list (regardless of field name)
        _, triples = next(iter(data.items()))

        # Handle case where single triple isn't nested properly
        if isinstance(triples, list) and len(triples) == 3 and all(isinstance(x, str) for x in triples):
            logger.warning("Found non-nested triple, normalizing format")
            triples = [triples]

        if not isinstance(triples, list):
            logger.error(f"Expected list of triples, got {type(triples)}")
            return None

        # Validate each triple
        valid_triples = []
        for i, triple in enumerate(triples):
            if not isinstance(triple, list):
                logger.warning(f"Triple {i} is not a list, skipping")
                continue

            if len(triple) != 3:
                logger.warning(f"Triple {i} does not have exactly 3 elements, skipping")
                continue

            # Convert all elements to strings
            valid_triples.append([str(elem) for elem in triple])

        if not valid_triples:
            logger.warning("No valid triples found in response")
            return None

        return valid_triples

    except JSONDecodeError as e:
        logger.error(f"Invalid JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Validation failed: {str(e)}")
        return None


@log_performance
async def process_chunk_with_ner(chunk: Chunk, paths: Paths) -> Optional[List[str]]:
    """Process a single chunk through NER."""
    try:
        # Prepare prompt
        ner_prompt = safe_format_prompt(NER_PROMPT, text=chunk.text)
        logger.debug(f"Starting NER processing of chunk: {chunk.chunk_id}")

        # API call section - isolated
        future = enqueue_api_call(
            model=NER_OPENAI_MODEL,
            messages=[{"role": "user", "content": ner_prompt}],
            response_format={"type": "json_object"}
        )
        response = await future
        logger.debug(f"NER API call used {response['token_usage']['total_tokens']} tokens")
        
        if not response["content"]:
            logger.warning("Empty NER response from OpenAI")
            chunk.named_entities = []
            return []

        entities = validate_ner_response(response["content"])
        if entities is None:
            chunk.named_entities = []
            return []

        chunk.named_entities = entities
        logger.debug(f"Updated chunk {chunk.chunk_id} with entities: {entities}")
        return entities

    except AssertionError as e:
        logger.error(f"Assertion Error: {str(e)}")
        if DEBUG:
            raise
        return []
    except Exception as e:
        logger.error(f"Failed to process chunk {chunk.chunk_id}: {str(e)}")
        if DEBUG:
            raise
        return []


@log_performance
async def extract_triples_from_ner(chunk: Chunk, entities: List[str], paths: Paths) -> Optional[List[Triple]]:
    """Extract triples from a chunk using the identified entities."""
    try:
        # Prepare prompt
        triple_prompt = safe_format_prompt(TRIPLE_PROMPT, text=chunk.text, entities=entities)
        logger.debug(f"Created triple prompt: {triple_prompt}")

        # API call section - isolated
        future = enqueue_api_call(
            model=NER_OPENAI_MODEL,
            messages=[{"role": "user", "content": triple_prompt}],
            response_format={"type": "json_object"}
        )
        response = await future
        logger.debug(f"Triple Extraction API call used {response['token_usage']['total_tokens']} tokens")
        
        if not response["content"]:
            logger.error("Empty Triple Extraction response from OpenAI")
            return None

        # Process response and create triples
        logger.debug(f"Raw Triple Extraction response: {response['content']}")
        valid_triples_data = validate_triple_extraction_response(response["content"])
        logger.debug(f"Triples extracted: {valid_triples_data}")
        if valid_triples_data is None:
            return None

        triples: List[Triple] = [
            Triple(
                triple_id=generate_id(f"{head}{relation}{tail}"),
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                head=head,
                relation=relation,
                tail=tail,
                metadata={"source": "openai_extraction"},
            )
            for head, relation, tail in valid_triples_data
        ]

        chunk.triple_ids = [triple.triple_id for triple in triples]
        logger.debug(f"Updated chunk {chunk.chunk_id} with triple IDs.")

        return triples

    except AssertionError as e:
        logger.error(f"Assertion Error: {str(e)}")
        if DEBUG:
            raise
        return None
    except Exception as e:
        logger.error(f"Failed to extract triples from chunk {chunk.chunk_id}: {str(e)}")
        if DEBUG:
            raise
        return None