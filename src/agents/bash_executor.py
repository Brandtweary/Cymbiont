import os
import sys
import pty
import fcntl
import termios
import struct
import select
import signal
import time
import re
import shlex
from pathlib import Path
from typing import Optional, Tuple
import pwd
import grp
from .agent_types import ShellAccessTier, RestrictedUser
from utils import get_paths
from shared_resources import DATA_DIR, logger, SHELL_ACCESS_TIER
import threading
from cymbiont_logger.bash_logger import BashLogger

# Get paths for data directories
paths = get_paths(DATA_DIR)
AGENT_WORKSPACE_DIR = str(paths.agent_workspace_dir)

def check_restricted_user_exists(username: str) -> bool:
    """Check if a restricted user exists on the system."""
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False

def get_setup_instructions() -> str:
    """Get instructions for setting up restricted users."""
    return (
        "Enhanced security requires restricted users to be set up.\n"
        "To enable this feature, run:\n"
        "    sudo ./scripts/setup_restricted_user.sh\n"
        "Or re-run bootstrap.sh and select 'y' when prompted for enhanced security."
    )

class BashExecutor:
    def __init__(self, access_tier: Optional[ShellAccessTier] = None):
        """Initialize a new bash process with PTY and security settings.
        
        Args:
            access_tier: Override the security tier from config. If None, uses config value.
        """
        # Load security tier from config if not overridden
        self.access_tier = access_tier or SHELL_ACCESS_TIER
        
        # Check for restricted user if needed
        self.use_restricted_user = False
        self.restricted_username: Optional[str] = None
        
        if self.access_tier == ShellAccessTier.TIER_1_PROJECT_READ:
            self.restricted_username = RestrictedUser.PROJECT_READ.value
        elif self.access_tier == ShellAccessTier.TIER_2_SYSTEM_READ:
            self.restricted_username = RestrictedUser.SYSTEM_READ.value
        elif self.access_tier == ShellAccessTier.TIER_3_PROJECT_RESTRICTED_WRITE:
            self.restricted_username = RestrictedUser.PROJECT_RESTRICTED_WRITE.value
        elif self.access_tier == ShellAccessTier.TIER_4_PROJECT_WRITE_EXECUTE:
            self.restricted_username = RestrictedUser.PROJECT_WRITE_EXECUTE.value
            
        if self.restricted_username:
            if check_restricted_user_exists(self.restricted_username):
                self.use_restricted_user = True
            else:
                logger.warning("Running in fallback mode without OS-level isolation.")
                logger.warning(get_setup_instructions())

        # Initialize other attributes
        self.master_fd = None
        self.bash_pid = None
        self.project_root = str(Path(__file__).parent.parent.parent)
        self.current_dir = self.project_root
        self.blocked_commands = 0
        self.bash_logger = BashLogger()
        
        # Start bash process
        self._start_bash()
        
        # Apply safeguards only if not in unrestricted mode
        if self.access_tier != ShellAccessTier.TIER_5_UNRESTRICTED:
            # Temporarily elevate to run safeguards
            original_tier = self.access_tier
            self.access_tier = ShellAccessTier.TIER_5_UNRESTRICTED
            self._apply_base_safeguards()
            self.access_tier = original_tier
        
        self._start_reset_timer()

    def _apply_base_safeguards(self) -> None:
        """Apply base security safeguards to bash environment."""
        # Set up minimal shell environment
        shell_env = [
            # Enable alias expansion
            "shopt -s expand_aliases",
            
            # Common color and formatting aliases
            "alias ls='ls --color=auto'",
            "alias grep='grep --color=auto'",
            "alias fgrep='fgrep --color=auto'",
            "alias egrep='egrep --color=auto'",
            "alias diff='diff --color=auto'",
            "alias ip='ip --color=auto'",
            
            # Common directory navigation
            "alias ll='ls -alF'",
            "alias la='ls -A'",
            "alias l='ls -CF'",
            
            # Set common environment variables
            "export TERM=xterm-256color",  # Enable 256 color support
            "export COLORTERM=truecolor",  # Enable true color support if available
            "export CLICOLOR=1",          # Enable colors for BSD tools
            
            # Core security settings
            "set -p",  # Use privileged mode for secure env
            "set -u",  # Error on undefined variables
            
            # Environment restrictions
            "PATH=/bin:/usr/bin:/usr/local/bin",  # Set safe PATH with necessary dirs
            "readonly PATH",  # Prevent PATH modification
            "readonly SHELL",  # Prevent shell switching
            "readonly USER",  # Prevent user changes
            "readonly LOGNAME",  # Prevent login name changes
            
            # File safety
            "set -o noclobber",  # Prevent accidental file overwrites
            "umask 022",  # Set safe file creation mask
            
            # Clean environment
            "unset BASH_ENV ENV",  # Disable startup files
            "unset CDPATH",  # Disable CDPATH
            
            # Security hardening
            "set +o history",  # Disable command history
            "set +o xtrace",  # Prevent tracing
            "set +o verbose",  # Prevent verbose mode
        ]
        
        for cmd in shell_env:
            output, _ = self._execute_raw(cmd)

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
                    except ValueError:
                        return False, "Cannot navigate outside project directory"
                    
                    # Only update current_dir if directory exists
                    if not os.path.isdir(abs_target):
                        return False, f"Directory does not exist: {target_path}"
                    
                    # Update current directory if validation passes
                    self.current_dir = abs_target
                        
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
        filesystem_write_commands = {'touch', 'mkdir', 'rm', 'rmdir', 'mv', 'cp', 'write',
                                   'tee', 'sed', 'awk', 'chmod', 'ln'}
        
        is_write_op = any(cmd in filesystem_write_commands for cmd in cmd_parts)
        
        if is_write_op:
            if self.access_tier in [ShellAccessTier.TIER_1_PROJECT_READ, 
                                  ShellAccessTier.TIER_2_SYSTEM_READ]:
                return False, "Write operations not allowed in read-only mode"
            
            if self.access_tier in [ShellAccessTier.TIER_3_PROJECT_RESTRICTED_WRITE,
                                  ShellAccessTier.TIER_4_PROJECT_WRITE_EXECUTE]:
                # For TIER_3, only allow writes in agent_workspace_dir
                if self.access_tier == ShellAccessTier.TIER_3_PROJECT_RESTRICTED_WRITE:
                    for part in cmd_parts[1:]:
                        if '>' in part or '>>' in part or part.startswith('-'):
                            continue  # Skip redirection operators and command flags
                        abs_target = os.path.normpath(os.path.join(self.current_dir, part))
                        if not str(abs_target).startswith(AGENT_WORKSPACE_DIR):
                            return False, f"Write operation not allowed outside of {AGENT_WORKSPACE_DIR}"
            
                # For both TIER_3 and TIER_4, ensure writes stay within project
                for part in cmd_parts[1:]:
                    if '>' in part or '>>' in part or part.startswith('-'):
                        continue  # Skip redirection operators and command flags
                    abs_target = os.path.normpath(os.path.join(self.current_dir, part))
                    try:
                        rel_path = os.path.relpath(abs_target, self.project_root)
                        if rel_path.startswith('..'):
                            return False, "Cannot write to files outside project directory"
                    except ValueError:
                        return False, "Cannot write to files outside project directory"
                    
        # Block file execution in restricted tiers (1-3)
        if self.access_tier in [ShellAccessTier.TIER_1_PROJECT_READ,
                              ShellAccessTier.TIER_2_SYSTEM_READ,
                              ShellAccessTier.TIER_3_PROJECT_RESTRICTED_WRITE]:
            # Block direct file execution
            if cmd_parts[0].startswith('./') or '/' in cmd_parts[0]:
                return False, "Executing files is not allowed in restricted tiers"
            
            # Block execution via common commands
            execute_commands = {'bash', 'sh', 'python', 'python3', 'perl', 'ruby', 'node', 'npm', 'yarn'}
            if cmd_parts[0] in execute_commands:
                return False, "Executing scripts is not allowed in restricted tiers"
        
        return True, None

    def _switch_to_user(self, username: str) -> None:
        """Switch the current process to run as a different user.
        
        Args:
            username: Username to switch to
        """
        try:
            user_info = pwd.getpwnam(username)
            # Set supplementary groups
            groups = [g.gr_gid for g in grp.getgrall() if username in g.gr_mem]
            os.setgroups(groups)
            # Set GID first (required for non-root)
            os.setgid(user_info.pw_gid)
            # Set UID
            os.setuid(user_info.pw_uid)
        except Exception as e:
            raise RuntimeError(f"Failed to switch to user {username}: {str(e)}")

    def _start_bash(self) -> None:
        """Start a new bash process with PTY."""
        # Fork a new process with PTY
        pid, master_fd = pty.fork()
        
        if pid == 0:  # Child process
            try:
                if self.use_restricted_user and self.restricted_username is not None:
                    # Start bash as restricted user
                    os.execvp('sudo', ['sudo', '-n', '-u', self.restricted_username, '/bin/bash'])
                else:
                    # Normal unrestricted mode
                    os.execvp('bash', ['bash'])
            except Exception as e:
                print(f"Child process failed: {e}", file=sys.stderr)
                os._exit(1)
        else:  # Parent process
            self.master_fd = master_fd
            self.bash_pid = pid
            
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

    def _filter_problematic_ansi_escapes(self, text: str) -> str:
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
        
        # Only remove specific cursor movement commands, preserve colors
        text = re.sub(r'\x1B\[\d*[ABCD]', '', text)  # Cursor movement
        text = re.sub(r'\x1B\[\d*[EF]', '', text)    # Cursor next/previous line
        text = re.sub(r'\x1B\[\d*[GH]', '', text)    # Cursor position
        text = re.sub(r'\x1B\[\d*[JK]', '', text)    # Clear screen/line parts
        
        return text

    def _strip_all_ansi_escapes(self, text: str) -> str:
        """Remove all ANSI escape sequences and control characters from text."""
        # First strip ANSI escape sequences
        text = re.sub(r'\x1B\[[^m]*m|\x1B\[[^\x40-\x7E]*[\x40-\x7E]', '', text)
        # Then strip control characters like \r
        text = re.sub(r'[\r\n\t\x0b\x0c]', '', text)
        return text
            
    def _read_until_prompt(self, timeout: float = 0.1) -> str:
        """Read output until we see a shell prompt."""
        output = []
        start_time = time.time()
        prompt_pattern = r'[^>]*@[^>]*:[^>]*[$#] '  # Matches bash-style prompts
        
        # Build up partial lines
        partial = ""
        filtered_partial = ""  # For prompt detection only
        
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
                    
                # Keep original data for output
                partial += data
                # Filter only for prompt detection
                filtered_data = self._filter_problematic_ansi_escapes(data)
                filtered_partial += filtered_data
                
                # Check if we have a complete prompt using filtered data
                if re.search(prompt_pattern, filtered_partial.split('\n')[-1]):
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
            
            # Split into lines, preserving the \r characters
            lines = output.split('\n')
            clean_lines = []
            prompt_pattern = r'[^>]*@[^>]*:[^>]*[$#] '
            
            for i, line in enumerate(lines):
                # Split on \r and take the last non-empty part
                parts = [p for p in line.split('\r') if p.strip()]
                if not parts:
                    continue
                    
                # Strip ANSI from the last part
                clean_line = self._strip_all_ansi_escapes(parts[-1])
                
                # Skip prompt lines, command echo, and single quotes/double quotes
                if (re.search(prompt_pattern, clean_line) or 
                    clean_line.strip() == command.strip() or 
                    clean_line.strip() in ['"', "'", '""', "''"]):
                    continue
                
                if clean_line.strip():
                    clean_lines.append(clean_line)
            
            result = '\n'.join(clean_lines)
            
            # Log command and output
            self.bash_logger.log_command(command, result)
            
            # For interactive commands, ensure terminal is reset
            if command.strip().split()[0] in ['less', 'vim', 'nano', 'htop', 'top', 'man']:
                # Send ctrl-C first in case program is still running
                os.write(self.master_fd, b'\x03')
                time.sleep(0.1)
                
                # Reset only alternate screen buffer and scrolling mode
                os.write(self.master_fd, b'\x1B[?1049l\x1B[?47l\x1B[?1047l')
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
                # Reset only alternate screen buffer and scrolling mode
                os.write(self.master_fd, b'\x1B[?1049l\x1B[?47l\x1B[?1047l')
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
            self.blocked_commands += 1
            if self.blocked_commands >= 10:
                logger.critical("Too many blocked commands - forcing shutdown for security")
                raise SystemExit("Security shutdown: Too many blocked commands")
            elif self.blocked_commands >= 9:
                logger.critical("Too many blocked commands - shutdown imminent")
            elif self.blocked_commands >= 4:
                logger.warning(f"Warning: too many blocked commands - possible security issue")
            return "", f"Security violation: {error}"
            
        return self._execute_raw(command, timeout)

    def reset_kill_switch_counter(self):
        """Reset the blocked commands counter. Useful for testing or when changing security contexts."""
        self.blocked_commands = 0

    def _start_reset_timer(self):
        """Start a timer thread that resets the kill switch counter every hour."""
        self._timer_active = True
        self._timer_thread = threading.Thread(target=self._reset_timer_loop, daemon=True)
        self._timer_thread.start()

    def _reset_timer_loop(self):
        """Timer loop that resets the kill switch counter every hour."""
        while self._timer_active:
            time.sleep(3600)  # Sleep for 1 hour
            if self._timer_active:  # Check again in case we were closed during sleep
                self.reset_kill_switch_counter()

    def close(self) -> None:
        """Clean up the bash process."""
        self._timer_active = False  # Stop the timer thread
        if self.bash_pid is not None:
            try:
                # Try to reset terminal before closing
                if self.master_fd is not None:
                    try:
                        os.write(self.master_fd, b'\x03')  # Send ctrl-C
                        time.sleep(0.1)
                        # Reset only alternate screen buffer and scrolling mode
                        os.write(self.master_fd, b'\x1B[?1049l\x1B[?47l\x1B[?1047l')
                        self._read_until_prompt(0.1)
                    except:
                        pass
                os.kill(self.bash_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
                
        if self.master_fd is not None:
            os.close(self.master_fd)
            self.master_fd = None
            self.bash_pid = None
            
    def __del__(self):
        """Ensure process cleanup on object destruction."""
        if hasattr(self, 'master_fd') and hasattr(self, 'bash_pid'):
            self.close()