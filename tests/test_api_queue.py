if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path
    
    # Get path to cymbiont.py
    project_root = Path(__file__).parent.parent
    cymbiont_path = project_root / 'cymbiont.py'
    
    # Re-run through cymbiont
    os.execv(sys.executable, [sys.executable, str(cymbiont_path), '--test', 'api_queue'])
else:
    # Normal imports for when the module is imported properly
    import asyncio
    from typing import List
    from shared_resources import logger
    from llms.api_queue import (
        enqueue_api_call, 
        BATCH_INTERVAL_TIME, 
        TPM_SOFT_LIMIT, 
        clear_token_history,
        is_queue_empty
    )
    from llms.llm_types import LLM, ChatMessage
    from llms.model_configuration import model_data

async def test_rpm_rate_limiting() -> None:
    """Test RPM rate limiting processes correct batch size."""
    model = LLM.GPT_4O.value
    model_config = model_data[model]
    rpm_limit = model_config["requests_per_minute"]
    batch_limit = int(rpm_limit * BATCH_INTERVAL_TIME / 60)  # Calculate how many requests we can make per batch
    num_requests: int = batch_limit * 4  # Request 4 batches worth
    futures: List[asyncio.Future] = []
    mock_tokens: int = 100

    for i in range(num_requests):
        future = enqueue_api_call(
            model=model,
            messages=[ChatMessage(
                role="user",
                content=f"Test message {i}"
            )],
            mock=True,
            mock_tokens=mock_tokens,
            system_message="mock system message"
        )
        futures.append(future)

    # Wait for two batch cycles
    await asyncio.sleep(BATCH_INTERVAL_TIME * 2)

    # Verify completed requests
    completed = [f for f in futures if f.done() and not f.exception()]
    expected = batch_limit * 2  # Should complete 2 batches worth
    assert len(completed) == expected, (
        f"Expected {expected} completed requests, got {len(completed)}"
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
    model = LLM.GPT_4O.value
    model_config = model_data[model]
    tpm_limit = model_config["total_tokens_per_minute"]

    # Step 1: Enqueue a call that exceeds the TPM limit
    tokens_per_call: int = int(tpm_limit * 1.1)  # Exceeds TPM limit
    high_token_call = enqueue_api_call(
        model=model,
        messages=[ChatMessage(
            role="user",
            content="High token usage test"
        )],
        mock=True,
        mock_tokens=tokens_per_call,
        system_message="mock system message"
    )

    # Step 2: Wait for the high token call to be processed
    await asyncio.sleep(BATCH_INTERVAL_TIME)
    assert high_token_call.done() and not high_token_call.exception(), "High token call did not complete as expected."

    # Step 3: Enqueue additional API calls subject to throttling
    new_futures: List[asyncio.Future] = []
    for i in range(3):
        future = enqueue_api_call(
            model=model,
            messages=[ChatMessage(
                role="user",
                content=f"Throttled message {i}"
            )],
            mock=True,
            mock_tokens=100,  # Regular token usage
            system_message="mock system message"
        )
        new_futures.append(future)

    # Step 4: Wait for the new batch to be processed
    await asyncio.sleep(BATCH_INTERVAL_TIME * 1.5)  # Slightly extended sleep for processing

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
    model = LLM.GPT_4O.value
    model_config = model_data[model]
    tpm_limit = model_config["total_tokens_per_minute"]

    # Step 1: Enqueue a call that exceeds the TPM soft limit
    tokens_per_call: int = int(tpm_limit * TPM_SOFT_LIMIT * 1.1)  # 10% over soft limit
    high_token_call = enqueue_api_call(
        model=model,
        messages=[ChatMessage(
            role="user",
            content="High token usage test"
        )],
        mock=True,
        mock_tokens=tokens_per_call,
        system_message="mock system message"
    )

    # Step 2: Wait for the high token call to be processed
    await asyncio.sleep(BATCH_INTERVAL_TIME * 2)  # Allow sufficient time for processing
    assert high_token_call.done() and not high_token_call.exception(), "High token call did not complete as expected."

    # Step 3: Enqueue additional API calls subject to throttling
    new_futures: List[asyncio.Future] = []
    for i in range(3):
        future = enqueue_api_call(
            model=model,
            messages=[ChatMessage(
                role="user",
                content=f"Throttled message {i}"
            )],
            mock=True,
            mock_tokens=100,  # Regular token usage
            system_message="mock system message"
        )
        new_futures.append(future)

    # Step 4: Wait for the new batch to be processed
    await asyncio.sleep(BATCH_INTERVAL_TIME * 2)  # Allow time for throttling to take effect

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
    from knowledge_graph.tag_extraction import extract_tags
    from knowledge_graph.knowledge_graph_types import Chunk
    from cymbiont_logger.process_log import ProcessLog

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
        logger.info(f"Running {test.__name__}...")
        try:
            await clear_token_history()  # Reset TPM throttle
            await empty_api_queue()
            await clear_token_history()  # Clear tokens from emptying queue
            await test()
            logger.info(f"✓ {test.__name__} passed\n")
            passed += 1
        except Exception as e:
            logger.error(f"✗ {test.__name__} failed: {str(e)}\n")
            failed += 1
    
    return passed, failed

async def empty_api_queue() -> None:
    """Ensure the API queue is empty before running the next test."""
    logger.debug("Emptying API queue...")
    while not is_queue_empty():
        await asyncio.sleep(0.1)
    logger.debug("API queue is empty.")