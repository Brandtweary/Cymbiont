import os
import pty
import fcntl
import termios
import struct
import select
import signal
import time
import re
import shlex
import tomllib
from pathlib import Path
from typing import Optional, Tuple, List, Set

from .agent_types import ShellAccessTier

# Security-critical paths that cannot be modified in restricted modes
PROTECTED_PATHS = {
    # Core shell execution
    "src/cymbiont_shell/cymbiont_shell.py",
    "src/agents/bash_executor.py",
    
    # Core configuration
    "config.toml",
    "config.example.toml",
    
    # Virtual environment
    ".venv",
    
    # Test files
    "tests/protected_file.txt",
}

class BashExecutor:
    def __init__(self, access_tier: Optional[ShellAccessTier] = None):
        """Initialize a new bash process with PTY and security settings.
        
        Args:
            access_tier: Override the security tier from config. If None, uses config value.
        """
        self.master_fd: Optional[int] = None
        self.pid: Optional[int] = None
        
        # Load security tier from config if not overridden
        if access_tier is None:
            config_path = Path(__file__).parent.parent.parent / "config.toml"
            try:
                with open(config_path, "rb") as f:
                    config = tomllib.load(f)
                tier_num = config.get("security", {}).get("shell_access_tier", 1)
                self.access_tier = ShellAccessTier(tier_num)
            except Exception as e:
                # Default to most restrictive tier on any error
                self.access_tier = ShellAccessTier.TIER_1_PROJECT_READ
        else:
            self.access_tier = access_tier
            
        self.project_root = str(Path(__file__).parent.parent.parent)
        # Track current directory
        self.current_dir = self.project_root
        self._start_bash()
        self._apply_base_safeguards()  # Important: Apply base safeguards at startup

    def _apply_base_safeguards(self) -> None:
        """Apply base security safeguards to bash environment."""
        if self.access_tier == ShellAccessTier.TIER_5_UNRESTRICTED:
            return  # No safeguards in unrestricted mode

        # Disable dangerous shell features
        safeguards = [
            "set -f",  # Disable glob expansion
            "set -p",  # Use privileged mode
            "set -u",  # Error on undefined variables
            "shopt -u expand_aliases",  # Disable alias expansion
            "unset BASH_ENV ENV",  # Disable startup files
            "PATH=/bin:/usr/bin",  # Restrict PATH
            "readonly PATH",  # Prevent PATH modification
            "unset CDPATH",  # Disable CDPATH
            "set +o history",  # Disable command history
            "readonly SHELL",  # Prevent shell switching
            "readonly HOME",  # Prevent home directory changes
            "readonly USER",  # Prevent user changes
            "readonly LOGNAME",  # Prevent login name changes
            "set -o noclobber",  # Prevent accidental file overwrites
            "umask 022",  # Set safe file creation mask
            "set +o errexit",  # Prevent exit on error
            "set +o nounset",  # Prevent error on undefined variables
            "set +o pipefail",  # Prevent exit on pipe failure
            "set +o xtrace",  # Prevent tracing
            "set +o verbose",  # Prevent verbose mode
            "unset SHELLOPTS",  # Disable shell options
            "unset ENV",  # Disable environment file
            "unset BASH_ENV",  # Disable bash environment file
            "unset CDPATH",  # Disable CDPATH
        ]
        
        for cmd in safeguards:
            self._execute_raw(cmd)

    def _is_protected_path(self, path: str) -> bool:
        """Check if a path is protected from modification."""
        path = os.path.normpath(path)
        abs_path = path if os.path.isabs(path) else os.path.join(self.project_root, path)
        
        # Check against protected paths
        for protected in PROTECTED_PATHS:
            protected_abs = os.path.join(self.project_root, protected)
            if abs_path.startswith(protected_abs):
                return True
        return False

    def _validate_command(self, command: str) -> Tuple[bool, Optional[str]]:
        """Validate a command against security restrictions.
        
        Returns:
            Tuple of (is_allowed, error_message)
        """
        if self.access_tier == ShellAccessTier.TIER_5_UNRESTRICTED:
            return True, None

        # Split command handling pipes and chains
        cmd_parts = shlex.split(command)
        if not cmd_parts:
            return False, "Empty command"

        # Block dangerous shell features for all tiers except TIER_5
        dangerous_patterns = [
            r'\$\(', r'`',                    # Command substitution
            r'eval\s', r'exec\s',             # Command execution
            r'source\s', r'\.\s',             # File sourcing
            r'alias\s',                       # Alias creation
            r'function\s.*\{',                # Function definition
            r'.*\(\s*\)\s*\{',               # Alternative function def
            r'set\s+[+-][^f]',               # Shell option changes
            r'shopt\s', r'enable\s',          # Shell feature changes
            r'export\s+.*=',                  # Environment modifications
            r'PATH=', r'ENV=', r'BASH_ENV=',  # Path/env modifications
            r'sudo\s', r'su\s'                # Privilege elevation
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, command):
                return False, f"Blocked dangerous shell feature: {pattern}"

        # Path-based restrictions
        if self.access_tier == ShellAccessTier.TIER_1_PROJECT_READ:
            cmd_name = cmd_parts[0]
            
            # Block navigation outside project
            if cmd_name == "cd":
                if len(cmd_parts) > 1:
                    target_path = cmd_parts[1]
                    abs_target = os.path.normpath(os.path.join(self.current_dir, target_path))
                    
                    # Check if target path is within project root
                    try:
                        rel_path = os.path.relpath(abs_target, self.project_root)
                        if rel_path.startswith('..'):
                            return False, "Cannot navigate outside project directory"
                        # Update current directory if validation passes
                        self.current_dir = abs_target
                    except ValueError:
                        return False, "Cannot navigate outside project directory"
                        
            # Block read operations outside project
            read_commands = {'cat', 'less', 'head', 'tail', 'more', 'ls', 'find', 'grep'}
            if cmd_name in read_commands and len(cmd_parts) > 1:
                # Similar handling for read operations
                target_path = cmd_parts[1]
                abs_target = os.path.normpath(os.path.join(self.current_dir, target_path))
                
                try:
                    rel_path = os.path.relpath(abs_target, self.project_root)
                    if rel_path.startswith('..'):
                        return False, "Cannot read files outside project directory"
                except ValueError:
                    return False, "Cannot read files outside project directory"

        # Write operation checks
        write_commands = {'touch', 'mkdir', 'rm', 'rmdir', 'mv', 'cp', 'write',
                         'echo', 'tee', 'sed', 'awk', 'chmod', 'ln'}
        
        is_write_op = any(cmd in write_commands for cmd in cmd_parts)
        
        if is_write_op:
            if self.access_tier in [ShellAccessTier.TIER_1_PROJECT_READ, 
                                  ShellAccessTier.TIER_2_SYSTEM_READ]:
                return False, "Write operations not allowed in read-only mode"
                
            if self.access_tier in [ShellAccessTier.TIER_3_PROJECT_RESTRICTED,
                                  ShellAccessTier.TIER_4_PROJECT_WRITE]:
                # Check if operation affects protected paths
                if self.access_tier == ShellAccessTier.TIER_3_PROJECT_RESTRICTED:
                    for part in cmd_parts[1:]:
                        if self._is_protected_path(part):
                            return False, f"Cannot modify protected path: {part}"
                
                # For both TIER_3 and TIER_4, ensure writes stay within project
                for part in cmd_parts[1:]:
                    if '>' in part or '>>' in part:
                        continue  # Skip redirection operators
                    abs_target = os.path.normpath(os.path.join(self.current_dir, part))
                    try:
                        rel_path = os.path.relpath(abs_target, self.project_root)
                        if rel_path.startswith('..'):
                            return False, "Cannot write to files outside project directory"
                    except ValueError:
                        return False, "Cannot write to files outside project directory"

        return True, None

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
            
    def _execute_raw(self, command: str, timeout: float = 0.1) -> Tuple[str, str]:
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
                
            return result, ""
            
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
        
    def execute(self, command: str, timeout: float = 30.0) -> Tuple[str, str]:
        """Execute a command with security validation.
        
        Args:
            command: Command to execute
            timeout: Maximum execution time in seconds
            
        Returns:
            Tuple of (stdout, stderr)
        """
        is_allowed, error = self._validate_command(command)
        if not is_allowed:
            return "", f"Security violation: {error}"
            
        return self._execute_raw(command, timeout)

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