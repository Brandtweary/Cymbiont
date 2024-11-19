import asyncio
import cmd
from typing import Optional
from api_queue import start_api_queue, stop_api_queue
from documents import process_documents
from shared_resources import DATA_DIR, logger
import threading

# ANSI color codes
GREEN = "\033[32m"
BLUE = "\033[34m"
RESET = "\033[0m"

class CymbiontShell(cmd.Cmd):
    intro = f'{GREEN}Welcome to Cymbiont. Type help or ? to list commands.{RESET}\n'
    prompt = f'{BLUE}cymbiont>{RESET} '
    
    def __init__(self):
        super().__init__()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        
    def do_process_documents(self, arg: str) -> None:
        """Process documents in the data directory.
        Usage: process_documents"""
        if self.loop is None:
            logger.error("Error: Event loop not initialized")
            return
            
        try:
            future = asyncio.run_coroutine_threadsafe(
                process_documents(DATA_DIR),
                self.loop
            )
            result = future.result(timeout=300)
        except Exception as e:
            logger.error(f"Document processing failed: {str(e)}")
    
    def do_exit(self, arg: str) -> bool:
        """Exit the Cymbiont shell"""
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
        return True

def main():
    # Start API queue in the main thread's event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Start API queue
        loop.run_until_complete(start_api_queue())
        
        # Create shell with access to the loop
        shell = CymbiontShell()
        shell.loop = loop
        
        # Run the shell with the loop in a separate thread
        shell_thread = threading.Thread(target=shell.cmdloop)
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