import asyncio
import hashlib
import time
import functools
from typing import Callable, Any, Dict, Optional, Generator, AsyncGenerator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from collections import defaultdict
from shared_resources import logger
from pathlib import Path
import json
from logging_config import BENCHMARK

@dataclass
class TimingContext:
    sections: Dict[str, float] = field(default_factory=lambda: defaultdict(float))

# Create a context variable to hold the timing context
_current_context: ContextVar[Optional[TimingContext]] = ContextVar('timing_context', default=None)

@contextmanager
def timing_section(section_name: str) -> Generator[None, None, None]:
    """Synchronous context manager for timing code sections."""
    context = _current_context.get()
    if context is None:
        yield
        return
        
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        context.sections[section_name] += duration

@asynccontextmanager
async def async_timing_section(section_name: str) -> AsyncGenerator[None, None]:
    """Asynchronous context manager for timing code sections."""
    context = _current_context.get()
    if context is None:
        yield
        return
        
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        context.sections[section_name] += duration

def log_performance(func: Callable) -> Callable:
    """Decorator to log function performance."""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs) -> Any:
        context = TimingContext()
        token = _current_context.set(context)
        
        start = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            total_duration = time.perf_counter() - start
            logger.log(BENCHMARK, f"{func.__name__} completed in {total_duration:.3f}s")
            
            for section, duration in context.sections.items():
                logger.log(BENCHMARK, f"  └─ {section}: {duration:.3f}s")
            _current_context.reset(token)
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        context = TimingContext()
        token = _current_context.set(context)
        
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            total_duration = time.perf_counter() - start
            logger.log(BENCHMARK, f"{func.__name__} completed in {total_duration:.3f}s")
            
            for section, duration in context.sections.items():
                logger.log(BENCHMARK, f"  └─ {section}: {duration:.3f}s")
            _current_context.reset(token)
    
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