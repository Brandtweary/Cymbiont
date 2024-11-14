import string
from typing import Any
from shared_resources import logger


NER_PROMPT = '''Return as a JSON array named "entities". Example:
{{
    "entities": ["John Smith", "UC Berkeley", "New York"]
}}
Please extract named entities from the following text:
---
{text}'''

TRIPLE_PROMPT = '''Return as a JSON array named "triples". Example:
{{
    "triples": [
        ["John Smith", "attended", "UC Berkeley"],
        ["UC Berkeley", "is located in", "California"]
    ]
}}
Please create RDF triples from the following text using OpenIE. Each triple should contain at least one named entity from the list.
---
Text: {text}

Named entities: {entities}'''


def safe_format_prompt(prompt_template: str, **kwargs: Any) -> str:
    """Safely format a prompt template with provided fields.
    
    Args:
        prompt_template: String template with {field_name} placeholders
        **kwargs: Field values to insert into template
    
    Returns:
        Formatted prompt string
    """
    # Format lists into string representation
    formatted_kwargs = {}
    for key, value in kwargs.items():
        if isinstance(value, list):
            formatted_kwargs[key] = f'["{"\", \"".join(str(x) for x in value)}"]'
        else:
            formatted_kwargs[key] = str(value)
    
    try:
        return prompt_template.format(**formatted_kwargs)
    except Exception as e:
        logger.error(f"Failed to format prompt: {e}")
        return prompt_template