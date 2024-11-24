import asyncio
from typing import List
from api_queue import enqueue_api_call, BATCH_TIMER, BATCH_LIMIT, TOKENS_PER_MINUTE, TPM_SOFT_LIMIT, is_queue_empty, clear_token_history
from shared_resources import logger
from custom_dataclasses import ChatMessage

async def test_rpm_rate_limiting() -> None:
    """Test RPM rate limiting processes correct batch size."""
    num_requests: int = 20  # Reduced from 160 to 20
    futures: List[asyncio.Future] = []
    mock_tokens: int = 100

    for i in range(num_requests):
        future = enqueue_api_call(
            model="gpt-4",
            messages=[ChatMessage(
                role="user",
                content=f"Test message {i}"
            )],
            response_format={"type": "text"},
            mock=True,
            mock_tokens=mock_tokens
        )
        futures.append(future)

    # Wait for two batch cycles
    await asyncio.sleep(BATCH_TIMER * 2)

    # Verify completed requests
    completed = [f for f in futures if f.done() and not f.exception()]
    expected_min = BATCH_LIMIT * 2
    expected_max = (BATCH_LIMIT + 1) * 2
    assert expected_min <= len(completed) <= expected_max, (
        f"Expected between {expected_min} and {expected_max} completed requests, "
        f"got {len(completed)}"
    )
    assert len(completed) == BATCH_LIMIT * 2, (
        f"Expected {BATCH_LIMIT * 2} completed requests, got {len(completed)}"
    )
    assert all(f.result()["content"] == f"Test message {i}" for i, f in enumerate(completed)), (
        "Responses should match mock response"
    )

    # Verify backlog is growing
    pending = [f for f in futures if not f.done()]
    assert len(pending) == num_requests - len(completed), (
        f"Expected {num_requests - len(completed)} pending requests, "
        f"got {len(pending)}"
    )

async def test_tpm_throttle() -> None:
    """Test that high token usage properly throttles the queue."""
    # Step 1: Enqueue a call that exceeds the TPM limit
    tokens_per_call: int = int(TOKENS_PER_MINUTE * 1.1)  # Exceeds TPM limit
    high_token_call = enqueue_api_call(
        model="gpt-4",
        messages=[ChatMessage(
            role="user",
            content="High token usage test"
        )],
        response_format={"type": "text"},
        mock=True,
        mock_tokens=tokens_per_call
    )

    # Step 2: Wait for the high token call to be processed
    await asyncio.sleep(BATCH_TIMER)
    assert high_token_call.done() and not high_token_call.exception(), "High token call did not complete as expected."

    # Step 3: Enqueue additional API calls subject to throttling
    new_futures: List[asyncio.Future] = []
    for i in range(3):
        future = enqueue_api_call(
            model="gpt-4",
            messages=[ChatMessage(
                role="user",
                content=f"Throttled message {i}"
            )],
            response_format={"type": "text"},
            mock=True,
            mock_tokens=100  # Regular token usage
        )
        new_futures.append(future)

    # Step 4: Wait for the new batch to be processed
    await asyncio.sleep(BATCH_TIMER * 1.5)  # Slightly extended sleep for processing

    # Step 5: Verify that throttling has been applied
    completed = [f for f in new_futures if f.done() and not f.exception()]
    expected_max = 1  # Expecting at most 1 processed due to throttling
    assert len(completed) <= expected_max, (
        f"Expected at most {expected_max} completed requests due to token throttling, got {len(completed)}"
    )

    pending = [f for f in new_futures if not f.done()]
    assert len(pending) >= 2, (
        f"Expected at least 2 pending requests due to token throttling, got {len(pending)}"
    )

async def test_tpm_soft_limit() -> None:
    """Test that token usage near the soft limit properly throttles the queue."""
    # Step 1: Enqueue a call that exceeds the TPM soft limit
    tokens_per_call: int = int(TOKENS_PER_MINUTE * TPM_SOFT_LIMIT * 1.1)  # 10% over soft limit
    high_token_call = enqueue_api_call(
        model="gpt-4",
        messages=[ChatMessage(
            role="user",
            content="High token usage test"
        )],
        response_format={"type": "text"},
        mock=True,
        mock_tokens=tokens_per_call
    )

    # Step 2: Wait for the high token call to be processed
    await asyncio.sleep(BATCH_TIMER * 2)  # Allow sufficient time for processing
    assert high_token_call.done() and not high_token_call.exception(), "High token call did not complete as expected."

    # Step 3: Enqueue additional API calls subject to throttling
    new_futures: List[asyncio.Future] = []
    for i in range(3):
        future = enqueue_api_call(
            model="gpt-4",
            messages=[ChatMessage(
                role="user",
                content=f"Throttled message {i}"
            )],
            response_format={"type": "text"},
            mock=True,
            mock_tokens=100  # Regular token usage
        )
        new_futures.append(future)

    # Step 4: Wait for the new batch to be processed
    await asyncio.sleep(BATCH_TIMER * 2)  # Allow time for throttling to take effect

    # Step 5: Verify that throttling has been applied correctly
    completed = [f for f in new_futures if f.done() and not f.exception()]
    expected_max = 0  # Since the high token call exceeded the soft limit, expecting no new calls to process
    assert len(completed) <= expected_max, (
        f"Expected at most {expected_max} completed requests due to token throttling, got {len(completed)}"
    )

    pending = [f for f in new_futures if not f.done()]
    assert len(pending) == len(new_futures), (
        f"Expected all requests to be pending due to token throttling, got {len(pending)} pending."
    )

