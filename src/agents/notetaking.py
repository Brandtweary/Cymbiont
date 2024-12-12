from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from shared_resources import logger, DATA_DIR, DEBUG_ENABLED
from utils import get_paths


def add_note(note_content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    """
    Add a note entry to the daily notes document.
    
    Args:
        note_content: The content of the note to add
        metadata: Optional dictionary of metadata tags to include with the note
    """
    try:
        # Get the daily notes directory path
        paths = get_paths(DATA_DIR)
        daily_notes_dir = paths.agent_notes_dir
        
        # Get current date and time
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        
        # Create daily notes file path
        note_file = daily_notes_dir / f"notes_{date_str}.md"
        
        # Create directory if it doesn't exist
        daily_notes_dir.mkdir(parents=True, exist_ok=True)
        
        # Format the note entry
        note_entry = f"\n\n---\n### {time_str}\n\n{note_content}\n"
        
        # Add metadata if provided
        if metadata:
            meta_str = "\nMetadata:\n" + "\n".join(f"- {k}: {v}" for k, v in metadata.items())
            note_entry += meta_str
            
        # Append the note to the file
        with open(note_file, "a", encoding="utf-8") as f:
            # If file is empty, add a header
            if note_file.stat().st_size == 0:
                f.write(f"# Daily Notes - {date_str}\n")
            f.write(note_entry)
            
        logger.info(f"Added note to {note_file}")
        
    except Exception as e:
        logger.error(f"Failed to add note: {str(e)}")
        if DEBUG_ENABLED:
            raise


def read_notes(date: Optional[str] = None) -> None:
    """
    Read notes from a specific date. If no date is provided, reads today's notes.
    
    Args:
        date: Optional date string in YYYY-MM-DD format. Defaults to current date.
    """
    try:
        # Get the daily notes directory path
        paths = get_paths(DATA_DIR)
        daily_notes_dir = paths.agent_notes_dir
        
        # Use current date if none provided
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            error_msg = f"Invalid date format: {date}. Please use YYYY-MM-DD format."
            logger.warning(error_msg)
            return
        
        # Get notes file path
        note_file = daily_notes_dir / f"notes_{date}.md"
        
        # Check if file exists
        if not note_file.exists():
            logger.warning(f"No notes found for date: {date}")
            return
            
        # Read and print notes
        with open(note_file, "r", encoding="utf-8") as f:
            notes_content = f.read()
            
        if notes_content.strip():
            logger.info(f"\n{notes_content}")
        else:
            logger.info(f"Notes file exists but is empty for date: {date}")
            
    except Exception as e:
        error_msg = f"Failed to read notes: {str(e)}"
        logger.error(error_msg)
        if DEBUG_ENABLED:
            raise
