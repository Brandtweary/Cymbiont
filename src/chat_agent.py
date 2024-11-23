import asyncio
from typing import Any
from shared_resources import openai_client, CHAT_AGENT_MODEL, logger
from prompts import CHAT_PROMPT
from utils import log_performance


@log_performance
async def get_chat_response(message: str) -> str:
    """
    Sends a message to the OpenAI chat agent and returns the response.

    Args:
        message (str): The user's input message.

    Returns:
        str: The assistant's response.
    """
    try:
        response = await openai_client.chat.completions.create(
            model=CHAT_AGENT_MODEL,
            messages=[
                {"role": "system", "content": CHAT_PROMPT},
                {"role": "user", "content": message}
            ],
            temperature=0.7
        )
        assistant_message = response.choices[0].message.content
        if assistant_message is None:
            logger.error("Received a null message from the OpenAI API.")
            return "Sorry, I encountered an error while processing your request."
        return assistant_message
    except Exception as e:
        logger.error(f"Error communicating with OpenAI API: {e}")
        return "Sorry, I encountered an error while processing your request."