import math
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText
from typing import Callable, Dict
from shared_resources import USER_NAME, AGENT_NAME, logger, token_logger
from chat_history import ChatHistory, setup_chat_history_handler
from constants import LogLevel
from chat_agent import get_chat_response

from .command_completer import CommandCompleter
from .doc_processing_commands import (
    do_process_documents,
    do_create_data_snapshot,
    do_parse_documents,
)
from .test_commands import (
    do_test_api_queue,
    do_test_document_processing,
    do_test_logger,
    do_test_parsing,
    do_test_progressive_summarization,
    do_run_all_tests,
)


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
            'process_documents': self.do_process_documents,
            'create_data_snapshot': self.do_create_data_snapshot,
            'parse_documents': self.do_parse_documents,
            'test_api_queue': self.do_test_api_queue,
            'test_document_processing': self.do_test_document_processing,
            'test_logger': self.do_test_logger,
            'test_parsing': self.do_test_parsing,
            'test_progressive_summarization': self.do_test_progressive_summarization,
            'run_all_tests': self.do_run_all_tests,
            'print_total_tokens': self.do_print_total_tokens,
        }
        
        # Create command completer
        command_completer = CommandCompleter(self.commands)
        
        # Create prompt session with styling
        style = Style.from_dict({
            'user': '#0080FE',    # Deep blue
            'command': 'ansigreen',
            'agent': '#00FFFF',   # Bright cyan
        })
        
        self.session = PromptSession(
            style=style,
            message=self.get_prompt,
            completer=command_completer
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
    
    async def do_exit(self, args: str) -> bool:
        """Exit the shell"""
        logger.log(LogLevel.SHELL, "Cymbiont shell exited")
        return True
    
    async def do_help(self, args: str) -> None:
        """Show help information"""
        if not args:
            # Show general help
            logger.info("Available commands (type help <command>):")
            formatted_commands = self.format_commands_columns(list(self.commands.keys()))
            logger.info(formatted_commands + "\n")
        else:
            # Show specific command help
            cmd = self.commands.get(args)
            if cmd:
                logger.info(f"{args}: {cmd.__doc__ or 'No help available'}\n")
            else:
                logger.info(f"No help available for '{args}'\n")
    
    async def handle_chat(self, text: str) -> None:
        """Handle chat messages"""
        try:
            token_logger.reset_tokens()
            # Record user message
            self.chat_history.add_message("user", text, name=USER_NAME)
            
            # Wait for any ongoing summarization
            await self.chat_history.wait_for_summary()
            
            # Get messages and summary separately
            messages, summary = self.chat_history.get_recent_messages()
            
            response = await get_chat_response(messages, summary)
            
            # Record assistant response
            self.chat_history.add_message("assistant", response, name=AGENT_NAME)
            
            # Print token usage and reset
            token_logger.print_tokens()
            token_logger.reset_tokens()
            
            # Print response with bright cyan agent name
            print(f"\x1b[38;2;0;255;255m{AGENT_NAME}\x1b[0m> {response}")
            
        except Exception as e:
            logger.error(f"Chat response failed: {str(e)}")
    
    async def execute_command(self, command: str, args: str) -> bool:
        """Execute a shell command"""
        try:
            # Log command execution
            logger.log(
                LogLevel.SHELL, 
                f"{USER_NAME} executed: {command}{' ' + args if args else ''}"
            )
            
            # Execute command
            return await self.commands[command](args)
            
        except Exception as e:
            logger.error(f"Command failed: {str(e)}")
            return False
    
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
                    if await self.execute_command(command, args):
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

    # Test commands
    async def do_test_api_queue(self, args: str) -> None:
        """Run API queue tests.
        Usage: test_api_queue"""
        await do_test_api_queue(self, args)

    async def do_test_document_processing(self, args: str) -> None:
        """Test document processing pipeline with mock API calls.
        Usage: test_document_processing"""
        await do_test_document_processing(self, args)

    async def do_test_logger(self, args: str) -> None:
        """Test all logging levels with colored output.
        Usage: test_logger"""
        await do_test_logger(self, args)

    async def do_test_parsing(self, args: str) -> None:
        """Run text parsing tests.
        Usage: test_parsing"""
        await do_test_parsing(self, args)

    async def do_test_progressive_summarization(self, args: str) -> None:
        """Test progressive summarization functionality.
        Usage: test_progressive_summarization"""
        await do_test_progressive_summarization(self, args)

    async def do_run_all_tests(self, args: str) -> None:
        """Run all tests.
        Usage: run_all_tests"""
        await do_run_all_tests(self, args)

    async def do_print_total_tokens(self, args: str) -> None:
        """Print the total token count"""
        token_logger.print_tokens()