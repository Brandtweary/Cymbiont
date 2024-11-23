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

# Models
TAG_EXTRACTION_OPENAI_MODEL = "gpt-4o-mini"
CHAT_AGENT_MODEL = "gpt-4o-mini"

# Initialize OpenAI client
openai_client = AsyncOpenAI()


# Load config
def load_config() -> dict:
    """Load config from config.toml, creating it from example if it doesn't exist"""
    config_path = Path("config.toml")
    example_config_path = Path("config.example.toml")
    
    # If config.toml doesn't exist, copy from example
    if not config_path.exists():
        if not example_config_path.exists():
            raise FileNotFoundError("Neither config.toml nor config.example.toml found")
        
        print("Creating config.toml from example template")
        with open(example_config_path, "rb") as src, open(config_path, "wb") as dst:
            dst.write(src.read())
    
    # Load the config
    with open(config_path, "rb") as f:
        return tomllib.load(f)

config = load_config()
DEBUG = config["app"]["debug"]
BENCHMARK = config["app"]["benchmark"]
FILE_RESET = config["app"]["file_reset"]
PROMPT = config["app"]["prompt"]
RESPONSE = config["app"]["response"]
DELETE_LOGS = config["app"]["delete_logs"]

# Shell config
USER_NAME = config["shell"]["user_name"]
AGENT_NAME = config["shell"]["agent_name"]

# Initialize logging first
logger = setup_logging(
    LOG_DIR, 
    debug=DEBUG, 
    benchmark=BENCHMARK,
    prompt=PROMPT,
    response=RESPONSE
)

@dataclass
class TokenLogger:
    token_count: int = 0
    
    def add_tokens(self, tokens: int) -> None:
        """Add tokens to the running total"""
        self.token_count += tokens
    
    def print_tokens(self) -> None:
        """Print the current token count"""
        logger.info(f"Tokens used: {self.token_count}")
    
    def reset_tokens(self) -> None:
        """Reset token count to zero"""
        old_count = self.token_count
        self.token_count = 0

# Initialize token logger
token_logger = TokenLogger()