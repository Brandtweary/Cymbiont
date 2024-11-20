# System imports
import asyncio
import cmd
import sys
from pathlib import Path

def setup_python_path() -> None:
    """Add project directories to Python path."""
    project_root = Path(__file__).parent.parent
    src_path = project_root / 'src'
    tests_path = project_root / 'tests'
    
    # Add src and tests to Python path
    sys.path.extend([str(project_root), str(src_path), str(tests_path)])

# Call setup before project imports
setup_python_path()

# Project imports
from api_queue import start_api_queue, stop_api_queue, enqueue_api_call
from documents import create_data_snapshot, process_documents
from shared_resources import DATA_DIR, logger, token_logger
from tests import test_api_queue
import threading

# ANSI color codes
GREEN = "\033[32m"
BLUE = "\033[34m"
RESET = "\033[0m"

class CymbiontShell(cmd.Cmd):
    intro = f'{GREEN}Welcome to Cymbiont. Type help or ? to list commands.{RESET}\n'
    prompt = f'{BLUE}cymbiont>{RESET} '
    
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.loop: asyncio.AbstractEventLoop = loop
    
    def do_process_documents(self, arg: str) -> None:
        """Process documents in the data directory.
        Usage: process_documents"""
        try:
            token_logger.reset_tokens()
            future = asyncio.run_coroutine_threadsafe(
                process_documents(DATA_DIR),
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
        """Create a snapshot of the data directory structure."""
        if not arg:
            print("Error: Please provide a name for the snapshot")
            return
        
        try:
            token_logger.reset_tokens()
            future = asyncio.run_coroutine_threadsafe(
                create_data_snapshot(arg),
                self.loop
            )
            snapshot_path = future.result()
            logger.info(f"Created snapshot at {snapshot_path}")
            token_logger.print_tokens()
        except Exception as e:
            logger.error(f"Snapshot creation failed: {str(e)}")

def main():
    # Create a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Start API queue
        loop.run_until_complete(start_api_queue())
        
        # Create shell with access to the loop by passing it to the constructor
        shell = CymbiontShell(loop=loop)
        
        # Run the shell with the loop in a separate thread
        shell_thread = threading.Thread(target=shell.cmdloop, daemon=True)
        shell_thread.start()
        
        # Keep the event loop running
        loop.run_forever()
        
    except KeyboardInterrupt:
        logger.debug("Keyboard interrupt received")
    finally:
        # Cleanup
        loop.run_until_complete(stop_api_queue())
        loop.close()
        logger.debug("Cymbiont shutdown complete")

if __name__ == "__main__":
    main()