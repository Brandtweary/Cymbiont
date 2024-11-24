import asyncio
import cmd
from shared_resources import DATA_DIR, logger, token_logger, USER_NAME, AGENT_NAME, chat_history_handler
from logging_config import RESPONSE
from documents import create_data_snapshot, process_documents
from tests import test_api_queue
from text_parser import test_parse
from tests.test_logger import run_logger_test
from tests.test_parsing import test_text_parsing
from chat_agent import get_chat_response
from custom_dataclasses import ChatHistory


# ANSI color codes
GREEN = "\033[32m"
BLUE = "\033[34m"
RESET = "\033[0m"

class CymbiontShell(cmd.Cmd):
    intro = f'{GREEN}Welcome to Cymbiont. Type help or ? to list commands.{RESET}\n'
    prompt = f'{BLUE}{USER_NAME}>{RESET} '
    
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.loop: asyncio.AbstractEventLoop = loop
        self.chat_history = ChatHistory()
        self.last_test_success: bool = True
        # Connect chat history to logger
        chat_history_handler.chat_history = self.chat_history
    
    def print_topics(self, header: str, cmds: list[str] | None, cmdlen: int, maxcol: int) -> None:
        """Override to add color to help topics"""
        if not cmds:  # Skip empty sections
            return
        if header:
            if header == "Documented commands (type help <topic>):":
                header = f"{GREEN}Available commands (type help <command>):{RESET}"
            self.stdout.write(f"{GREEN}{header}{RESET}\n")
        self.columnize([f"{GREEN}{cmd}{RESET}" for cmd in cmds], maxcol-1)
        self.stdout.write("\n")

    def print_help_text(self, text: str) -> None:
        """Helper method to print help text in green"""
        self.stdout.write(f"{GREEN}{text}{RESET}\n")

    def do_help(self, arg: str) -> None:
        """Override the help command to add color"""
        if arg:
            # Show help for specific command
            try:
                func = getattr(self, 'help_' + arg)
            except AttributeError:
                try:
                    doc = getattr(self, 'do_' + arg).__doc__
                    if doc:
                        self.print_help_text(str(doc))
                        return
                except AttributeError:
                    pass
                self.print_help_text(f"*** No help on {arg}")
        else:
            # Show the list of commands
            super().do_help(arg)
    
    def do_process_documents(self, arg: str) -> None:
        """Process documents in the data/input_documents directory.
        Usage: process_documents [document_name]
        - document_name: Optional. If provided, only this file or folder will be processed.
                        Otherwise, processes all .txt and .md files."""
        try:
            token_logger.reset_tokens()
            future = asyncio.run_coroutine_threadsafe(
                process_documents(DATA_DIR, arg if arg else None),
                self.loop
            )
            future.result()
            token_logger.print_tokens()
        except Exception as e:
            logger.error(f"Document processing failed: {str(e)}")
    
    def do_exit(self, arg: str) -> bool:
        """Exit the Cymbiont shell"""
        self.loop.call_soon_threadsafe(self.loop.stop)
        return True
    
    def do_test_api_queue(self, arg: str) -> None:
        """Run API queue tests.
        Usage: test_api_queue"""
        try:
            future = asyncio.run_coroutine_threadsafe(
                test_api_queue.run_tests(),
                self.loop
            )
            future.result()  # Adjust timeout as needed
            logger.info("API queue tests passed successfully")
            self.last_test_success = True
        except Exception as e:
            logger.error(f"API queue tests failed: {str(e)}")
            self.last_test_success = False

    def do_test_parsing(self, arg: str) -> None:
        """Run text parsing tests.
        Usage: test_parsing"""
        try:
            test_text_parsing()
            logger.info("Text parsing tests passed successfully")
            self.last_test_success = True
        except AssertionError as e:
            logger.error(f"Text parsing tests failed: {str(e)}")
            self.last_test_success = False
        except Exception as e:
            logger.error(f"Text parsing tests failed with unexpected error: {str(e)}")
            self.last_test_success = False

    def do_run_all_tests(self, arg: str) -> None:
        """Run all tests
        Usage: run_all_tests"""
        test_commands = [cmd for cmd in self.get_commands() if cmd.startswith('test_')]
        total_tests = len(test_commands)
        passed_tests = 0
        failed_tests: list[tuple[str, str]] = []

        for cmd in test_commands:
            try:
                # Get the method and call it with empty args
                method = getattr(self, f'do_{cmd}')
                method('')
                if self.last_test_success:
                    passed_tests += 1
                    logger.info(f"✅ {cmd} passed")
                else:
                    failed_tests.append((cmd, "Test failed"))
            except Exception as e:
                failed_tests.append((cmd, str(e)))
                logger.error(f"❌ {cmd} failed")

        success_rate = (passed_tests / total_tests) * 100

        # Print results with ASCII art
        print("\n=== Test Results ===")
        print(f"Tests Run: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {len(failed_tests)}")
        print(f"Success Rate: {success_rate:.1f}%\n")

        if failed_tests:
            print("Failed Tests:")
            for cmd, error in failed_tests:
                print(f"❌ {cmd}: {error}")

        if success_rate == 100:
            print("""
    🎉 Perfect Score! 🎉
    ┌────────────────┐
    │   100% PASS    │
    │    ⭐ ⭐ ⭐    │
    └────────────────┘
            """)
        elif success_rate >= 80:
            print("""
    😊 Almost There! 
    ┌────────────────┐
    │   Keep Going!  │
    │    ⭐ ⭐      │
    └────────────────┘
            """)
        else:
            print("""
    😢 Needs Work 
    ┌────────────────┐
    │   Don't Give   │
    │     Up! 💪     │
    └────────────────┘
            """)
    
    def do_create_data_snapshot(self, arg: str) -> None:
        """Creates an isolated snapshot by processing documents in the data/input_documents directory.
        The snapshot contains all processing artifacts (chunks, indexes, etc.) as if you had
        only processed the specified documents.

        Usage: create_data_snapshot <snapshot_name> [document_name]
        - snapshot_name: Name for the new snapshot directory
        - document_name: Optional. If provided, only this file or folder will be processed.
                        Otherwise, processes all .txt and .md files."""
        args = arg.split()
        if not args:
            print("Error: Please provide a name for the snapshot")
            return
        
        try:
            token_logger.reset_tokens()
            future = asyncio.run_coroutine_threadsafe(
                create_data_snapshot(args[0], args[1] if len(args) > 1 else None),
                self.loop
            )
            snapshot_path = future.result()
            logger.info(f"Created snapshot at {snapshot_path}")
            token_logger.print_tokens()
        except Exception as e:
            logger.error(f"Snapshot creation failed: {str(e)}")
    
    def do_parse_documents(self, arg: str) -> None:
        """Test document parsing without running LLM tag extraction.
        This command parses documents in data/input_documents into chunks and records the results to logs/parse_test_results.log.

        Usage: parse_documents [document_name]
        - document_name: Optional. If provided, only this file or folder will be tested.
                        Otherwise, tests all .txt and .md files."""
        try:
            test_parse(arg if arg else None)
        except Exception as e:
            logger.error(f"Parse testing failed: {str(e)}")
    
    def do_test_logger(self, arg: str) -> None:
        """Test all logging levels with colored output.
        Usage: test_logger"""
        try:
            run_logger_test()
            logger.info("Logger tests passed successfully")
            self.last_test_success = True
        except Exception as e:
            logger.error(f"Logger testing failed: {str(e)}")
            self.last_test_success = False
    
    def get_commands(self) -> list[str]:
        """Get a list of all available commands"""
        return [attr[3:] for attr in dir(self) if attr.startswith('do_')]

    def default(self, line: str) -> None:
        """Handle chat messages"""
        try:
            # Record user message
            self.chat_history.add_message("user", line)
            
            future = asyncio.run_coroutine_threadsafe(
                get_chat_response(line, self.chat_history.get_recent_messages()),
                self.loop
            )
            response = future.result()
            
            # Record and log assistant response
            self.chat_history.add_message("assistant", response)
            logger.log(RESPONSE, f"Agent response: {response}")
            # Print response directly to user
            print(f"{BLUE}{AGENT_NAME}>{RESET} {response}\n")
        except Exception as e:
            logger.error(f"Chat response failed: {str(e)}")

    def completenames(self, text: str, *ignored) -> list[str]:
        """Override completenames to only show actual commands"""
        return [name for name in self.get_commands() if name.startswith(text)]