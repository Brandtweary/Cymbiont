import math
import asyncio
import sys
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.formatted_text.base import StyleAndTextTuples
from typing import Tuple, Optional, cast
from agents import agent
from agents.tool_helpers import register_tools
from shared_resources import USER_NAME, AGENT_NAME, logger, DEBUG_ENABLED, AGENT_ACTIVATION_MODE, console_handler, SHELL_ACCESS_TIER
from cymbiont_logger.token_logger import token_logger
from agents.chat_history import ChatHistory, setup_chat_history_handler
from cymbiont_logger.logger_types import LogLevel
from agents.agent import Agent, DEFAULT_SYSTEM_PROMPT_PARTS
from agents.chat_agent import ChatAgent
from agents.tool_helpers import format_all_tool_schemas
from llms.system_prompt_parts import SYSTEM_MESSAGE_PARTS
from llms.keyword_router import KeywordRouter
from .command_completer import CommandCompleter
from .command_metadata import create_commands
from agents.agent_types import ActivationMode
from prompt_toolkit.patch_stdout import patch_stdout
from agents.bash_executor import BashExecutor
from utils import get_shell_access_tier_documentation
import sys
from prompt_toolkit.application import get_app


class CymbiontShell:
    def __init__(self) -> None:
        self.chat_history = ChatHistory()
        self.test_successes: int = 0
        self.test_failures: int = 0
        self.bash_executor: Optional[BashExecutor] = None
        self.log_queue = asyncio.Queue()  # Queue for log messages
        self._needs_new_prompt = False  # Flag for new prompt
        self._exit_type: Optional[str] = None  # Track how we're exiting
        
        # Initialize agents
        register_tools()
        self.chat_agent = ChatAgent(
            self.chat_history,
            agent_name=AGENT_NAME,
            activation_mode=ActivationMode.CONTINUOUS if AGENT_ACTIVATION_MODE == "continuous" else ActivationMode.CHAT
        )
        self.chat_agent_task: Optional[asyncio.Task] = None
        
        # Connect chat history to logger
        setup_chat_history_handler(logger, self.chat_history)
        
        # Connect shell to console handler
        if console_handler:
            console_handler.shell = self
        
        # Store command metadata
        self.commands = create_commands(
            do_exit=self.do_exit,
            do_help=self.do_help,
            do_hello_world=self.do_hello_world,
            do_print_total_tokens=self.do_print_total_tokens,
            do_bash=self.do_bash
        )
        
        # Initialize keyword router with command names
        self.keyword_router = KeywordRouter(shell_commands=list(self.commands.keys()))
        
        # Generate command documentation and format shell_command_docs part
        shell_doc = self.generate_command_documentation()
        SYSTEM_MESSAGE_PARTS['shell_command_docs'].content = \
            SYSTEM_MESSAGE_PARTS['shell_command_docs'].content.format(
                shell_command_documentation=shell_doc
            )
        
        # Format tool schemas with dynamic content
        format_all_tool_schemas(
            command_metadata=self.commands,
            system_prompt_parts=DEFAULT_SYSTEM_PROMPT_PARTS,
            tools=self.chat_agent.default_tools
        )
        
        # Initialize command completer
        self.completer = CommandCompleter(self.commands)
        
        # Create prompt session with styling
        style = Style.from_dict({
            'user': '#0080FE',    # Deep blue
            'command': 'ansigreen',
            'agent': '#00FFFF',   # Bright cyan
        })
        
        self.session = PromptSession(
            style=style,
            message=self.get_prompt,
            completer=self.completer
        )
        #self.session.shell = cast('CymbiontShell', self)  # Connect shell to session
        
        # Connect shell to console handler
        if console_handler:
            console_handler.set_shell(self)
        
        # Log shell startup
        logger.log(LogLevel.SHELL, "Cymbiont shell started")
        logger.info("Welcome to Cymbiont. Type help or ? to list commands.")
    
    def get_prompt(self) -> FormattedText:
        """Generate the prompt text"""
        return FormattedText([
            ('class:user', f'{USER_NAME}'),
            ('', '> ')
        ])
    
    def format_commands_columns(self, commands: list[str], num_columns: int = 3) -> str:
        """Format commands into columns"""
        if not commands:
            return ""
        
        # Sort commands
        commands = sorted(commands)
        
        # Calculate rows needed
        num_commands = len(commands)
        num_rows = math.ceil(num_commands / num_columns)
        
        # Pad command list to fill grid
        while len(commands) < num_rows * num_columns:
            commands.append('')
            
        # Create columns
        columns = []
        for i in range(num_columns):
            column = commands[i * num_rows:(i + 1) * num_rows]
            columns.append(column)
            
        # Find maximum width for each column
        col_widths = [max(len(cmd) for cmd in col) + 2 for col in columns]
        
        # Format rows
        rows = []
        for row_idx in range(num_rows):
            row = []
            for col_idx, column in enumerate(columns):
                if row_idx < len(column) and column[row_idx]:
                    row.append(column[row_idx].ljust(col_widths[col_idx]))
            rows.append(''.join(row).rstrip())
            
        return '\n'.join(rows)
    
    def generate_command_documentation(self) -> str:
        """Generate formatted documentation for shell commands from their docstrings.
        
        Returns:
            Formatted string containing command documentation
        """
        doc_lines = []
        
        for cmd_name, cmd_data in self.commands.items():
            if not cmd_data.callable.__doc__:
                continue
                
            doc = cmd_data.callable.__doc__.strip()
            
            # Add shell access tier info for bash command
            if cmd_name == "bash":
                tier_doc = get_shell_access_tier_documentation(SHELL_ACCESS_TIER)
                # Split and indent each line of the tier documentation
                tier_doc = '\n        '.join(tier_doc.split('\n'))
                doc += "\n\n        " + tier_doc
                
            doc_lines.append(f"{cmd_name}: {doc}")
        
        return '\n'.join(doc_lines)

    async def do_exit(self, args: str) -> bool:
        """Exit the shell"""
        logger.log(LogLevel.SHELL, "Cymbiont shell exited")
        return True
    
    async def do_help(self, args: str) -> None:
        """Show help information
        Usage: help [command]"""
        if not args:
            # Show general help
            logger.info("Available commands (type help <command>):")
            formatted_commands = self.format_commands_columns(list(self.commands.keys()))
            logger.info(formatted_commands)
        else:
            # Show specific command help
            cmd_data = self.commands.get(args)
            if cmd_data:
                logger.info(f"{args}: {cmd_data.callable.__doc__ or 'No help available'}")
            else:
                logger.info(f"No help available for '{args}'")

    async def run_chat_agent(self) -> None:
        """Background task that runs the chat agent based on its activation mode."""
        while True:
            try:
                # Only process if agent is active
                if not self.chat_agent.active:
                    await asyncio.sleep(0.1)
                    continue

                with token_logger.show_tokens():
                    await self.chat_history.wait_for_summary()
                    with patch_stdout(raw=True):
                        response = await self.chat_agent.get_response()
                        self.keyword_router.toggle_context(response, self.chat_agent)
                        await asyncio.sleep(0)  # Let run loop take control

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in chat agent loop: {str(e)}")
                if DEBUG_ENABLED:
                    raise

    async def _prompt_async_with_patch(self) -> str:
        """Wrapper around prompt_async that handles patch_stdout correctly"""
        with patch_stdout(raw=True):
            return await self.session.prompt_async()

    async def run(self) -> None:
        """Run the shell"""
        try:
            await self.start_chat_agent()
            # Give initial logs a chance to queue
            await asyncio.sleep(0.1)

            while True:
                try:
                    # Create prompt task
                    prompt_task = asyncio.create_task(self._prompt_async_with_patch())
                    
                    while True:
                        # Wait a bit and check for logs
                        done, _ = await asyncio.wait([prompt_task], timeout=0.1)
                        
                        if not self.log_queue.empty():
                            # Then cancel the prompt task
                            prompt_task.cancel()
                            try:
                                await prompt_task
                            except asyncio.CancelledError:
                                pass
                                
                            # Clear prompt using direct stdout
                            sys.stdout.write("\033[A\033[2K\r")
                            sys.stdout.flush()
                                
                            # Process logs
                            while not self.log_queue.empty():
                                log_msg = self.log_queue.get_nowait()
                                if console_handler and console_handler.stream:
                                    console_handler.stream.write(log_msg)
                                    console_handler.stream.write(console_handler.terminator)
                                    console_handler.stream.flush()
                            
                            # Only break to create new prompt if no more logs
                            if self.log_queue.empty():
                                break
                            # Otherwise continue checking for more logs
                            continue
                            
                        if done:
                            # We got user input
                            text = prompt_task.result()
                            
                            if text and text.strip():
                                should_exit = await self.handle_input(text)
                                if should_exit:
                                    self._exit_type = 'exit'
                                    return

                            break

                except (EOFError, KeyboardInterrupt):
                    self._exit_type = 'interrupt'
                    break

        finally:
            await self.stop_chat_agent()
            # Re-raise KeyboardInterrupt if that's how we exited
            if self._exit_type == 'interrupt':
                raise KeyboardInterrupt()

    async def handle_input(self, text: str) -> bool:
        """Handle user input, returns True if shell should exit"""
        # Parse command and arguments
        parts = text.strip().split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ''
        
        # Execute command or treat as chat
        if command in self.commands:
            success, should_exit = await self.execute_command(command, args)
            return should_exit
        else:
            # Record user message and update context
            self.chat_history.add_message("user", text, name=USER_NAME)
            self.keyword_router.toggle_context(text, self.chat_agent)
            
            # Activate chat agent
            self.chat_agent.active = True
            
            return False

    async def execute_command(self, command: str, args: str, name: str = '') -> Tuple[bool, bool]:
        """Execute a shell command
        
        Returns:
            tuple[bool, bool]: (success, should_exit)
            - success: True if command executed successfully, False if it failed
            - should_exit: True if the shell should exit, False otherwise
        """
        try:
            # Log command execution
            if name:
                executor = name
            else:
                executor = USER_NAME
            logger.log(
                LogLevel.SHELL,
                f"{executor} executed: {command}{' ' + args if args else ''}"
            )
            
            # Execute command and get return value
            if self.commands[command].needs_shell:
                result = await self.commands[command].callable(self, args)
            else:
                result = await self.commands[command].callable(args)
            
            # Handle different return types for backward compatibility
            if isinstance(result, bool):
                # Old style: bool indicates should_exit
                return (True, result)
            elif isinstance(result, tuple) and len(result) == 2:
                # New style: (success, should_exit)
                return result
            else:
                # Assume success, don't exit
                return (True, False)
            
        except Exception as e:
            logger.error(f"Command failed: {str(e)}")
            if DEBUG_ENABLED:
                raise
            return (False, False)

    async def start_chat_agent(self) -> None:
        """Start the chat agent background task."""
        if self.chat_agent_task is None or self.chat_agent_task.done():
            self.chat_agent_task = asyncio.create_task(self.run_chat_agent())

    async def stop_chat_agent(self) -> None:
        """Stop the chat agent background task."""
        if self.chat_agent_task and not self.chat_agent_task.done():
            self.chat_agent_task.cancel()
            try:
                await self.chat_agent_task
            except asyncio.CancelledError:
                pass
      
        # Clear shell reference from handler so it falls back to direct output
        if console_handler:
            console_handler.shell = None

    async def do_print_total_tokens(self, args: str) -> None:
        """Print the total token count"""
        token_logger.print_total_tokens()

    async def do_hello_world(self, args: str = '') -> bool:
        """A friendly greeting with emojis! 🤖"""
        logger.info("Hello World! 🤖 ⚡")
        return False

    async def do_bash(self, args: str) -> None:
        """Execute a command in bash.
        Usage: bash <command>
        """
        if not args:
            logger.error("No command provided. Usage: bash <command>")
            return
            
        # Initialize bash executor if needed
        if self.bash_executor is None:
            try:
                self.bash_executor = BashExecutor()
            except Exception as e:
                logger.error(f"Failed to initialize bash executor: {e}")
                return
                
        try:
            # Execute the command
            output, error = self.bash_executor.execute(args)
            
            if error:
                logger.error(error)
            elif output:
                logger.log(LogLevel.BASH, output)
                
        except Exception as e:
            logger.error(f"Failed to execute command: {e}")
            # Reset executor on failure
            self.bash_executor = None
