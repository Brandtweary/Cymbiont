from pathlib import Path
from openai import AsyncOpenAI
from logging_config import setup_logging
import tomllib  # built-in for Python 3.11+

DATA_DIR = Path("./data")
LOG_DIR = DATA_DIR / "logs"

# Load config
def load_config() -> dict:
    with open("config.toml", "rb") as f:  # Note: tomllib requires binary mode ('rb')
        return tomllib.load(f)

config = load_config()
DEBUG = config["app"]["debug"]
BENCHMARK = config["app"]["benchmark"]
FILE_RESET = config["app"]["file_reset"]

# Initialize logging first
logger = setup_logging(LOG_DIR, debug=DEBUG, benchmark=BENCHMARK)

# Initialize OpenAI client
openai_client = AsyncOpenAI()