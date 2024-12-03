import math
from unittest.mock import DEFAULT
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText
from typing import Callable, Dict, Any, Tuple
from shared_resources import USER_NAME, AGENT_NAME, logger
from token_logger import token_logger
from agents.chat_history import ChatHistory, setup_chat_history_handler
from constants import LogLevel, ToolName
from agents.chat_agent import get_response
from prompt_helpers import DEFAULT_SYSTEM_PROMPT_PARTS
from agents.tool_schemas import format_all_tool_schemas
from system_prompt_parts import SYSTEM_MESSAGE_PARTS
import re
import inspect

from .command_completer import CommandCompleter
from .doc_processing_commands import (
    do_process_documents,
    do_create_data_snapshot,
    do_parse_documents,
    do_revise_document
)
from .test_commands import (
    do_test_api_queue,
    do_test_document_processing,
    do_test_logger,
    do_test_parsing,
    do_test_progressive_summarization,
    do_test_agent_tools,
    do_run_all_tests,
)

# Define which commands accept arguments
COMMAND_METADATA = {
    'exit': {'takes_args': False},
    'help': {'takes_args': True},  # Optional command name to get help for
    'hello_world': {'takes_args': False},
    'process_documents': {'takes_args': True},  # File paths
    'create_data_snapshot': {'takes_args': True},  # Snapshot name \\ file paths
    'parse_documents': {'takes_args': True},  # File paths
    'revise_document': {'takes_args': True},  # File path
    'test_api_queue': {'takes_args': False},
    'test_document_processing': {'takes_args': False},
    'test_logger': {'takes_args': False},
    'test_parsing': {'takes_args': False},
    'test_progressive_summarization': {'takes_args': False},
    'test_agent_tools': {'takes_args': False},
    'run_all_tests': {'takes_args': False},
    'print_total_tokens': {'takes_args': False},
}


