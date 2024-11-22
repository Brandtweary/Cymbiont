import asyncio
import hashlib
import time
import functools
from typing import Callable, Any, Dict, Optional, Generator, AsyncGenerator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from collections import defaultdict
from shared_resources import logger, FILE_RESET, DELETE_LOGS
from pathlib import Path
import json
from logging_config import BENCHMARK
from custom_dataclasses import Paths
import shutil

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

def reset_files(paths: Paths) -> None:
    """Clear indices, move processed documents back, and clean generated files"""
    clear_indices(paths)
    move_processed_to_documents(paths)
    clean_directories(paths)

def clear_indices(paths: Paths) -> None:
    """Clear all index files when in file reset mode"""
    index_files = [
        paths.index_dir / "documents.json",
        paths.index_dir / "chunks.json",
        paths.index_dir / "folders.json"
    ]
    for index_file in index_files:
        save_index({}, index_file)

def move_processed_to_documents(paths: Paths) -> None:
    """Move processed files and folders back to documents directory in debug mode"""
    # Handle individual files
    for file_path in paths.processed_dir.glob("*.*"):
        if file_path.suffix.lower() in ['.txt', '.md']:
            try:
                shutil.move(str(file_path), str(paths.docs_dir / file_path.name))
                logger.debug(f"Moved file {file_path.name} back to input_documents")
            except Exception as e:
                logger.error(f"Failed to move file {file_path.name}: {str(e)}")
    
    # Handle folders
    for folder_path in paths.processed_dir.glob("*"):
        if folder_path.is_dir():
            try:
                shutil.move(str(folder_path), str(paths.docs_dir / folder_path.name))
                logger.debug(f"Moved folder {folder_path.name} back to input_documents")
            except Exception as e:
                logger.error(f"Failed to move folder {folder_path.name}: {str(e)}")

def clean_directories(paths: Paths) -> None:
    """Remove all files from chunks directory"""
    for chunk_file in paths.chunks_dir.glob("*.txt"):
        chunk_file.unlink()

def setup_directories(base_dir: Path) -> Paths:
    """Create directory structure and return paths"""
    try:
        paths = get_paths(base_dir)
        
        # Create directories first
        for dir_path in paths:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Failed to create directory {dir_path}: {str(e)}")
                raise
        
        # Reset files if needed
        if FILE_RESET:
            logger.info("File reset mode on: resetting processed files")
            reset_files(paths)
            
        return paths
    except Exception as e:
        logger.error(f"Directory setup failed: {str(e)}")
        raise

def get_paths(base_dir: Path) -> Paths:
    """Get directory paths for the specified base directory"""
    try:
        return Paths(
            base_dir=base_dir,
            docs_dir=base_dir / "input_documents",
            processed_dir=base_dir / "processed_documents",
            chunks_dir=base_dir / "chunks",
            index_dir=base_dir / "indexes",
            logs_dir=base_dir / "logs",
            inert_docs_dir=base_dir / "inert_documents",
            snapshots_dir=base_dir / "snapshots"
        )
    except Exception as e:
        logger.error(f"Failed to get paths for {base_dir}: {str(e)}")
        raise

def delete_logs(base_dir: Path) -> None:
    """Delete all log files if DELETE_LOGS is True"""
    if not DELETE_LOGS:
        return
        
    paths = get_paths(base_dir)
    if not paths.logs_dir.exists():
        return
        
    logger.info("Deleting log files")
    for log_file in paths.logs_dir.glob("*.log"):  # Only target .log files
        try:
            log_file.unlink()
        except Exception as e:
            logger.error(f"Failed to delete log file {log_file}: {str(e)}")