from typing import Any, List, Optional
from shared_resources import logger, DEBUG_ENABLED
import re
from .llm_types import SystemPromptPartInfo, SystemPromptPartsData
from llms.system_prompt_parts import SYSTEM_MESSAGE_PARTS


DEFAULT_SYSTEM_PROMPT_PARTS = SystemPromptPartsData(parts={
    "chat_agent_base_prompt": SystemPromptPartInfo(toggled=True, index=0),
    "cymbiont_agent_overview": SystemPromptPartInfo(toggled=False, index=1),
    "biographical": SystemPromptPartInfo(toggled=False, index=2),
    "shell_command_docs": SystemPromptPartInfo(toggled=False, index=3),
    "taskpad": SystemPromptPartInfo(toggled=True, index=4),
    "previous_tool_call": SystemPromptPartInfo(toggled=True, index=5),
    "response_guidelines": SystemPromptPartInfo(toggled=True, index=6)
})


def escape_json_in_prompt(content: str) -> tuple[str, bool]:
    """
    Find and escape JSON-like objects in prompt content.
    Returns the escaped content and whether any unescaped JSON was found.
    """
    # Pattern to match JSON-like objects with unescaped braces
    # Looks for {<whitespace>"key":<any chars>} pattern
    json_pattern = r'(?<!{){[\s\n]*"[^"]+"\s*:'

    found_unescaped = bool(re.search(json_pattern, content))
    
    # Replace single braces around JSON-like objects with double braces
    def replace_json_braces(match: re.Match) -> str:
        # Get the full JSON object by finding matching closing brace
        start = match.start()
        brace_count = 1
        end = start + 1
        
        while brace_count > 0 and end < len(content):
            if content[end] == '{':
                brace_count += 1
            elif content[end] == '}':
                brace_count -= 1
            end += 1
            
        json_obj = content[start:end]
        # Replace the outer braces with double braces
        return '{{' + json_obj[1:-1] + '}}'
    
    escaped_content = re.sub(json_pattern, replace_json_braces, content)
    
    return escaped_content, found_unescaped

def create_system_prompt_parts_data(part_names: List[str], **kwargs) -> SystemPromptPartsData:
    """Create a SystemPromptPartsData instance from a list of part names.
    Each part will be toggled on with an incrementing index.
    
    Args:
        part_names: List of part names to include
        **kwargs: Additional format arguments for the message parts
        
    Returns:
        SystemPromptPartsData with the specified parts enabled
    """
    parts = {}
    for i, name in enumerate(part_names):
        if name not in SYSTEM_MESSAGE_PARTS:
            logger.warning(f"Unknown system message part: {name}")
            continue
        parts[name] = SystemPromptPartInfo(toggled=True, index=i)
        
    return SystemPromptPartsData(parts=parts, kwargs=kwargs)

def get_system_message(
    system_prompt_parts: Optional[SystemPromptPartsData] = None
) -> str:
    """Build a system message from specified parts.
    
    Args:
        system_prompt_parts: Optional SystemPromptPartsData instance containing which parts to include
                           and their toggle/index info. If None, uses DEFAULT_SYSTEM_PROMPT_PARTS.
    """
    message_parts = []
    
    # If no system_prompt_parts provided, use DEFAULT_SYSTEM_PROMPT_PARTS
    if system_prompt_parts is None:
        system_prompt_parts = DEFAULT_SYSTEM_PROMPT_PARTS
    
    # Sort parts by index
    ordered_parts = sorted(
        system_prompt_parts.parts.items(), 
        key=lambda x: x[1].index
    )

    # Build message from parts
    for part, info in ordered_parts:
        if part not in SYSTEM_MESSAGE_PARTS:
            logger.warning(f"Unknown system message part: {part}")
            continue
            
        part_info = SYSTEM_MESSAGE_PARTS[part]
        
        # Check all required parameters are provided
        if not all(param in system_prompt_parts.kwargs for param in part_info.required_params):
            logger.warning(f"Missing required parameters for {part}")
            continue
        
        # Only include and format content if the part is toggled on
        if info.toggled:
            try:
                # Check for and escape any JSON-like objects
                escaped_content, found_unescaped = escape_json_in_prompt(part_info.content)
                if found_unescaped:
                    logger.warning(f"Found and escaped JSON-like objects in {part}")
                
                # Format the content with provided parameters
                formatted_content = escaped_content.format(**system_prompt_parts.kwargs)
                # Strip any extra newlines from the end of the content
                formatted_content = formatted_content.rstrip()
                # Join header and content with single newline
                message_parts.append(f"-- {part_info.header} --\n{formatted_content}")
            except Exception as e:
                logger.error(f"Failed to format {part}: {e}")
                if DEBUG_ENABLED:
                    raise
            
    return "\n\n".join(message_parts)