from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from typing import Callable, Dict
import asyncio
import math
from shared_resources import USER_NAME, AGENT_NAME, logger, token_logger, DATA_DIR
from chat_history import ChatHistory, setup_chat_history_handler
from constants import LogLevel
from chat_agent import get_chat_response
from documents import process_documents, create_data_snapshot
from text_parser import test_parse
from tests.test_api_queue import run_api_queue_tests
from tests.test_document_processing import run_document_processing_tests
from tests.test_logger import run_logger_test
from tests.test_parsing import run_text_parsing_test
from tests.test_chat_history import test_progressive_summarization


class CommandCompleter(Completer):
    def __init__(self, commands: Dict[str, Callable]) -> None:
        self.commands = commands
        # Create a word completer for command arguments
        self.arg_completions: Dict[str, WordCompleter] = {
            'help': WordCompleter(list(commands.keys()), ignore_case=True),
            # Add more command-specific completers as needed
        }

    def get_completions(self, document, complete_event):
        text_before_cursor: str = document.text_before_cursor
        words: list[str] = text_before_cursor.split()
        
        # If no words yet, show all commands
        if not words:
            for command in self.commands:
                yield Completion(command, start_position=0)
            return
            
        # If we're still typing the first word (no space after it)
        if len(words) == 1 and not text_before_cursor.endswith(' '):
            word_before_cursor: str = words[0]
            for command in self.commands:
                if command.startswith(word_before_cursor.lower()):
                    yield Completion(command, start_position=-len(word_before_cursor))
            return
            
        # Handle argument completion using WordCompleter
        first_word: str = words[0].lower()
        if first_word in self.commands and first_word in self.arg_completions:
            # Get the word completer for this command
            word_completer = self.arg_completions[first_word]
            # Delegate to the word completer
            yield from word_completer.get_completions(document, complete_event)


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
            'prompt': '#00FFFF',  # Cyan
            'command': 'ansigreen',
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
            ('class:prompt', f'{USER_NAME}> ')
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
            
            # Print response directly (already logged in chat_agent)
            print(f"{AGENT_NAME}> {response}")
            
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
    
    async def do_process_documents(self, args: str) -> None:
        """Process documents in the data/input_documents directory.
        Usage: process_documents [document_name]
        - document_name: Optional. If provided, only this file or folder will be processed.
                        Otherwise, processes all .txt and .md files."""
        try:
            token_logger.reset_tokens()
            await process_documents(DATA_DIR, args if args else None)
            token_logger.print_tokens()
            token_logger.reset_tokens()
        except Exception as e:
            logger.error(f"Document processing failed: {str(e)}")

    async def do_create_data_snapshot(self, args: str) -> None:
        """Creates an isolated snapshot by processing documents in the data/input_documents directory.
        The snapshot contains all processing artifacts (chunks, indexes, etc.) as if you had
        only processed the specified documents.

        Usage: create_data_snapshot <snapshot_name> [document_name]
        - snapshot_name: Name for the new snapshot directory
        - document_name: Optional. If provided, only this file or folder will be processed.
                        Otherwise, processes all .txt and .md files."""
        arg_parts = args.split()
        if not arg_parts:
            logger.error("Error: Please provide a name for the snapshot")
            return
        
        try:
            token_logger.reset_tokens()
            snapshot_path = await create_data_snapshot(
                arg_parts[0], 
                arg_parts[1] if len(arg_parts) > 1 else None
            )
            logger.info(f"Created snapshot at {snapshot_path}")
            token_logger.print_tokens()
            token_logger.reset_tokens()
        except Exception as e:
            logger.error(f"Snapshot creation failed: {str(e)}")

    async def do_parse_documents(self, args: str) -> None:
        """Test document parsing without running LLM tag extraction.
        This command parses documents in data/input_documents into chunks and records the results to logs/parse_test_results.log.

        Usage: parse_documents [document_name]
        - document_name: Optional. If provided, only this file or folder will be tested.
                        Otherwise, tests all .txt and .md files."""
        try:
            test_parse(args if args else None)
        except Exception as e:
            logger.error(f"Parse testing failed: {str(e)}")

    async def do_test_api_queue(self, args: str) -> None:
        """Run API queue tests.
        Usage: test_api_queue"""
        try:
            passed, failed = await run_api_queue_tests()
            self.test_successes = passed
            self.test_failures = failed
        except Exception as e:
            logger.error(f"API queue tests failed: {str(e)}")
            self.test_successes = 0
            self.test_failures = 1

    async def do_test_document_processing(self, args: str) -> None:
        """Test document processing pipeline with mock API calls.
        Usage: test_document_processing"""
        try:
            self.test_successes, self.test_failures = await run_document_processing_tests()
        except Exception as e:
            logger.error(f"Document processing tests failed with unexpected error: {str(e)}")
            self.test_successes = 0
            self.test_failures = 1

    async def do_test_logger(self, args: str) -> None:
        """Test all logging levels with colored output.
        Usage: test_logger"""
        try:
            run_logger_test()
            logger.info("Logger tests passed successfully")
            self.test_successes += 1
        except Exception as e:
            logger.error(f"Logger testing failed: {str(e)}")
            self.test_failures += 1

    async def do_test_parsing(self, args: str) -> None:
        """Run text parsing tests.
        Usage: test_parsing"""
        try:
            run_text_parsing_test()
            logger.info("Text parsing tests passed successfully")
            self.test_successes += 1
        except AssertionError as e:
            logger.error(f"Text parsing tests failed: {str(e)}")
            self.test_failures += 1
        except Exception as e:
            logger.error(f"Text parsing tests failed with unexpected error: {str(e)}")
            self.test_failures += 1

    async def do_run_all_tests(self, args: str) -> None:
        """Run all tests
        Usage: run_all_tests"""
        test_commands = [cmd for cmd in self.commands.keys() if cmd.startswith('test_')]
        total_successes = 0
        total_failures = 0
        failed_tests: list[tuple[str, str]] = []

        for cmd in test_commands:
            try:
                # Reset test counters before each test
                self.test_successes = 0
                self.test_failures = 0
                
                # Run the test
                method = self.commands[cmd]
                await method('')
                
                # Accumulate results
                total_successes += self.test_successes
                total_failures += self.test_failures
                
                if self.test_failures > 0:
                    failed_tests.append((cmd, f"{self.test_failures} tests failed"))
                    logger.error(f"❌ {cmd} failed\n")
                else:
                    logger.info(f"✅ {cmd} passed\n")
                    
            except Exception as e:
                total_failures += 1
                failed_tests.append((cmd, str(e)))
                logger.error(f"❌ {cmd} failed\n")

        total_tests = total_successes + total_failures
        success_rate = (total_successes / total_tests) * 100 if total_tests > 0 else 0

        # Print results with logger
        logger.info("\n=== Test Results ===")
        logger.info(f"Tests Run: {total_tests}")
        logger.info(f"Passed: {total_successes}")
        logger.info(f"Failed: {total_failures}")
        logger.info(f"Success Rate: {success_rate:.1f}%\n")

        if failed_tests:
            logger.info("Failed Tests:")
            for cmd, error in failed_tests:
                logger.error(f"❌ {cmd}: {error}")

        if success_rate == 100:
            logger.info("""
    🎉 Perfect Score! 🎉
    ┌────────────────┐
    │   100% PASS    │
    │    ⭐ ⭐ ⭐    │
    └────────────────┘
            """)
        elif success_rate >= 80:
            logger.info("""
    😊 Almost There! 
    ┌────────────────┐
    │   Keep Going!  │
    │    ⭐ ⭐       │
    └────────────────┘
            """)
        else:
            logger.info("""
    😢 Needs Work 
    ┌────────────────┐
    │   Don't Give   │
    │     Up! 💪     │
    └────────────────┘
            """)

    async def do_test_progressive_summarization(self, args: str) -> None:
        """Test progressive summarization functionality.
        Usage: test_progressive_summarization"""
        try:
            await test_progressive_summarization()
            logger.info("Progressive summarization tests passed successfully")
            self.test_successes += 1
        except AssertionError as e:
            logger.error(f"Progressive summarization tests failed: {str(e)}")
            self.test_failures += 1
        except Exception as e:
            logger.error(f"Progressive summarization tests failed with unexpected error: {str(e)}")
            self.test_failures += 1
    
    async def do_print_total_tokens(self, args: str) -> None:
        """Print the total token count"""
        token_logger.print_total_tokens()