class CymbiontShell:
    def __init__(self) -> None:
        self.chat_history = ChatHistory()
        self.test_successes: int = 0
        self.test_failures: int = 0
        
        # Connect chat history to logger
        setup_chat_history_handler(logger, self.chat_history)
        
        # Define command handlers
        self.commands: Dict[str, Callable] = {
            'exit': self.do_exit,
            'help': self.do_help,
            'hello_world': self.do_hello_world,
            'process_documents': self.do_process_documents,
            'create_data_snapshot': self.do_create_data_snapshot,
            'parse_documents': self.do_parse_documents,
            'revise_document': self.do_revise_document,
            'test_api_queue': self.do_test_api_queue,
            'test_document_processing': self.do_test_document_processing,
            'test_logger': self.do_test_logger,
            'test_parsing': self.do_test_parsing,
            'test_progressive_summarization': self.do_test_progressive_summarization,
            'test_agent_tools': self.do_test_agent_tools,
            'run_all_tests': self.do_run_all_tests,
            'print_total_tokens': self.do_print_total_tokens,
        }
        
        self.command_metadata = COMMAND_METADATA
        
        # Map commands to their original functions for documentation
        self.command_mapping: Dict[str, Callable] = {
            'exit': self.do_exit,  # Built-in commands use their wrapper docstrings
            'help': self.do_help,
            'hello_world': self.do_hello_world,
            'process_documents': do_process_documents,  # Imported commands use their original docstrings
            'create_data_snapshot': do_create_data_snapshot,
            'parse_documents': do_parse_documents,
            'revise_document': do_revise_document,
            'test_api_queue': do_test_api_queue,
            'test_document_processing': do_test_document_processing,
            'test_logger': do_test_logger,
            'test_parsing': do_test_parsing,
            'test_progressive_summarization': do_test_progressive_summarization,
            'test_agent_tools': do_test_agent_tools,
            'run_all_tests': do_run_all_tests,
            'print_total_tokens': self.do_print_total_tokens,
        }
        
        # Generate command documentation and format shell_command_info part
        shell_doc = self.generate_command_documentation()
        SYSTEM_MESSAGE_PARTS['shell_command_info'].content = \
            SYSTEM_MESSAGE_PARTS['shell_command_info'].content.format(
                shell_command_documentation=shell_doc
            )
        
        # Format tool schemas with command metadata
        format_all_tool_schemas(
            {ToolName.EXECUTE_SHELL_COMMAND},
            commands=list(self.commands.keys()),
            command_metadata=self.command_metadata
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
        
        for cmd_name, handler in self.command_mapping.items():
            if not handler.__doc__:
                continue
                
            doc_lines.append(f"{cmd_name}: {handler.__doc__.strip()}")
        
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
            cmd = self.command_mapping.get(args)
            if cmd:
                logger.info(f"{args}: {cmd.__doc__ or 'No help available'}\n")
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
                
                response = await get_response(
                    chat_history=self.chat_history,
                    tools={
                        ToolName.CONTEMPLATE_LOOP, 
                        ToolName.EXECUTE_SHELL_COMMAND,
                        ToolName.TOGGLE_PROMPT_PART,
                        ToolName.INTRODUCE_SELF,
                        ToolName.SHELL_LOOP
                        },
                    token_budget=20000
                )

                if response:
                    print(f"\x1b[38;2;0;255;255m{AGENT_NAME}\x1b[0m> {response}")
        
        except Exception as e:
            logger.error(f"Chat response failed: {str(e)}")
    
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
            result = await self.commands[command](args)
            
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
            return (False, False)

    async def run(self) -> None:
        """Main shell loop"""
        while True:
            try:
                text = await self.session.prompt_async()
                if not text:
                    continue
                    
                # Parse command and arguments
                parts = text.strip().split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ''
                
                # Execute command or treat as chat
                if command in self.commands:
                    success, should_exit = await self.execute_command(command, args)
                    if should_exit:
                        break
                else:
                    # Handle as chat message
                    await self.handle_chat(text)
                    
            except KeyboardInterrupt:
                continue
            except EOFError:
                break

    # Document processing commands
    async def do_process_documents(self, args: str) -> None:
        """Process documents in the data/input_documents directory for LLM tag extraction.
        Usage: process_documents [document_name]
        - document_name: Optional. If provided, only this file or folder will be processed.
                        Otherwise, processes all .txt and .md files."""
        await do_process_documents(args)

    async def do_create_data_snapshot(self, args: str) -> None:
        """Creates an isolated snapshot folder by processing documents in the data/input_documents directory.
        The snapshot contains all processing artifacts (chunks, indexes, etc.) as if you had
        only processed the specified documents.

        Usage: create_data_snapshot <snapshot_name> [document_name]
        - snapshot_name: Name for the new snapshot folder
        - document_name: Optional. If provided, only this file or folder will be processed.
                        Otherwise, processes all .txt and .md files."""
        await do_create_data_snapshot(args)

    async def do_parse_documents(self, args: str) -> None:
        """Test document parsing without running LLM tag extraction.
        This command parses documents in data/input_documents into chunks and records the results to logs/parse_test_results.log.

        Usage: parse_documents [document_name]
        - document_name: Optional. If provided, only this file or folder will be tested.
                        Otherwise, tests all .txt and .md files."""
        await do_parse_documents(args)

    async def do_revise_document(self, args: str) -> None:
        """Revise a document"""
        await do_revise_document(args)

    # Test commands
    async def do_test_api_queue(self, args: str) -> None:
        """Run API queue tests."""
        await do_test_api_queue(self, args)

    async def do_test_document_processing(self, args: str) -> None:
        """Test document processing pipeline with mock API calls."""
        await do_test_document_processing(self, args)

    async def do_test_logger(self, args: str) -> None:
        """Test all logging levels with colored output."""
        await do_test_logger(self, args)

    async def do_test_parsing(self, args: str) -> None:
        """Run text parsing tests."""
        await do_test_parsing(self, args)

    async def do_test_progressive_summarization(self, args: str) -> None:
        """Test progressive summarization functionality."""
        await do_test_progressive_summarization(self, args)

    async def do_test_agent_tools(self, args: str) -> None:
        """Test agent tools functionality."""
        await do_test_agent_tools(self, args)

    async def do_run_all_tests(self, args: str) -> None:
        """Run all tests."""
        await do_run_all_tests(self, args)

    async def do_print_total_tokens(self, args: str) -> None:
        """Print the total token count"""
        token_logger.print_total_tokens()

    async def do_hello_world(self, args: str = '') -> bool:
        """A friendly greeting with emojis! 🤖"""
        print("Hello World! 🤖 ⚡")
        return False
