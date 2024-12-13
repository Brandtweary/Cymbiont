import os
import pty
import fcntl
import termios
import struct
import select
import signal
import time
import re
from typing import Optional, Tuple

class BashExecutor:
    def __init__(self):
        """Initialize a new bash process with PTY."""
        self.master_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self._start_bash()
        
    def _start_bash(self) -> None:
        """Start a new bash process with PTY."""
        # Fork a new process with PTY
        pid, master_fd = pty.fork()
        
        if pid == 0:  # Child process
            # Execute bash in the child process
            os.execvp('bash', ['bash'])
        else:  # Parent process
            self.master_fd = master_fd
            self.pid = pid
            
            # Set non-blocking I/O on the master file descriptor
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            
            # Set terminal size
            self._set_terminal_size(24, 80)
            
            # Clear initial prompt
            self._read_until_prompt()
            
    def _set_terminal_size(self, rows: int, cols: int) -> None:
        """Set the terminal size for the PTY."""
        if self.master_fd is not None:
            size = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size)

    def _filter_ansi_escapes(self, text: str) -> str:
        """Filter out ANSI escape sequences that could affect the parent terminal state.
        Preserves color and basic formatting sequences."""
        # Remove only specific escape sequences that affect terminal state
        text = re.sub(r'\x1B\[\?1049[hl]', '', text)  # Alternate screen buffer
        text = re.sub(r'\x1B\[\?1000[hl]', '', text)  # Mouse tracking
        text = re.sub(r'\x1B\[\?1002[hl]', '', text)  # Mouse tracking
        text = re.sub(r'\x1B\[\?1006[hl]', '', text)  # Mouse tracking
        text = re.sub(r'\x1B\[\?25[hl]', '', text)    # Cursor visibility
        text = re.sub(r'\x1B\[\?47[hl]', '', text)    # Alternate screen buffer (older terminals)
        text = re.sub(r'\x1B\[\?1047[hl]', '', text)  # Alternate screen buffer (older terminals)
        text = re.sub(r'\x1B\[\?2004[hl]', '', text)  # Bracketed paste mode
        
        # Remove cursor movement and screen clearing sequences
        text = re.sub(r'\x1B\[\d*[ABCDEFGJKST]', '', text)  # Cursor movement and clear screen parts
        text = re.sub(r'\x1B\[\d*[HJ]', '', text)           # Cursor position and clear screen
        
        return text
            
    def _read_until_prompt(self, timeout: float = 0.1) -> str:
        """Read output until we see a shell prompt."""
        output = []
        start_time = time.time()
        prompt_pattern = r'[^>]*@[^>]*:[^>]*[$#] '  # Matches bash-style prompts
        
        # Build up partial lines
        partial = ""
        
        while True:
            try:
                if time.time() - start_time > timeout:
                    break
                    
                r, _, _ = select.select([self.master_fd], [], [], 0.1)
                if not r:
                    continue
                    
                data = os.read(self.master_fd, 1024).decode()  # type: ignore
                if not data:
                    break
                    
                # Filter escape sequences before adding to output
                data = self._filter_ansi_escapes(data)
                partial += data
                
                # Check if we have a complete prompt
                if re.search(prompt_pattern, partial.split('\n')[-1]):
                    break
                    
            except (OSError, BlockingIOError):
                break
                
        return partial
            
    def execute(self, command: str, timeout: float = 0.1) -> Tuple[str, int]:
        """Execute a command in the bash process."""
        if self.master_fd is None:
            raise RuntimeError("Bash process not initialized")
            
        old_settings = None
        try:
            # Save terminal settings
            old_settings = termios.tcgetattr(0)
            
            # Add newline if not present
            if not command.endswith('\n'):
                command += '\n'
                
            # Write command to bash process
            os.write(self.master_fd, command.encode())
            
            # Read until we get the full output including next prompt
            output = self._read_until_prompt(timeout)
            
            # Split into lines and clean up
            lines = output.split('\n')
            
            # Remove lines containing prompts and the command echo
            clean_lines = []
            prompt_pattern = r'[^>]*@[^>]*:[^>]*[$#] '
            for line in lines:
                # Skip prompt lines and command echo
                if re.search(prompt_pattern, line) or line.strip() == command.strip():
                    continue
                if line.strip():
                    clean_lines.append(line)
            
            result = '\n'.join(clean_lines)
            
            # For interactive commands, ensure terminal is reset
            if command.strip().split()[0] in ['less', 'vim', 'nano', 'htop', 'top', 'man']:
                # Send ctrl-C first in case program is still running
                os.write(self.master_fd, b'\x03')
                time.sleep(0.1)
                
                # Reset terminal
                os.write(self.master_fd, 'tput reset\n'.encode())
                self._read_until_prompt(timeout)
                
                # Restore terminal settings
                if old_settings is not None:
                    try:
                        termios.tcsetattr(0, termios.TCSADRAIN, old_settings)
                    except:
                        pass
                
            return result, 0
            
        except Exception as e:
            # If anything goes wrong, try to reset the terminal
            try:
                os.write(self.master_fd, b'\x03')  # Send ctrl-C
                time.sleep(0.1)
                os.write(self.master_fd, 'tput reset\n'.encode())
                self._read_until_prompt(timeout)
                if old_settings is not None:
                    try:
                        termios.tcsetattr(0, termios.TCSADRAIN, old_settings)
                    except:
                        pass
            except:
                pass
            raise
        
    def close(self) -> None:
        """Clean up the bash process."""
        if self.pid is not None:
            try:
                # Try to reset terminal before closing
                if self.master_fd is not None:
                    try:
                        os.write(self.master_fd, b'\x03')  # Send ctrl-C
                        time.sleep(0.1)
                        os.write(self.master_fd, 'tput reset\n'.encode())
                        self._read_until_prompt(0.1)
                    except:
                        pass
                os.kill(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
                
        if self.master_fd is not None:
            os.close(self.master_fd)
            self.master_fd = None
            self.pid = None
            
    def __del__(self):
        """Ensure process cleanup on object destruction."""
        self.close()