from shared_resources import logger, TOKEN_LOGGING
from dataclasses import dataclass, field
from contextlib import contextmanager
import inspect
from typing import List, Optional


@dataclass
class TokenLogger:
    running_token_count: int = 0
    total_token_count: int = 0
    _token_stack: List[int] = field(default_factory=list)
    
    def add_tokens(self, tokens: int) -> None:
        """Add tokens to the running total"""
        self.running_token_count += tokens
        self.total_token_count += tokens
        
    @contextmanager
    def show_tokens(self, print_tokens: bool = True, name: Optional[str] = None):
        """Context manager that shows token usage for a scope.
        Handles nested token tracking automatically.
        
        Args:
            print_tokens: Whether to print token usage when exiting the scope
            name: Optional name to identify the scope. If not provided, will try to
                 determine the calling function name."""
        if name is None:
            name = "unknown"
            # Get calling frame
            frame = inspect.currentframe()
            if frame is not None:
                try:
                    # Go up two frames: one for show_tokens, one for the context manager
                    caller = frame.f_back
                    if caller is not None and caller.f_back is not None:
                        caller = caller.f_back  # Get the actual calling frame
                        name = caller.f_code.co_name
                        # Special cases
                        if name == "handle_chat":
                            name = ""  # Empty string for handle_chat
                        elif name.startswith("do_"):
                            name = name[3:]  # Remove do_ prefix
                finally:
                    del frame  # Avoid reference cycles
                
        self._token_stack.append(self.running_token_count)
        self.running_token_count = 0
        try:
            yield
        finally:
            # Get tokens used in this scope
            scope_tokens = self.running_token_count
            # Restore parent scope's tokens
            self.running_token_count = self._token_stack.pop() + scope_tokens
            if print_tokens and TOKEN_LOGGING:
                prefix = f"Tokens used in {name}: " if name else "Tokens used: "
                logger.info(f"{prefix}{scope_tokens}")
    
    def print_total_tokens(self) -> None:
        """Print the total token count across all scopes"""
        logger.info(f"Total tokens used: {self.total_token_count}")
        
# Initialize token logger
token_logger = TokenLogger()