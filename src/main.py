# System imports
import asyncio
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
from api_queue import start_api_queue, stop_api_queue
from shared_resources import logger, DATA_DIR
import threading
from cymbiont_shell import CymbiontShell
from utils import setup_directories



def main():
    # Setup directories
    setup_directories(DATA_DIR)
    
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