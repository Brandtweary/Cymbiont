import asyncio
import time
import functools
from typing import Callable, Any
from shared_resources import logger

def log_performance(func: Callable) -> Callable:
    """Decorator to log function performance."""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        duration = time.perf_counter() - start
        logger.info(f"⚡ {func.__name__} completed in {duration:.2f}s")
        return result
        
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        duration = time.perf_counter() - start
        logger.info(f"⚡ {func.__name__} completed in {duration:.2f}s")
        return result
        
    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper