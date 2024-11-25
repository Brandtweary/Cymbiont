from typing import Any
from shared_resources import logger


TAG_PROMPT = '''Please extract relevant tags from the following text. Tag all named entities, categories, and concepts.
Return as a JSON array named "tags". Example:
{{
    "tags": ["John Smith", "UC Berkeley", "machine learning"]
}}
---
Text: {text}
---'''

CHAT_AGENT_SYSTEM_PROMPT = '''You are an autonomous agent in a shell environment.
When the user executes a command, you can see the output as a system message.
The user may optionally enable or disable log levels by modifying their config.toml file.
'''

PROGRESSIVE_SUMMARY_PROMPT = '''You are a highly skilled AI trained in conversation summarization. Your task is to create a concise yet comprehensive summary of the following conversation. Focus on:

1. Key discussion points and decisions
2. Important context and background information
3. Any action items or next steps
4. Technical details that might be relevant for future reference

Please include key information from the previous summary if it exists.

Conversation:
{conversation}
---

Provide your summary in a clear, structured format.'''


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