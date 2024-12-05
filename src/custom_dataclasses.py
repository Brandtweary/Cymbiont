import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Dict, Literal, Optional, NamedTuple, Set, Union, Callable
from pathlib import Path
from constants import ToolName, CommandArgType
from process_log import ProcessLog


MessageRole = Literal["user", "assistant", "system"]

@dataclass
class ChatMessage:
    role: MessageRole
    content: str
    name: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class Document:
    """Represents a processed document"""
    doc_id: str
    filename: str
    processed_at: float
    metadata: Dict
    tags: Optional[List[str]] = None
    folder_id: Optional[str] = None

@dataclass
class Chunk:
    """A chunk of text with references"""
    chunk_id: str
    doc_id: str
    text: str
    position: int
    metadata: Dict
    tags: Optional[List[str]] = None

class Paths(NamedTuple):
    """Paths for data storage"""
    base_dir: Path
    docs_dir: Path
    processed_dir: Path
    chunks_dir: Path
    index_dir: Path
    logs_dir: Path
    inert_docs_dir: Path
    snapshots_dir: Path

@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    timestamp: float

@dataclass
class SystemMessagePart:
    header: str
    content: str
    required_params: List[str]

@dataclass
class SystemPromptPartInfo:
    """Info for a single system prompt part"""
    toggled: bool
    index: int

@dataclass
class SystemPromptPartsData:
    """Data structure for system prompt parts configuration.
    Each part has a toggle state and an index for ordering."""
    parts: Dict[str, SystemPromptPartInfo]

    def __post_init__(self):
        # Validate that all values are SystemPromptPartInfo
        for part_name, part_info in self.parts.items():
            if not isinstance(part_info, SystemPromptPartInfo):
                if isinstance(part_info, dict):
                    self.parts[part_name] = SystemPromptPartInfo(**part_info)
                else:
                    raise ValueError(f"Invalid part info for {part_name}: {part_info}")

@dataclass
class CommandData:
    """Data structure for shell command metadata"""
    callable: Callable
    takes_args: bool
    arg_types: Optional[List[CommandArgType]] = None

@dataclass
class ToolLoopData:
    """Data for managing tool loops."""
    loop_type: str
    loop_message: str
    active: bool = True
    available_tools: Set[ToolName] = field(default_factory=set)
    loop_tokens: int = 0
    system_prompt_parts: Optional[SystemPromptPartsData] = None

@dataclass
class APICall:
    model: str
    messages: List[ChatMessage]
    system_message: str
    timestamp: float
    mock: bool
    mock_tokens: Optional[int]
    expiration_counter: int
    future: asyncio.Future[Dict[str, Any]]
    provider: str
    max_completion_tokens: int
    temperature: float = 0.7
    process_log: Optional[ProcessLog] = None
    tools: Optional[Set[ToolName]] = None
    system_prompt_parts: Optional[SystemPromptPartsData] = None
    tool_choice: Literal["auto", "required", "none"] = "auto"