import asyncio
import cmd
from shared_resources import DATA_DIR, logger, token_logger, USER_NAME, AGENT_NAME
from documents import create_data_snapshot, process_documents
from tests import test_api_queue
from text_parser import test_parse
from tests.test_logger import run_logger_test
from chat_agent import get_chat_response


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
        except Exception as e:
            logger.error(f"API queue tests failed: {str(e)}")
    
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
    
    def do_test_parse(self, arg: str) -> None:
        """Test document parsing without running LLM tag extraction.
        This command parses documents in data/input_documents into chunks and records the results to logs/parse_test_results.log.

        Usage: test_parse [document_name]
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
        except Exception as e:
            logger.error(f"Logger testing failed: {str(e)}")
    
    def get_commands(self) -> list[str]:
        """Get a list of all available commands"""
        return [attr[3:] for attr in dir(self) if attr.startswith('do_')]

    def default(self, line: str) -> None:
        """Handle any input that isn't a recognized command by sending it to the chat agent"""
        try:
            future = asyncio.run_coroutine_threadsafe(
                get_chat_response(line),
                self.loop
            )
            response = future.result()  # This blocks until we get the response
            print(f"{BLUE}{AGENT_NAME}>{RESET} {response}")
        except Exception as e:
            logger.error(f"Chat response failed: {str(e)}")

    def completenames(self, text: str, *ignored) -> list[str]:
        """Override completenames to only show actual commands"""
        return [name for name in self.get_commands() if name.startswith(text)]