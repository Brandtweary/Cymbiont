if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path
    
    # Get path to cymbiont.py
    project_root = Path(__file__).parent.parent
    cymbiont_path = project_root / 'cymbiont.py'
    
    # Re-run through cymbiont
    os.execv(sys.executable, [sys.executable, str(cymbiont_path), '--test', 'logger'])
else:
    # Normal imports for when the module is imported properly
    from shared_resources import logger
    from cymbiont_logger.logger_types import LogLevel

    def run_logger_test() -> None:
        """Test all available log levels in the logging system"""
        # Test each log level - will raise an exception if any fail
        logger.debug("This is a DEBUG message")
        logger.info("This is an INFO message")
        logger.log(LogLevel.BENCHMARK, "This is a BENCHMARK message")
        logger.log(LogLevel.PROMPT, "This is a PROMPT message")
        logger.log(LogLevel.RESPONSE, "This is a RESPONSE message")
        logger.warning("This is a WARNING message")
        logger.error("This is an ERROR message")
        logger.critical("This is a CRITICAL message")