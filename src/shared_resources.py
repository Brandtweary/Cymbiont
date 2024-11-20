from pathlib import Path
from openai import AsyncOpenAI
from logging_config import setup_logging
import tomllib
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional

# Get the project root (one level up from src)
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Load environment variables first
load_dotenv(PROJECT_ROOT / '.env')

# Verify the path exists
if not DATA_DIR.exists():
    DATA_DIR.mkdir(parents=True)

LOG_DIR = DATA_DIR / "logs"

# Load config
def load_config() -> dict:
    with open("config.toml", "rb") as f:  # Note: tomllib requires binary mode ('rb')
        return tomllib.load(f)

config = load_config()
DEBUG = config["app"]["debug"]
BENCHMARK = config["app"]["benchmark"]
FILE_RESET = config["app"]["file_reset"]
PROMPT = config["app"]["prompt"]
RESPONSE = config["app"]["response"]

# Initialize logging first
logger = setup_logging(
    LOG_DIR, 
    debug=DEBUG, 
    benchmark=BENCHMARK,
    prompt=PROMPT,
    response=RESPONSE
)

# Initialize OpenAI client
openai_client = AsyncOpenAI()

@dataclass
class TokenLogger:
    token_count: int = 0
    
    def add_tokens(self, tokens: int) -> None:
        """Add tokens to the running total"""
        self.token_count += tokens
    
    def print_tokens(self) -> None:
        """Print the current token count"""
        logger.info(f"Current token count: {self.token_count}")
    
    def reset_tokens(self) -> None:
        """Reset token count to zero"""
        old_count = self.token_count
        self.token_count = 0

# Initialize token logger
token_logger = TokenLogger()