async def test_retry_mechanism() -> None:
    """Test that API calls retry properly through various failure cases."""
    from tag_extraction import extract_tags
    from custom_dataclasses import Chunk, ProcessLog

    test_cases = [
        {
            "name": "empty_response",
            "mock_content": "",
            "expected_retries": 3,
            "expected_tags": []
        },
        {
            "name": "invalid_json",
            "mock_content": "not json at all",
            "expected_retries": 3,
            "expected_tags": []
        },
        {
            "name": "empty_tag_array",
            "mock_content": '{"tags": []}',
            "expected_retries": 3,
            "expected_tags": []
        },
        {
            "name": "execution_error",
            "mock_content": "halt and catch fire",  # Our special error trigger
            "expected_retries": 3,
            "expected_tags": []
        },
        {
            "name": "success_case",
            "mock_content": '{"tags": ["final", "success"]}',
            "expected_retries": 1,
            "expected_tags": ["final", "success"]
        }
    ]

    for case in test_cases:
        # Create fresh test objects for each case
        chunk = Chunk(
            chunk_id=f"test_{case['name']}",
            doc_id="test_doc",
            text="This is a test chunk that needs tags.",
            position=0,
            metadata={},
            tags=None
        )
        process_log = ProcessLog(name=f"test_{case['name']}", logger=logger)

        await clear_token_history()
        
        # Handle the expected error case
        try:
            await extract_tags(chunk, process_log, mock=True, mock_content=case["mock_content"])
        except RuntimeError as e:
            if case["name"] == "execution_error":
                # Verify the error message matches our expectation
                assert str(e) == "🔥 The system caught fire, as requested", (
                    f"Expected specific error message, got: {str(e)}"
                )
            else:
                raise  # Re-raise if this wasn't the expected error case
        
        # For non-error cases, verify tags
        if case["name"] != "execution_error":
            assert chunk.tags == case["expected_tags"], (
                f"{case['name']}: Expected tags {case['expected_tags']}, got {chunk.tags}"
            )

        # Check final attempt count
        final_attempt_msgs = [msg for msg in process_log.messages if "Final attempt count:" in msg[1]]
        assert len(final_attempt_msgs) == 1, "Expected exactly one final attempt count message"
        final_count = int(final_attempt_msgs[0][1].split(": ")[1])
        assert final_count == case["expected_retries"], (
            f"{case['name']}: Expected {case['expected_retries']} attempts, got {final_count}"
        )


async def run_api_queue_tests() -> tuple[int, int]:
    """Execute all API queue tests sequentially.
    Returns: Tuple of (passed_tests, failed_tests)"""
    tests = [
        test_rpm_rate_limiting,
        test_tpm_throttle,
        test_tpm_soft_limit,
        test_retry_mechanism
    ]
    passed = 0
    failed = 0

    for test in tests:
        logger.info(f"Starting {test.__name__}")
        try:
            await clear_token_history() # needs to be called before in order to reset TPM throttle
            await empty_api_queue()
            await clear_token_history() # needs to be called again to clear out tokens from emptying queue
            await test()
            logger.info(f"Completed {test.__name__}")
            print(f"\033[32m✓ {test.__name__} passed.\033[0m\n")
            passed += 1
        except (AssertionError, Exception) as e:
            logger.error(f"{test.__name__} failed: {str(e)}")
            print(f"\033[31m{test.__name__} failed: {str(e)}\033[0m\n")
            failed += 1
    
    return passed, failed

async def empty_api_queue() -> None:
    """Ensure the API queue is empty before running the next test."""
    logger.debug("Emptying API queue...")
    while not is_queue_empty():
        await asyncio.sleep(0.1)
    logger.debug("API queue is empty.")