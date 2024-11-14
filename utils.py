import asyncio
import hashlib
import time
import functools
from typing import Callable, Any, Dict
from shared_resources import logger
from pathlib import Path
import json

def log_performance(func: Callable) -> Callable:
    """Decorator to log function performance."""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        duration = time.perf_counter() - start
        logger.debug(f"{func.__name__} completed in {duration:.2f}s")
        return result
        
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        duration = time.perf_counter() - start
        logger.debug(f"{func.__name__} completed in {duration:.2f}s")
        return result
        
    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

def generate_id(content: str) -> str:
    """Generate a stable ID from content"""
    return hashlib.sha256(content.encode()).hexdigest()[:12]

def load_index(index_path: Path) -> Dict:
    """Load an index file or create if doesn't exist"""
    if index_path.exists():
        return json.loads(index_path.read_text())
    return {}

def save_index(data: Dict, index_path: Path) -> None:
    """Save an index to disk"""
    index_path.write_text(json.dumps(data, indent=2))