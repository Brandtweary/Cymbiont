from enum import Enum
from dataclasses import dataclass
from typing import Callable, Optional, List


class CommandArgType(Enum):
    """Types of arguments that shell commands can accept"""
    FILENAME = "filename"      # File name
    ENTRY = "entry"       # File or folder name
    TEXT = "text"             # Free-form text
    FLAG = "flag"             # Command flag (e.g., -v)
    COMMAND = "command"       # Command name (for help command)

@dataclass
class CommandData:
    """Data structure for shell command metadata"""
    callable: Callable
    takes_args: bool
    arg_types: Optional[List[CommandArgType]] = None
    needs_shell: bool = False