from pathlib import Path
from openai import AsyncOpenAI
from logging_config import setup_logging
import tomllib
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import Optional
from contextlib import contextmanager
from typing import List
import inspect
from anthropic import AsyncAnthropic

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

# Initialize logging first
logger = setup_logging(
    LOG_DIR, 
    debug=DEBUG_ENABLED,
    benchmark=BENCHMARK_ENABLED,
    prompt=PROMPT_ENABLED,
    response=RESPONSE_ENABLED,
    tool=TOOL_ENABLED
)

@dataclass
class TokenLogger:
    running_token_count: int = 0
    total_token_count: int = 0
    _token_stack: List[int] = field(default_factory=list)
    
    def add_tokens(self, tokens: int) -> None:
        """Add tokens to the running total"""
        self.running_token_count += tokens
        self.total_token_count += tokens
        
    @contextmanager
    def show_tokens(self, print_tokens: bool = True, name: Optional[str] = None):
        """Context manager that shows token usage for a scope.
        Handles nested token tracking automatically.
        
        Args:
            print_tokens: Whether to print token usage when exiting the scope
            name: Optional name to identify the scope. If not provided, will try to
                 determine the calling function name."""
        if name is None:
            name = "unknown"
            # Get calling frame
            frame = inspect.currentframe()
            if frame is not None:
                try:
                    # Go up two frames: one for show_tokens, one for the context manager
                    caller = frame.f_back
                    if caller is not None and caller.f_back is not None:
                        caller = caller.f_back  # Get the actual calling frame
                        name = caller.f_code.co_name
                        # Special cases
                        if name == "handle_chat":
                            name = ""  # Empty string for handle_chat
                        elif name.startswith("do_"):
                            name = name[3:]  # Remove do_ prefix
                finally:
                    del frame  # Avoid reference cycles
                
        self._token_stack.append(self.running_token_count)
        self.running_token_count = 0
        try:
            yield
        finally:
            # Get tokens used in this scope
            scope_tokens = self.running_token_count
            # Restore parent scope's tokens
            self.running_token_count = self._token_stack.pop() + scope_tokens
            if print_tokens and TOKEN_LOGGING:
                prefix = f"Tokens used in {name}: " if name else "Tokens used: "
                logger.info(f"{prefix}{scope_tokens}")
    
    def print_total_tokens(self) -> None:
        """Print the total token count across all scopes"""
        logger.info(f"Total tokens used: {self.total_token_count}")
        
# Initialize token logger
token_logger = TokenLogger()