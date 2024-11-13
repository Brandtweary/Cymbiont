from pathlib import Path
from openai import AsyncOpenAI
from logging_config import setup_logging

DATA_DIR = Path("./data")
LOG_DIR = DATA_DIR / "logs"

DEBUG = True
FILE_RESET = True

# Initialize logging first
logger = setup_logging(LOG_DIR, debug=DEBUG)

# Initialize OpenAI client
openai_client = AsyncOpenAI()