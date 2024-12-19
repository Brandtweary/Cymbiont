from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.application import get_app
from prompt_toolkit.formatted_text.base import StyleAndTextTuples
from typing import Any, Union, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .cymbiont_shell import CymbiontShell

class LogAwareSession(PromptSession):
    """A PromptSession that properly handles log output by repositioning the prompt."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shell: Optional['CymbiontShell'] = None  # Will be set by shell
    
    def clear_prompt(self) -> None:
        """Clear the current prompt from the screen"""
        app = get_app()
        if not app.output:
            return
            
        # Move up and clear the prompt line
        output = app.output
        output.cursor_up(1)
        output.erase_down()
        output.flush()
    
    def redraw_prompt(self) -> None:
        """Tell prompt_toolkit to redraw the prompt"""
        app = get_app()
        if not app.output:
            return
        app.invalidate()
    
    async def prompt_async(self, *args, **kwargs) -> Any:
        """Override prompt_async to handle log output while preserving all original parameters."""
        # Get input from user, passing through all original parameters
        with patch_stdout(raw=True):
            result = await super().prompt_async(*args, **kwargs)
        
        return result
