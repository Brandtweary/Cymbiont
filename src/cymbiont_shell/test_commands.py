from shared_resources import logger, console_filter
from tests.test_api_queue import run_api_queue_tests
from tests.test_document_processing import run_document_processing_tests
from tests.test_logger import run_logger_test
from tests.test_parsing import run_text_parsing_test
from tests.test_progressive_summarization import run_progressive_summarization_test
from tests.test_agent_tools import run_agent_tool_tests


async def do_test_api_queue(shell, args: str) -> None:
    """Run API queue tests."""
    try:
        passed, failed = await run_api_queue_tests()  # Already returns (passed, failed)
        shell.test_successes = passed
        shell.test_failures = failed
        if failed == 0:
            logger.info("✓ All API queue tests passed")
        else:
            logger.error(f"✗ {failed} API queue test(s) failed")
    except Exception as e:
        logger.error(f"✗ API queue tests failed: {str(e)}")
        shell.test_successes = 0
        shell.test_failures = 1


async def do_test_document_processing(shell, args: str) -> None:
    """Run document processing tests."""
    try:
        passed, failed = await run_document_processing_tests()  # Already returns (passed, failed)
        shell.test_successes = passed
        shell.test_failures = failed
        if failed == 0:
            logger.info("✓ All document processing tests passed")
        else:
            logger.error(f"✗ {failed} document processing test(s) failed")
    except Exception as e:
        logger.error(f"Document processing tests failed: {str(e)}")
        shell.test_successes = 0
        shell.test_failures = 1


async def do_test_logger(shell, args: str) -> None:
    """Test all logging levels with colored output."""
    try:
        run_logger_test()  # Will raise an exception if test fails
        shell.test_successes = 1
        shell.test_failures = 0
        logger.info("✓ Logger tests passed")
    except Exception as e:
        logger.error(f"✗ Logger tests failed: {str(e)}")
        shell.test_successes = 0
        shell.test_failures = 1


async def do_test_parsing(shell, args: str) -> None:
    """Run text parsing tests."""
    try:
        run_text_parsing_test()  # Will raise an exception if test fails
        shell.test_successes = 1
        shell.test_failures = 0
        logger.info("✓ Text parsing tests passed")
    except Exception as e:
        logger.error(f"✗ Text parsing tests failed: {str(e)}")
        shell.test_successes = 0
        shell.test_failures = 1


async def do_test_progressive_summarization(shell, args: str) -> None:
    """Test progressive summarization functionality."""
    try:
        await run_progressive_summarization_test()  # Will raise an exception if test fails
        shell.test_successes = 1
        shell.test_failures = 0
        logger.info("✓ Progressive summarization tests passed")
    except Exception as e:
        logger.error(f"✗ Progressive summarization tests failed: {str(e)}")
        shell.test_successes = 0
        shell.test_failures = 1


async def do_test_agent_tools(shell, args: str) -> None:
    """Run agent tools tests."""
    try:
        passed, failed = await run_agent_tool_tests()
        shell.test_successes = passed
        shell.test_failures = failed
        if failed == 0:
            logger.info("✓ All agent tools tests passed")
        else:
            logger.error(f"✗ {failed} agent tools test(s) failed")
    except Exception as e:
        logger.error(f"✗ Agent tools tests failed: {str(e)}")
        shell.test_successes = 0
        shell.test_failures = 1


async def do_run_all_tests(shell, args: str) -> None:
    """Run all tests

    Usage: run_all_tests [-v | --verbose]
        -verbose flag to show all logs
    """
    # Parse args for standard flags
    args_list = args.split()
    verbose = any(arg in ('-v', '--verbose') for arg in args_list)
    
    test_commands = [cmd for cmd in shell.commands.keys() if cmd.startswith('test_')]
    total_successes = 0
    total_failures = 0
    failed_tests: list[tuple[str, str]] = []
        
    try:
        if not verbose:
            console_filter.quiet = True
            
        for cmd in test_commands:
            try:
                # Reset test counters before each test
                shell.test_successes = 0
                shell.test_failures = 0
                
                # Run the test
                method = shell.commands[cmd]
                await method('')
                
                # Accumulate results
                total_successes += shell.test_successes
                total_failures += shell.test_failures
                
                if shell.test_failures > 0:
                    failed_tests.append((cmd, f"{shell.test_failures} tests failed"))
                    logger.error(f"❌ {cmd} failed\n")
                else:
                    logger.info(f"✅ {cmd} passed\n")
                    
            except Exception as e:
                total_failures += 1
                failed_tests.append((cmd, str(e)))
                logger.error(f"❌ {cmd} failed\n")

    finally:
        # Restore console output
        if not verbose:
            console_filter.quiet = False

    total_tests = total_successes + total_failures
    success_rate = (total_successes / total_tests) * 100 if total_tests > 0 else 0

    # Always show final results
    logger.info("\n=== Test Results ===")
    logger.info(f"Tests Run: {total_tests}")
    logger.info(f"Passed: {total_successes}")
    logger.info(f"Failed: {total_failures}")
    logger.info(f"Success Rate: {success_rate:.1f}%\n")

    if failed_tests:
        logger.info("Failed Tests:")
        for cmd, error in failed_tests:
            logger.error(f"❌ {cmd}: {error}")

    if success_rate == 100:
        logger.info("""
🎉 Perfect Score! 🎉
┌────────────────┐
│   100% PASS    │
│    ⭐ ⭐ ⭐    │
└────────────────┘
        """)
    elif success_rate >= 80:
        logger.info("""
😊 Almost There! 
┌────────────────┐
│   Keep Going!  │
│    ⭐ ⭐       │
└────────────────┘
        """)
    else:
        logger.info("""
😢 Needs Work 
┌────────────────┐
│   Don't Give   │
│     Up! 💪     │
└────────────────┘
        """)
