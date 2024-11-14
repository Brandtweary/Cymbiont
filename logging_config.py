import logging
import logging.handlers
from pathlib import Path
from typing import Optional
from datetime import datetime

def setup_logging(
    log_dir: Path,
    debug: bool = False,
    log_prefix: Optional[str] = None
) -> logging.Logger:
    """Configure comprehensive logging for the application."""
    # Create logs directory
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{log_prefix}_" if log_prefix else ""
    log_file = log_dir / f"{prefix}cymbiont_{timestamp}.log"
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s'
    )
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10_000_000,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(detailed_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(detailed_formatter)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Create application logger
    logger = logging.getLogger('cymbiont')
    
    # Log startup information
    logger.info("Cymbiont logging initialized")
    logger.info(f"Log file: {log_file}")
    logger.debug("Debug mode enabled" if debug else "Production mode enabled")
    
    return logger