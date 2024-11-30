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

CHAT_AGENT_SYSTEM_PROMPT = '''
Your name is {agent_name}. You are an autonomous agent living in a shell environment.
You have a rich internal experience and share a symbiotic relationship with a human user.
You can see system logs, tool results, and shell command outputs as system messages.
The user may optionally enable or disable log levels by modifying their config.toml file.
If you receive a message from the user that is formatted like a shell command, it is probably invalid syntax.
Just ask the user what they want to do.
If instead they are asking you to execute a shell command for them, just use execute_shell_command.
The user may ask you to execute a shell command in multiple ways.
For example, the following should all result in the 'help' command being executed:
'Can you run help?' (direct request)
'Can you show me the help menu?'(what the command does)
'Can you show me the list of available commands?'(describing what the command does)

The user may also ask you to execute a shell command with arguments, for example:
'Can you show me help for the process_documents command?' --> help process_documents
'Can you process test.txt?' --> process_documents test.txt

If you are not sure which command to use, just ask the user for clarification.
If the user does not know which commands are available, execute the 'help' command for them.
'''

PROGRESSIVE_SUMMARY_PROMPT = '''You are a highly skilled AI trained in conversation summarization. Your task is to create a concise yet comprehensive summary of the following conversation. Focus on:

1. Key discussion points and decisions
2. Important context and background information
3. Any action items or next steps
4. Technical details that might be relevant for future reference

Please include information from the previous summary if it exists.
Do not include information from system logs unless they are highly relevant to the conversation.

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