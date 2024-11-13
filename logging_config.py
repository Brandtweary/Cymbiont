import logging
import logging.handlers
from pathlib import Path
from typing import Optional
from datetime import datetime

class ConsoleFilter(logging.Filter):
    """Filter debug messages from console unless debug mode is enabled"""
    def __init__(self, debug: bool):
        self.debug = debug
        
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == logging.DEBUG:
            return self.debug
        return True

def setup_logging(
    log_dir: Path,
    debug: bool = False,
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
    console_handler.addFilter(ConsoleFilter(debug))  # Add filter for debug messages
    
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