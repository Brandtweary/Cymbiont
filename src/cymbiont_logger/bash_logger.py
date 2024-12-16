from datetime import datetime
from pathlib import Path
from typing import Optional
from utils import get_paths
from shared_resources import DATA_DIR

class BashLogger:
    """Logs bash commands and output to a session-specific file."""
    
    def __init__(self):
        paths = get_paths(DATA_DIR)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = paths.logs_dir / f"bash_{timestamp}.log"
        paths.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Create the log file and write session start
        with open(self.log_file, 'w') as f:
            start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{start_time}] Bash session started\n")
            f.write("-" * 80 + "\n")
    
    def log_command(self, command: str, output: Optional[str] = None) -> None:
        """Write a bash command and its output to the log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_file, 'a') as f:
            f.write(f"[{timestamp}] Command: {command.strip()}\n")
            if output:
                f.write(f"[{timestamp}] Output:\n{output}\n")
            f.write("-" * 80 + "\n")
