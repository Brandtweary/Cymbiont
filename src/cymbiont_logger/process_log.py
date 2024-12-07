import logging
from typing import List, Tuple
from cymbiont_logger.logger_types import LogLevel


class ProcessLog:
    """Collects logs for a specific process/task"""
    def __init__(self, name: str, logger: logging.Logger):
        self.name = name
        self.logger = logger
        self.messages: List[Tuple[int, str]] = []
    
    def debug(self, message: str) -> None:
        self.messages.append((logging.DEBUG, message))
    
    def info(self, message: str) -> None:
        self.messages.append((logging.INFO, message))
        
    def warning(self, message: str) -> None:
        self.messages.append((logging.WARNING, message))
        
    def error(self, message: str) -> None:
        self.messages.append((logging.ERROR, message))
        
    def benchmark(self, message: str) -> None:
        self.messages.append((LogLevel.BENCHMARK, message))
        
    def prompt(self, message: str) -> None:
        self.messages.append((LogLevel.PROMPT, message))
        
    def response(self, message: str) -> None:
        self.messages.append((LogLevel.RESPONSE, message))
    
    def add_to_logger(self) -> None:
        """Add all collected messages to the main logger"""
        # Print header
        self.logger.info(f"{'='*10} Process: {self.name} {'='*10}")
        
        # Print messages in sequence
        for level, message in self.messages:
            self.logger.log(level, f"  {message}")
        
        # Print footer
        self.logger.info(f"{'='*20} END {'='*20}")