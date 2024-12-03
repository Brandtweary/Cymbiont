"""Cymbiont Testing Framework

This package implements a specialized testing framework for Cymbiont that ensures all tests
are run in a fully operational instance of the program. This is necessary because most test
modules require access to the complete Cymbiont environment, including the interactive shell,
logging system, and other dependencies that can't be easily initialized in isolation.

Test Routing System
-----------------
All test executions from the command line are ultimately routed through `cymbiont.py --test [test_name]`, which:
1. Creates a temporary Cymbiont instance
2. Sets up all required dependencies
3. Runs the specified test(s) using the shell
4. Exits immediately afterwards

Creating New Test Modules
-----------------------
To create a new test module that integrates with this system:

1. Create a new file in the tests/ directory named test_[name].py
2. Add the following routing boilerplate at the top of the file:
   ```python
   if __name__ == "__main__":
       import os
       import sys
       from pathlib import Path
       
       # Get path to cymbiont.py
       project_root = Path(__file__).parent.parent
       cymbiont_path = project_root / 'cymbiont.py'
       
       # Re-run through cymbiont
       os.execv(sys.executable, [sys.executable, str(cymbiont_path), '--test', '[name]'])
   else:
       # Your normal imports here
       from shared_resources import ...
   ```

3. Define your test function:
   ```python
   def run_[name]_test() -> None:
       '''Test description'''
       # Your test code here
       # Raise an exception if test fails
   ```

4. Create and register the test command in src/cymbiont_shell/test_commands.py:
   ```python
   async def do_test_[name](shell, args: str) -> None:
       '''Test description.'''
       try:
           # For tests that return (passed, failed) counts:
           passed, failed = await run_[name]_test()
           shell.test_successes = passed
           shell.test_failures = failed
           if failed == 0:
               logger.info("✓ All [name] tests passed")
           else:
               logger.error(f"✗ {failed} [name] test(s) failed")
           
           # OR for tests that raise exceptions on failure:
           run_[name]_test()  # Will raise an exception if test fails
           shell.test_successes = 1
           shell.test_failures = 0
           logger.info("✓ [Name] tests passed")
       except Exception as e:
           logger.error(f"✗ [Name] tests failed: {str(e)}")
           shell.test_successes = 0
           shell.test_failures = 1
   ```

5. Register the command in CymbiontShell (src/cymbiont_shell/cymbiont_shell.py):
   - Add to COMMAND_METADATA:
     ```python
     'test_[name]': {'takes_args': False}
     ```
   - Add to self.commands in __init__:
     ```python
     'test_[name]': self.do_test_[name]
     ```
   - Add to self.command_mapping in __init__:
     ```python
     'test_[name]': do_test_[name]
     ```

Example:
See tests/test_logger.py and src/cymbiont_shell/test_commands.py for complete examples
of properly structured test modules and commands.
"""

import os
import sys
from pathlib import Path
from typing import Optional

def run_via_cymbiont(test_name: Optional[str] = None) -> None:
    """
    Run tests through cymbiont.py instead of directly.
    This ensures proper environment setup and consistent test execution.
    
    Args:
        test_name: Optional name of specific test to run. If None, runs all tests.
    """
    project_root = Path(__file__).parent.parent
    cymbiont_path = project_root / 'cymbiont.py'
    
    # Build the command
    args = [sys.executable, str(cymbiont_path), '--test']
    if test_name:
        # Strip 'test_' prefix if present
        test_name = test_name.replace('test_', '')
        args.append(test_name)
    
    # Replace current process with cymbiont.py
    os.execv(sys.executable, args)

# Handle both package-level and module-level test execution
if __name__ == '__main__':
    # Running the whole test package (python -m tests)
    run_via_cymbiont()
elif '.' in __name__:
    # Running a specific test module (python -m tests.test_logger)
    test_name = __name__.split('.')[-1]
    run_via_cymbiont(test_name)