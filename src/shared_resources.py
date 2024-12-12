from pathlib import Path
from openai import AsyncOpenAI
from cymbiont_logger.logging_config import setup_logging
import tomllib
from dotenv import load_dotenv
from typing import NamedTuple
from anthropic import AsyncAnthropic


class Paths(NamedTuple):
    """Paths for data storage"""
    base_dir: Path
    docs_dir: Path
    processed_dir: Path
    chunks_dir: Path
    index_dir: Path
    logs_dir: Path
    inert_docs_dir: Path
    snapshots_dir: Path
    agent_notes_dir: Path  # Directory for agent's daily notes

# Get the project root (one level up from src)
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Load environment variables first
load_dotenv(PROJECT_ROOT / '.env')

# Verify the path exists
if not DATA_DIR.exists():
    DATA_DIR.mkdir(parents=True)

LOG_DIR = DATA_DIR / "logs"

openai_client = AsyncOpenAI()
anthropic_client = AsyncAnthropic()

# Shell singleton instance
_shell_instance = None

def get_shell():
    """Get the shell instance. Raises RuntimeError if not initialized."""
    global _shell_instance
    if _shell_instance is None:
        raise RuntimeError("Shell instance not initialized")
    return _shell_instance

def set_shell(shell):
    """Set the shell instance."""
    global _shell_instance
    _shell_instance = shell

# Load config
def load_config() -> dict:
    """Load config from config.toml, creating it from example if it doesn't exist"""
    config_path = Path("config.toml")
    example_config_path = Path("config.example.toml")
    
    # If config.toml doesn't exist, copy from example
    if not config_path.exists():
        with example_config_path.open("rb") as f:
            example_config = f.read()
        with config_path.open("wb") as f:
            f.write(example_config)
    
    with config_path.open("rb") as f:
        return tomllib.load(f)

config = load_config()
DEBUG_ENABLED = config["app"]["debug"]
BENCHMARK_ENABLED = config["app"]["benchmark"]
FILE_RESET = config["app"]["file_reset"]
PROMPT_ENABLED = config["app"]["prompt"]
RESPONSE_ENABLED = config["app"]["response"]
DELETE_LOGS = config["app"]["delete_logs"]
TOKEN_LOGGING = config["app"]["token_logging"]
TOOL_ENABLED = config["app"]["tool"]

# Shell config
USER_NAME = config["shell"]["user_name"]
AGENT_NAME = config["shell"]["agent_name"]

# Agent activation mode config
VALID_AGENT_ACTIVATION_MODES = {"continuous", "chat"}
AGENT_ACTIVATION_MODE = config["shell"].get("agent_activation_mode", "continuous")
if AGENT_ACTIVATION_MODE not in VALID_AGENT_ACTIVATION_MODES:
    raise ValueError(
        f"Invalid agent activation mode: {AGENT_ACTIVATION_MODE}. "
        f"Must be one of: {', '.join(VALID_AGENT_ACTIVATION_MODES)}"
    )

# Initialize logging
logger, console_filter, console_handler = setup_logging(
    LOG_DIR, 
    debug=DEBUG_ENABLED,
    benchmark=BENCHMARK_ENABLED,
    prompt=PROMPT_ENABLED,
    response=RESPONSE_ENABLED,
    tool=TOOL_ENABLED
)
