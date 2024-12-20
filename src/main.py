# System imports
from pathlib import Path
import sys
import asyncio

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
from shared_resources import logger, DATA_DIR, set_shell, DEBUG_ENABLED, console_handler
from cymbiont_logger.token_logger import token_logger
from cymbiont_shell.cymbiont_shell import CymbiontShell
from utils import setup_directories, delete_logs
from llms.api_queue import start_api_queue, stop_api_queue

async def async_main() -> None:
    # Setup directories
    setup_directories(DATA_DIR)
    
    # Start API queue
    await start_api_queue()
    
    # Initialize shell
    shell = CymbiontShell()
    set_shell(shell)
    
    try:
        # Check if we have a one-shot command
        if len(sys.argv) > 1 and sys.argv[1] == '--test':
            # Set test mode for logging
            if console_handler:
                console_handler.in_test_mode = True
                
            # Run the test command
            if len(sys.argv) > 2:
                test_name = sys.argv[2]
                logger.info(f"Running test: {test_name}")
                success, _ = await shell.execute_command(f'test_{test_name}', '')
                if not success:
                    sys.exit(1)
            else:
                logger.info("Running all tests")
                success, _ = await shell.execute_command('run_all_tests', '')
                if not success:
                    sys.exit(1)
            return
            
        # Normal interactive mode
        await shell.run()
        
    except KeyboardInterrupt:
        logger.debug("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        if DEBUG_ENABLED:
            raise
    finally:
        # Cleanup
        await stop_api_queue()
        token_logger.print_total_tokens()
        delete_logs(DATA_DIR)
        logger.debug("Cymbiont shutdown complete")

def main() -> None:
    """Entry point that runs the async main function"""
    asyncio.run(async_main())

if __name__ == "__main__":
    main()