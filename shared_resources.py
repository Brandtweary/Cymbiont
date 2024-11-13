import logging
from pathlib import Path
from openai import AsyncOpenAI


DATA_DIR = Path("./data")

openai_client = AsyncOpenAI()

logger = logging.getLogger(__name__)