# System imports
from pathlib import Path
import sys
import asyncio

def setup_python_path() -> None:
    """Add project directories to Python path."""
    project_root = Path(__file__).parent.parent
    src_path = project_root / 'src'
    tests_path = project_root / 'tests'
    
    # Add to front of sys.path in reverse order so project_root ends up first
    sys.path.insert(0, str(tests_path))
    sys.path.insert(0, str(src_path))
    sys.path.insert(0, str(project_root))

# Call setup before project imports
setup_python_path()

# Project imports
from shared_resources import logger, DATA_DIR, set_shell, DEBUG_ENABLED
from cymbiont_logger.token_logger import token_logger
from cymbiont_shell.cymbiont_shell import CymbiontShell
from utils import setup_directories, delete_logs
from llms.api_queue import start_api_queue, stop_api_queue
from llms.model_configuration import initialize_model_configuration
from llms.model_registry import registry

async def async_main() -> None:
    # Setup directories
    setup_directories(DATA_DIR)
    
    # Initialize models
    model_config = initialize_model_configuration()
    if not model_config:
        logger.error("Failed to initialize any models. Exiting.")
        sys.exit(1)
    registry.initialize(model_config)
    
    # Start API queue
    await start_api_queue()
    
    # Initialize shell
    shell = CymbiontShell()
    set_shell(shell)
    
    try:
        # Check if we have a one-shot command
        if len(sys.argv) > 1 and sys.argv[1] == '--test':
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
        logger.error("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        if DEBUG_ENABLED:
            raise
    finally:
        # Cleanup
        await stop_api_queue()
        token_logger.print_total_tokens()
        delete_logs(DATA_DIR)
        logger.info("Cymbiont shutdown complete")

def main() -> None:
    """Entry point that runs the async main function"""
    asyncio.run(async_main())

if __name__ == "__main__":
    main()