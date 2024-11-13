import logging
from pathlib import Path
from openai import AsyncOpenAI


DATA_DIR = Path("./data")

DEBUG = True

openai_client = AsyncOpenAI()


logger = logging.getLogger(__name__)