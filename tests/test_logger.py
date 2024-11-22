from shared_resources import logger
from logging_config import BENCHMARK, PROMPT, RESPONSE

def run_logger_test() -> None:
    """Test all available log levels in the logging system"""
    logger.debug("This is a DEBUG message")
    logger.info("This is an INFO message")
    logger.log(BENCHMARK, "This is a BENCHMARK message")
    logger.log(PROMPT, "This is a PROMPT message")
    logger.log(RESPONSE, "This is a RESPONSE message")
    logger.warning("This is a WARNING message")
    logger.error("This is an ERROR message")
    logger.critical("This is a CRITICAL message")