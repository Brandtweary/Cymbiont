import logging
import logging.handlers
from pathlib import Path
from typing import Optional, Tuple, Any
from datetime import datetime
from .logger_types import LogLevel


# Register all custom log levels
for level in LogLevel:
    logging.addLevelName(level, level.name)

class ConsoleFilter(logging.Filter):
    """Filter messages based on config flags"""
    def __init__(
        self, 
        debug: bool, 
        benchmark: bool,
        prompt: bool,
        response: bool,
        tool: bool
    ):
        self.debug = debug
        self.benchmark = benchmark
        self.prompt = prompt
        self.response = response
        self.tool = tool
        self._quiet = False  # New flag for quiet mode

    @property
    def quiet(self) -> bool:
        return self._quiet

    @quiet.setter
    def quiet(self, value: bool) -> None:
        self._quiet = value

    def filter(self, record: logging.LogRecord) -> bool:
        if self._quiet:
            return False  # Block all messages in quiet mode
        if record.levelno == LogLevel.SHELL:
            return False  # Never show SHELL messages in console
        if record.levelno == logging.DEBUG:
            return self.debug
        if record.levelno == LogLevel.BENCHMARK:
            return self.benchmark
        if record.levelno == LogLevel.PROMPT:
            return self.prompt
        if record.levelno == LogLevel.RESPONSE:
            return self.response
        if record.levelno == LogLevel.TOOL:
            return self.tool
        return True

class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds color to console output"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ANSI color codes
        self.GREEN = "\033[38;2;0;255;0m"  # Neon green for Info, Debug
        self.YELLOW = "\033[33m"      # Warning
        self.RED = "\033[31m"         # Error
        self.BRIGHT_RED = "\033[91m"  # Critical
        self.WHITE = "\033[97m"       # Benchmark
        self.MAGENTA = "\033[35m"     # Prompt/Response
        self.CYAN = "\033[38;2;0;255;255m"  # Cyan for agent name in reasoning text
        self.RESET = "\033[0m"
        # RGB colors
        self.ORANGE = "\033[38;2;255;165;0m"  # Tool logs (RGB: 255,165,0)

    def format(self, record: logging.LogRecord) -> str:
        # Select color based on log level
        color = self.GREEN  # default
        prefix = ""
        
        if record.levelno == logging.WARNING:
            color = self.YELLOW
        elif record.levelno == logging.ERROR:
            color = self.RED
        elif record.levelno == logging.CRITICAL:
            color = self.BRIGHT_RED
            prefix = "CRITICAL: "
        elif record.levelno == LogLevel.BENCHMARK:
            color = self.WHITE
        elif record.levelno == LogLevel.TOOL:
            color = self.ORANGE
        elif record.levelno in (LogLevel.PROMPT, LogLevel.RESPONSE):
            color = self.MAGENTA
        elif record.levelno == LogLevel.REASONING_TEXT:
            # Special handling for reasoning text - color agent name in cyan
            if '>' in record.msg:
                agent_name, message = record.msg.split('>', 1)
                record.msg = f"{self.CYAN}{agent_name}>{self.WHITE}{message}"
                return super().format(record)
            color = self.WHITE
            
        # Format the message with color
        record.msg = f"{color}{prefix}{record.msg}{self.RESET}"
        return super().format(record)

class PromptRefreshingHandler(logging.StreamHandler):
    """A handler that refreshes the prompt after emitting logs"""
    
    def __init__(self, stream=None):
        super().__init__(stream)
        self.prompt_session: Any = None
    
    def emit(self, record):
        try:
            msg = self.format(record)
            
            # Clear the prompt first if we have a session
            if self.prompt_session:
                self.prompt_session.clear_prompt()
            
            # Write the message
            self.stream.write(msg)
            self.stream.write(self.terminator)
            self.flush()
            
            # Redraw the prompt after logs
            if self.prompt_session:
                self.prompt_session.redraw_prompt()
        except Exception:
            self.handleError(record)

def setup_logging(
    log_dir: Path,
    debug: bool = False,
    benchmark: bool = False,
    prompt: bool = False,
    response: bool = False,
    tool: bool = False,
    log_prefix: Optional[str] = None
) -> Tuple[logging.Logger, ConsoleFilter, PromptRefreshingHandler]:
    """Configure logging with separate handlers for cymbiont and all logs
    
    Returns:
        A tuple of (logger, console_filter, prompt_handler)
    """
    # Create logs directory
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{log_prefix}_" if log_prefix else ""
    cymbiont_log_file = log_dir / f"{prefix}cymbiont_{timestamp}.log"
    complete_log_file = log_dir / f"{prefix}complete_{timestamp}.log"
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s'
    )
    console_formatter = ColoredFormatter('%(message)s')
    
    # Set up complete logging (all modules)
    complete_handler = logging.handlers.RotatingFileHandler(
        complete_log_file,
        maxBytes=10_000_000,  # 10MB
        backupCount=5
    )
    complete_handler.setFormatter(file_formatter)
    
    # Configure root logger (catches everything)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    root_logger.addHandler(complete_handler)
    
    # Set up cymbiont-specific logging
    cymbiont_file_handler = logging.handlers.RotatingFileHandler(
        cymbiont_log_file,
        maxBytes=10_000_000,  # 10MB
        backupCount=5
    )
    cymbiont_file_handler.setFormatter(file_formatter)
    
    # Create console filter
    console_filter = ConsoleFilter(
        debug=debug,
        benchmark=benchmark,
        prompt=prompt,
        response=response,
        tool=tool
    )
    
    console_handler = PromptRefreshingHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(console_filter)
    
    # Configure cymbiont logger
    cymbiont_logger = logging.getLogger('cymbiont')
    cymbiont_logger.setLevel(logging.DEBUG)  # Always capture debug messages
    cymbiont_logger.addHandler(cymbiont_file_handler)
    cymbiont_logger.addHandler(console_handler)
    cymbiont_logger.propagate = True  # Allow logs to propagate to root logger
    
    # Log startup information
    cymbiont_logger.debug("Cymbiont logging initialized")
    cymbiont_logger.debug(f"App log created at: {cymbiont_log_file}") # only Cymbiont logs
    cymbiont_logger.debug(f"Full log created at: {complete_log_file}") # includes logs from all modules, not just Cymbiont
    
    return cymbiont_logger, console_filter, console_handler