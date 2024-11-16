import logging
import logging.handlers
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime
from dataclasses import dataclass, field

BENCHMARK = logging.INFO + 5  # Custom level between INFO and WARNING
PROMPT = logging.INFO + 6
RESPONSE = logging.INFO + 7

logging.addLevelName(BENCHMARK, 'BENCHMARK')
logging.addLevelName(PROMPT, 'PROMPT')
logging.addLevelName(RESPONSE, 'RESPONSE')

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
        if record.levelno == logging.DEBUG:
            return self.debug
        if record.levelno == BENCHMARK:
            return self.benchmark
        if record.levelno == PROMPT:
            return self.prompt
        if record.levelno == RESPONSE:
            return self.response
        return True

@dataclass
class ProcessLog:
    """Collects logs for a specific process/task to be written together later"""
    name: str
    messages: List[Tuple[int, str]] = field(default_factory=list)
    
    def debug(self, message: str) -> None:
        """Store a debug level message"""
        self.messages.append((logging.DEBUG, message))
    
    def info(self, message: str) -> None:
        """Store an info level message"""
        self.messages.append((logging.INFO, message))
        
    def benchmark(self, message: str) -> None:
        """Store a benchmark level message"""
        self.messages.append((BENCHMARK, message))
        
    def warning(self, message: str) -> None:
        """Store a warning level message"""
        self.messages.append((logging.WARNING, message))
        
    def error(self, message: str) -> None:
        """Store an error level message"""
        self.messages.append((logging.ERROR, message))
        
    def prompt(self, message: str) -> None:
        """Store a prompt level message"""
        self.messages.append((PROMPT, message))
        
    def response(self, message: str) -> None:
        """Store a response level message"""
        self.messages.append((RESPONSE, message))
        
    def add_to_logger(self, logger: logging.Logger) -> None:
        """Write all collected messages to the provided logger"""
        if not self.messages:
            return
            
        # Create a process group header
        logger.info(f"=== Process Log: {self.name} ===")
        
        # Write all messages, respecting their original levels
        for level, message in self.messages:
            logger.log(level, message)
            
        logger.info(f"=== END ===")

def setup_logging(
    log_dir: Path,
    debug: bool = False,
    benchmark: bool = False,
    prompt: bool = False,
    response: bool = False,
    log_prefix: Optional[str] = None
) -> logging.Logger:
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
    console_formatter = logging.Formatter('%(message)s')  # Only show the message
    
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
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(ConsoleFilter(
        debug=debug,
        benchmark=benchmark,
        prompt=prompt,
        response=response
    ))
    
    # Configure cymbiont logger
    cymbiont_logger = logging.getLogger('cymbiont')
    cymbiont_logger.setLevel(logging.DEBUG)  # Always capture debug messages
    cymbiont_logger.addHandler(cymbiont_file_handler)
    cymbiont_logger.addHandler(console_handler)
    cymbiont_logger.propagate = True  # Allow logs to propagate to root logger
    
    # Log startup information
    cymbiont_logger.debug("Cymbiont logging initialized")
    cymbiont_logger.debug(f"Cymbiont log: {cymbiont_log_file}")
    cymbiont_logger.debug(f"Complete log: {complete_log_file}")
    
    return cymbiont_logger