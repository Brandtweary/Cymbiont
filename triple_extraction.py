from typing import List, Optional
from custom_dataclasses import Chunk, Paths, Triple
from shared_resources import openai_client, logger, DEBUG
from utils import log_performance
from prompts import safe_format_prompt, NER_PROMPT, TRIPLE_PROMPT
import json
from json.decoder import JSONDecodeError
from utils import generate_id, load_index, save_index


NER_OPENAI_MODEL = "gpt-4o-mini"

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
        field_name, triples = next(iter(data.items()))
        
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
async def extract_triples_from_ner(chunk: Chunk, entities: List[str]) -> Optional[List[Triple]]:
    """Extract triples from a chunk using the identified entities."""
    try:
        try:
            triple_prompt = safe_format_prompt(
                TRIPLE_PROMPT,
                text=chunk.text,
                entities=entities
            )
            logger.debug(f"Created triple prompt: {triple_prompt}")
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
            
        content = triple_response.choices[0].message.content
        if not content:
            logger.error("Empty response from OpenAI")
            return None
            
        valid_triples_data = validate_triple_extraction_response(content)
        logger.debug(f"Triples extracted: {valid_triples_data}")
        if valid_triples_data is None:
            return None
            
        # Convert to Triple objects
        triples = [
            Triple(
                triple_id=generate_id(f"{head}{relation}{tail}"),
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                head=head,
                relation=relation,
                tail=tail,
                metadata={"source": "openai_extraction"}
            )
            for head, relation, tail in valid_triples_data
        ]
    
        # Update chunk's triple_ids
        chunk.triple_ids = [triple.triple_id for triple in triples]
        return triples
            
    except Exception as e:
        logger.error(f"Failed to process chunk {chunk.chunk_id}: {str(e)}")
        if DEBUG:
            raise
        return None

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
        field_name, entities = next(iter(data.items()))
        
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

@log_performance
async def process_chunk_with_ner(chunk: Chunk, paths: Paths) -> Optional[List[Triple]]:
    """Process a single chunk through NER and triple extraction."""
    try:
        logger.debug(f"Starting processing of chunk: {chunk.chunk_id}")        
        try:
            ner_prompt = safe_format_prompt(
                NER_PROMPT,
                text=chunk.text
            )
        except ValueError as e:
            logger.error(f"Failed to format NER prompt: {e}")
            return None
            
        logger.debug(f"NER Prompt: {ner_prompt}")
            
        ner_response = await openai_client.chat.completions.create(
            model=NER_OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": ner_prompt
            }]
        )
        
        content = ner_response.choices[0].message.content
        logger.debug(f"Raw response: {content}")
        
        if not content:
            logger.warning("Empty response from OpenAI, using empty entities list")
            chunk.named_entities = []
            return await extract_triples_from_ner(chunk, [])
            
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
            doc_data["named_entities"] = list(set(doc_data["named_entities"] + entities))
            save_index(doc_index, paths.index_dir / "documents.json")
        else:
            logger.error(f"Document {chunk.doc_id} not found in document index")
            
        return await extract_triples_from_ner(chunk, entities)
        
    except Exception as e:
        logger.error(f"Failed to process chunk {chunk.chunk_id}: {str(e)}")
        if DEBUG:
            raise
        return None