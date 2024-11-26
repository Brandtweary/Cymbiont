from shared_resources import logger
from constants import LogLevel

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