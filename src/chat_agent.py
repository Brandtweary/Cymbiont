import asyncio
from typing import Any, List, Optional
from api_queue import enqueue_api_call
from shared_resources import logger
from constants import CHAT_AGENT_MODEL, LogLevel
from prompts import CHAT_AGENT_SYSTEM_PROMPT
from utils import log_performance, convert_messages_to_string
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam, ChatCompletionAssistantMessageParam
from custom_dataclasses import ChatMessage


def convert_to_openai_message(message: ChatMessage) -> ChatCompletionMessageParam:
    """Convert our message format to OpenAI's format"""
    if message.role == "system":
        return ChatCompletionSystemMessageParam(role=message.role, content=message.content)
    elif message.role == "user":
        return ChatCompletionUserMessageParam(role=message.role, content=message.content)
    else:  # assistant
        return ChatCompletionAssistantMessageParam(role=message.role, content=message.content)


@log_performance
async def get_chat_response(messages: List[ChatMessage], progressive_summary: Optional[str] = None) -> str:
    """
    Sends a message to the OpenAI chat agent with conversation history.

    Args:
        messages: List of recent messages from buffer
        progressive_summary: Optional formatted summary of previous conversation

    Returns:
        str: The assistant's response.
    """
    try:
        # Build system prompt with optional summary
        system_content = CHAT_AGENT_SYSTEM_PROMPT
        if progressive_summary:
            system_content = f"{system_content}\n[{progressive_summary}]"
            
        # Initialize all messages (fixed list construction)
        messages_to_send: List[ChatMessage] = [
            ChatMessage(role="system", content=system_content),
            *messages
        ]
        
        # Log the complete prompt
        prompt_text = convert_messages_to_string(messages_to_send, truncate_last=False)
        logger.log(LogLevel.PROMPT, f"{prompt_text}")
        
        response = await enqueue_api_call(
            model=CHAT_AGENT_MODEL,
            messages=messages_to_send,
            response_format={"type": "text"},
            temperature=0.7
        )
        
        if not response["content"]:
            logger.error("Received an empty message from the OpenAI API.")
            return "Sorry, I encountered an error while processing your request."
            
        return response["content"]
    except Exception as e:
        logger.error(f"Error communicating with OpenAI API: {e}")
        return "Sorry, I encountered an error while processing your request."