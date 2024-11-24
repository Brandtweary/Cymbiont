import asyncio
from typing import Any, List
from api_queue import enqueue_api_call
from shared_resources import logger
from constants import CHAT_AGENT_MODEL
from prompts import CHAT_AGENT_SYSTEM_PROMPT
from utils import log_performance
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam, ChatCompletionAssistantMessageParam
from custom_dataclasses import ChatMessage
from logging_config import PROMPT


def convert_to_openai_message(message: ChatMessage) -> ChatCompletionMessageParam:
    """Convert our message format to OpenAI's format"""
    if message.role == "system":
        return ChatCompletionSystemMessageParam(role=message.role, content=message.content)
    elif message.role == "user":
        return ChatCompletionUserMessageParam(role=message.role, content=message.content)
    else:  # assistant
        return ChatCompletionAssistantMessageParam(role=message.role, content=message.content)


@log_performance
async def get_chat_response(message: str, chat_history: List[ChatMessage]) -> str:
    """
    Sends a message to the OpenAI chat agent with conversation history.

    Args:
        message (str): The user's input message.
        chat_history (List[ChatMessage]): Previous messages.

    Returns:
        str: The assistant's response.
    """
    try:
        # Initialize all messages in our format first
        messages: List[ChatMessage] = [
            ChatMessage(role="system", content=CHAT_AGENT_SYSTEM_PROMPT),
            *chat_history
        ]
        
        # Log the complete prompt
        prompt_text = "\n".join(
            f"{msg.role.upper()}: {msg.content}" for msg in messages
        ).replace("\n\n", "\n")
        logger.log(PROMPT, f"{prompt_text}")
        
        response = await enqueue_api_call(
            model=CHAT_AGENT_MODEL,
            messages=messages,
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