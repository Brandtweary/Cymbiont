import math
import asyncio
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.formatted_text.base import StyleAndTextTuples
from typing import Tuple, Optional
from agents import agent
from agents.tool_helpers import register_tools
from shared_resources import USER_NAME, AGENT_NAME, logger, DEBUG_ENABLED, TOOL_AGENT_ACTIVATION_MODE, console_handler
from token_logger import token_logger
from agents.chat_history import ChatHistory, setup_chat_history_handler
from constants import LogLevel
from agents.agent import Agent, DEFAULT_SYSTEM_PROMPT_PARTS
from agents.chat_agent import ChatAgent
from agents.tool_agent import ToolAgent
from agents.tool_helpers import format_all_tool_schemas
from system_prompt_parts import SYSTEM_MESSAGE_PARTS
from .command_completer import CommandCompleter
from .command_metadata import create_commands
from .log_aware_session import LogAwareSession


class CymbiontShell:
    def __init__(self) -> None:
        self.chat_history = ChatHistory()
        self.test_successes: int = 0
        self.test_failures: int = 0
        
        # Initialize agents
        register_tools()
        self.tool_agent = ToolAgent(
            self.chat_history,
            activation_mode=TOOL_AGENT_ACTIVATION_MODE
        )
        self.chat_agent = ChatAgent(
            self.chat_history,
            agent_name=AGENT_NAME,
        )
        Agent.bind_agents(self.chat_agent, self.tool_agent)
        self.tool_agent_task: Optional[asyncio.Task] = None
        
        # Connect chat history to logger
        setup_chat_history_handler(logger, self.chat_history)
        
        # Store command metadata
        self.commands = create_commands(
            do_exit=self.do_exit,
            do_help=self.do_help,
            do_hello_world=self.do_hello_world,
            do_print_total_tokens=self.do_print_total_tokens
        )
        
        # Generate command documentation and format shell_command_info part
        shell_doc = self.generate_command_documentation()
        SYSTEM_MESSAGE_PARTS['shell_command_info'].content = \
            SYSTEM_MESSAGE_PARTS['shell_command_info'].content.format(
                shell_command_documentation=shell_doc
            )
        
        # Format tool schemas with dynamic content
        format_all_tool_schemas(
            command_metadata=self.commands,
            system_prompt_parts=DEFAULT_SYSTEM_PROMPT_PARTS
        )
        
        # Initialize command completer
        self.completer = CommandCompleter(self.commands)
        
        # Create prompt session with styling
        style = Style.from_dict({
            'user': '#0080FE',    # Deep blue
            'command': 'ansigreen',
            'agent': '#00FFFF',   # Bright cyan
        })
        
        self.session = LogAwareSession(
            style=style,
            message=self.get_prompt,
            completer=self.completer
        )
        
        # Connect the prompt session to the logging handler
        console_handler.prompt_session = self.session
        
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
                
            doc_lines.append(f"{cmd_name}: {cmd_data.callable.__doc__.strip()}")
        
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
            logger.info(formatted_commands + "\n")
        else:
            # Show specific command help
            cmd_data = self.commands.get(args)
            if cmd_data:
                logger.info(f"{args}: {cmd_data.callable.__doc__ or 'No help available'}\n")
            else:
                logger.info(f"No help available for '{args}'\n")
    
    async def handle_chat(self, text: str) -> None:
        """Handle chat messages"""
        try:
            # Use show_tokens to handle nested token tracking
            with token_logger.show_tokens():
                # Record user message
                self.chat_history.add_message("user", text, name=USER_NAME)
                
                # Wait for any ongoing summarization
                await self.chat_history.wait_for_summary()
                
                response = await self.chat_agent.get_response(token_budget=20000)
                
                if response:
                    print(f"\x1b[38;2;0;255;255m{AGENT_NAME}\x1b[0m> {response}")
        
        except Exception as e:
            logger.error(f"Chat response failed: {str(e)}")
            if DEBUG_ENABLED:
                raise

    async def start_tool_agent(self) -> None:
        """Start the tool agent background task."""
        if self.tool_agent_task is None or self.tool_agent_task.done():
            self.tool_agent_task = asyncio.create_task(self.run_tool_agent())

    async def stop_tool_agent(self) -> None:
        """Stop the tool agent background task."""
        if self.tool_agent_task and not self.tool_agent_task.done():
            self.tool_agent_task.cancel()
            try:
                await self.tool_agent_task
            except asyncio.CancelledError:
                pass

    async def run_tool_agent(self) -> None:
        """Background task that runs the tool agent based on its activation mode."""
        while True:
            try:
                if not self.tool_agent.active:
                    await asyncio.sleep(0.1)  # Short sleep when inactive
                    continue

                with token_logger.show_tokens():
                    response = await self.tool_agent.get_response(
                        token_budget=20000
                    )

                if response:
                    logger.log(LogLevel.TOOL, f"{self.tool_agent.agent_name}: {response}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in tool agent loop: {str(e)}")
                if DEBUG_ENABLED:
                    raise

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
            # Handle as chat message
            await self.handle_chat(text)
            return False

    async def run(self) -> None:
        """Run the shell"""
        try:
            # Start the tool agent
            await self.start_tool_agent()

            while True:
                try:
                    # Get user input
                    text = await self.session.prompt_async()
                    
                    # Skip empty lines
                    if not text.strip():
                        continue
                    
                    # Handle the input
                    should_exit = await self.handle_input(text)
                    if should_exit:
                        break
                
                except KeyboardInterrupt:
                    continue
                except EOFError:
                    break
        finally:
            # Stop the tool agent
            await self.stop_tool_agent()

    async def do_print_total_tokens(self, args: str) -> None:
        """Print the total token count"""
        token_logger.print_total_tokens()

    async def do_hello_world(self, args: str = '') -> bool:
        """A friendly greeting with emojis! 🤖"""
        logger.info("Hello World! 🤖 ⚡")
        return False
