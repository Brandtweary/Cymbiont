import logging
import logging.handlers
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
from custom_dataclasses import ChatHistory
from constants import LogLevel
import re


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
        response: bool
    ):
        self.debug = debug
        self.benchmark = benchmark
        self.prompt = prompt
        self.response = response
        
    def filter(self, record: logging.LogRecord) -> bool:
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
        return True

class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds color to console output"""
    def format(self, record: logging.LogRecord) -> str:
        # ANSI color codes
        GREEN = "\033[32m"       # Info, Debug
        YELLOW = "\033[33m"      # Warning
        RED = "\033[31m"         # Error
        BRIGHT_RED = "\033[91m"  # Critical
        WHITE = "\033[97m"       # Benchmark
        MAGENTA = "\033[35m"     # Prompt/Response
        RESET = "\033[0m"
        
        # Select color based on log level
        color = GREEN  # default
        prefix = ""
        
        if record.levelno == logging.WARNING:
            color = YELLOW
        elif record.levelno == logging.ERROR:
            color = RED
        elif record.levelno == logging.CRITICAL:
            color = BRIGHT_RED
            prefix = "CRITICAL: "
        elif record.levelno == LogLevel.BENCHMARK:
            color = WHITE
        elif record.levelno in (LogLevel.PROMPT, LogLevel.RESPONSE):
            color = MAGENTA
            
        # Format the message with color
        record.msg = f"{color}{prefix}{record.msg}{RESET}"
        return super().format(record)

class ChatHistoryHandler(logging.Handler):
    """Handler that adds log messages to chat history"""
    def __init__(
        self, 
        chat_history: Optional[ChatHistory] = None,
        console_filter: Optional[logging.Filter] = None
    ):
        super().__init__()
        self.chat_history = chat_history
        self.console_filter = console_filter
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def emit(self, record: logging.LogRecord) -> None:
        if (self.chat_history is not None 
            and record.levelno not in (LogLevel.PROMPT, LogLevel.RESPONSE)
            and (record.levelno == LogLevel.SHELL  # Always include SHELL messages
                or (self.console_filter is None or self.console_filter.filter(record)))
        ):
            clean_message = self.ansi_escape.sub('', self.format(record))
            prefixed_message = f"{record.levelname} - {clean_message}"
            self.chat_history.add_message("system", prefixed_message)

def setup_logging(
    log_dir: Path,
    debug: bool = False,
    benchmark: bool = False,
    prompt: bool = False,
    response: bool = False,
    log_prefix: Optional[str] = None
) -> Tuple[logging.Logger, ChatHistoryHandler]:  # Return both logger and handler
    """Configure logging with separate handlers for cymbiont and all logs"""
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
        response=response
    )
    
    console_handler = logging.StreamHandler()
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
    
    # Create chat history handler (initially without chat history)
    chat_history_handler = ChatHistoryHandler(console_filter=console_filter)
    chat_history_handler.setFormatter(logging.Formatter('%(message)s'))
    cymbiont_logger.addHandler(chat_history_handler)
    
    return cymbiont_logger, chat_history_handler