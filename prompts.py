import string
from typing import Dict, Any
import logging
import re

logger = logging.getLogger(__name__)

def safe_format_prompt(prompt_template: str, params: Dict[str, Any]) -> str:
    """Combat-ready prompt formatter. No JSON validation, just pure string formatting."""
    # Initialize sanitized_params BEFORE try block
    sanitized_params = {
        k: str(v).replace('{', '').replace('}', '')  # Strip formatting characters
        for k, v in params.items()
    }
    
    try:
        # Direct format attempt
        return prompt_template.format(**sanitized_params)
            
    except Exception as e:
        logger.error(f"Prompt formatting failed: {str(e)}")
        # Now sanitized_params is ALWAYS defined
        return prompt_template.replace('{text}', sanitized_params.get('text', ''))

def validate_prompt_template(template: str) -> bool:
    """Validate a prompt template for common issues."""
    try:
        # Check for balanced brackets
        bracket_count = 0
        for char in template:
            if char == '{': bracket_count += 1
            if char == '}': bracket_count -= 1
            if bracket_count < 0:
                raise ValueError("Unmatched closing bracket")
        if bracket_count != 0:
            raise ValueError("Unmatched opening bracket")
            
        # Validate format string syntax
        string.Formatter().parse(template)
        
        return True
    except Exception as e:
        logger.error(f"Template validation failed: {str(e)}")
        return False

def create_safe_prompt(template: str, **kwargs: Any) -> str:
    """Create a prompt with validation and safe formatting."""
    if not validate_prompt_template(template):
        raise ValueError("Invalid prompt template")
    return safe_format_prompt(template, kwargs)

NER_PROMPT = '''Extract named entities from the text:

{text}

Format as JSON with an "entities" array.'''

TRIPLE_PROMPT = '''Extract factual relationships from this text as simple triples. Each triple should be a list of [entity1, relationship, entity2].

Text: {text}
Known entities: {entities}

Return as JSON array named "triples".'''