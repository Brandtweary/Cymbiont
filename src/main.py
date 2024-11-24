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
from shared_resources import logger, DATA_DIR
from cymbiont_shell import CymbiontShell
from utils import setup_directories, delete_logs
from api_queue import start_api_queue, stop_api_queue

async def async_main() -> None:
    # Setup directories
    setup_directories(DATA_DIR)
    
    # Start API queue
    await start_api_queue()
    
    try:
        # Create and run shell
        shell = CymbiontShell()
        await shell.run()
        
    except KeyboardInterrupt:
        logger.debug("Keyboard interrupt received")
    finally:
        # Cleanup
        await stop_api_queue()
        delete_logs(DATA_DIR)
        logger.debug("Cymbiont shutdown complete")

def main() -> None:
    """Entry point that runs the async main function"""
    asyncio.run(async_main())

if __name__ == "__main__":
    main()