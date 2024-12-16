import asyncio
import hashlib
import time
import functools
from typing import Callable, Any, Dict, Optional, Generator, AsyncGenerator, List
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from collections import defaultdict
from shared_resources import logger, FILE_RESET, DELETE_LOGS, DEBUG_ENABLED, Paths, ShellAccessTier
from pathlib import Path
import json
from cymbiont_logger.logger_types import LogLevel
from llms.llm_types import ChatMessage
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
            logger.log(LogLevel.BENCHMARK, f"{func.__name__} completed in {total_duration:.3f}s")
            
            for section, duration in context.sections.items():
                logger.log(LogLevel.BENCHMARK, f"  └─ {section}: {duration:.3f}s")
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
            logger.log(LogLevel.BENCHMARK, f"{func.__name__} completed in {total_duration:.3f}s")
            
            for section, duration in context.sections.items():
                logger.log(LogLevel.BENCHMARK, f"  └─ {section}: {duration:.3f}s")
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
                raise
    
    # Handle folders
    for folder_path in paths.processed_dir.glob("*"):
        if folder_path.is_dir():
            try:
                shutil.move(str(folder_path), str(paths.docs_dir / folder_path.name))
                logger.debug(f"Moved folder {folder_path.name} back to input_documents")
            except Exception as e:
                logger.error(f"Failed to move folder {folder_path.name}: {str(e)}")
                raise

def clean_directories(paths: Paths) -> None:
    """Remove all files from chunks directory"""
    for chunk_file in paths.chunks_dir.glob("*.txt"):
        chunk_file.unlink()

def setup_directories(base_dir: Path) -> Paths:
    """Create directory structure and return paths"""
    try:
        paths = get_paths(base_dir)
        
        # Create directories first - iterate over the actual Path objects
        for dir_path in paths._asdict().values():
            if isinstance(dir_path, Path):  # Skip base_dir since it might be a string
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
        agent_workspace_dir = base_dir / "agent_workspace"
        return Paths(
            base_dir=base_dir,
            docs_dir=base_dir / "input_documents",
            processed_dir=base_dir / "processed_documents",
            chunks_dir=base_dir / "chunks",
            index_dir=base_dir / "indexes",
            logs_dir=base_dir / "logs",
            inert_docs_dir=base_dir / "inert_documents",
            snapshots_dir=base_dir / "snapshots",
            agent_workspace_dir=agent_workspace_dir,
            daily_notes_dir=agent_workspace_dir / "daily_notes"
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
            if DEBUG_ENABLED:
                raise

def convert_messages_to_string(
    messages: List[ChatMessage], 
    word_limit: Optional[int] = 300,
    truncate_last: bool = False
) -> str:
    def truncate_message(text: str, limit: Optional[int]) -> str:
        if not limit:
            return text
        # Split into lines first to preserve structure
        lines = text.split('\n')
        truncated_lines = []
        words_remaining = limit
        
        for line in lines:
            words = line.split()
            if words_remaining <= 0:
                break
            if len(words) <= words_remaining:
                truncated_lines.append(line)
                words_remaining -= len(words)
            else:
                truncated_lines.append(' '.join(words[:words_remaining]) + '...')
                break
                
        return '\n'.join(truncated_lines)
    
    formatted_messages = []
    for i, msg in enumerate(messages):
        should_truncate = word_limit and (
            (not truncate_last and i < len(messages) - 1) or
            (truncate_last)
        )
        content = truncate_message(msg.content, word_limit if should_truncate else None)
        
        # Strip any trailing newlines from the content
        content = content.rstrip('\n')
        
        prefix = 'SYSTEM' if msg.role == 'system' else msg.name or msg.role.upper()
        formatted_messages.append(f"{prefix}: {content}")
    
    # Join messages with single newlines and clean up any resulting double newlines
    return '\n'.join(formatted_messages).replace('\n\n\n', '\n\n')

def get_shell_access_tier_documentation(tier: ShellAccessTier) -> str:
    """Get a human-readable description of shell access tier constraints.
    
    Args:
        tier: The ShellAccessTier enum value
        
    Returns:
        A string describing the access tier and its constraints
    """
    descriptions = {
        ShellAccessTier.TIER_1_PROJECT_READ: 
            "Your current shell access tier is: Project Read-Only (Tier 1)\n"
            "You can only read files within the Cymbiont project directory. You cannot execute files or navigate outside the project.",
            
        ShellAccessTier.TIER_2_SYSTEM_READ:
            "Your current shell access tier is: System Read-Only (Tier 2)\n"
            "You can read files anywhere on the system but cannot write or execute files.",
            
        ShellAccessTier.TIER_3_PROJECT_RESTRICTED_WRITE:
            "Your current shell access tier is: Project Restricted Write (Tier 3)\n" 
            "You can read system files and write to your agent workspace, but cannot execute files.",
            
        ShellAccessTier.TIER_4_PROJECT_WRITE_EXECUTE:
            "Your current shell access tier is: Project Write/Execute (Tier 4)\n"
            "You can read system files and write/execute within the Cymbiont project directory.",
            
        ShellAccessTier.TIER_5_UNRESTRICTED:
            "Your current shell access tier is: Unrestricted (Tier 5)\n"
            "You can use all read/write/execute commands."
    }
    return descriptions[tier]