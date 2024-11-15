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
    log_performance
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
        logger.debug(f"Starting NER processing of chunk: {chunk.chunk_id}")
        ner_prompt = safe_format_prompt(NER_PROMPT, text=chunk.text)
        logger.debug(f"NER Prompt: {ner_prompt}")

        # Define the API call as a coroutine
        async def api_call() -> str:
            response = await openai_client.chat.completions.create(
                model=NER_OPENAI_MODEL,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": ner_prompt}],
            )
            # Ensure 'usage' is present
            assert response.usage is not None, "API response missing 'usage'"
            tokens = response.usage.total_tokens
            logger.debug(f"NER API call used {tokens} tokens.")
            content = response.choices[0].message.content
            # Ensure 'content' is not None
            assert content is not None, "API response missing 'content'"
            return content

        # Create a future to await the result
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        def callback(result: Any) -> None:
            if isinstance(result, Exception):
                future.set_exception(result)
            else:
                future.set_result(result)

        # Enqueue the API call with priority 1
        enqueue_api_call(api_call, priority=1, callback=callback)

        # Await the future for the API response
        content: str = await future
        logger.debug(f"Raw NER response: {content}")

        if not content:
            logger.warning("Empty NER response from OpenAI")
            chunk.named_entities = []
            return []

        entities = validate_ner_response(content)
        if entities is None:
            logger.error("Failed to validate NER response")
            return None

        # Store entities in chunk and update parent document
        chunk.named_entities = entities

        # Load and update document index
        doc_index = load_index(paths.index_dir / "documents.json")
        if chunk.doc_id in doc_index:
            doc_data = doc_index[chunk.doc_id]
            # Add new entities without duplicates
            existing_entities = doc_data.get("named_entities", [])
            doc_data["named_entities"] = list(set(existing_entities + entities))
            save_index(doc_index, paths.index_dir / "documents.json")
            logger.debug(f"Updated document {chunk.doc_id} with new entities.")
        else:
            logger.error(f"Document {chunk.doc_id} not found in document index")

        return entities

    except AssertionError as e:
        logger.error(f"Assertion Error: {str(e)}")
        if DEBUG:
            raise
        return None
    except Exception as e:
        logger.error(f"Failed to process chunk {chunk.chunk_id}: {str(e)}")
        if DEBUG:
            raise
        return None


@log_performance
async def extract_triples_from_ner(chunk: Chunk, entities: List[str], paths: Paths) -> Optional[List[Triple]]:
    """Extract triples from a chunk using the identified entities."""
    try:
        triple_prompt = safe_format_prompt(TRIPLE_PROMPT, text=chunk.text, entities=entities)
        logger.debug(f"Created triple prompt: {triple_prompt}")

        # Define the API call as a coroutine
        async def api_call() -> str:
            response = await openai_client.chat.completions.create(
                model=NER_OPENAI_MODEL,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": triple_prompt}],
            )
            # Ensure 'usage' is present
            assert response.usage is not None, "API response missing 'usage'"
            tokens = response.usage.total_tokens
            logger.debug(f"Triple Extraction API call used {tokens} tokens.")
            content = response.choices[0].message.content
            # Ensure 'content' is not None
            assert content is not None, "API response missing 'content'"
            return content

        # Create a future to await the result
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        def callback(result: Any) -> None:
            if isinstance(result, Exception):
                future.set_exception(result)
            else:
                future.set_result(result)

        # Enqueue the API call with priority 1
        enqueue_api_call(api_call, priority=1, callback=callback)

        # Await the future for the API response
        content: str = await future
        logger.debug(f"Raw Triple Extraction response: {content}")

        if not content:
            logger.error("Empty Triple Extraction response from OpenAI")
            return None

        valid_triples_data = validate_triple_extraction_response(content)
        logger.debug(f"Triples extracted: {valid_triples_data}")
        if valid_triples_data is None:
            return None

        # Convert to Triple objects
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

        # Update chunk's triple_ids
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