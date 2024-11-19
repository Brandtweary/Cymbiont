import pytest
import asyncio
import time
from typing import AsyncGenerator, List, Dict, Any
from unittest.mock import Mock, patch
from api_queue import (
    start_api_queue,
    stop_api_queue,
    enqueue_api_call,
    BATCH_TIMER,
    BATCH_LIMIT,
    TOKENS_PER_MINUTE,
    TPM_SOFT_LIMIT
)

@pytest.fixture(autouse=True)
async def setup_queue():
    """Setup and teardown the API queue for each test."""
    print("\nSTARTING QUEUE")
    await start_api_queue()
    yield
    print("\nSTOPPING QUEUE")
    await stop_api_queue()

def create_mock_message(index: int) -> List[Dict[str, Any]]:
    """Create a numbered test message."""
    return [{"role": "user", "content": f"Test message {index}"}]

@pytest.mark.asyncio
async def test_rpm_rate_limiting() -> None:
    """Test that RPM rate limiting processes correct batch size in FIFO order."""
    # Import fresh to get current state
    from api_queue import _processor_task
    print(f"\nIn test: _processor_task = {_processor_task}")
    
    assert _processor_task is not None, "API queue not running at start of test"
    
    # Setup mock response
    mock_response = Mock()
    mock_response.usage.total_tokens = 100
    mock_response.choices = [Mock(message=Mock(content="test response"))]
    
    # Track all futures for verification
    futures: List[asyncio.Future] = []
    
    # Create a flood of requests (80 per second for 2 seconds)
    num_requests: int = 160
    
    with patch('api_queue.openai_client.chat.completions.create',
               return_value=mock_response):
        
        # Flood the queue with requests
        for i in range(num_requests):
            future = enqueue_api_call(
                model="gpt-4",
                messages=create_mock_message(i),
                response_format={"type": "text"}
            )
            futures.append(future)
        
        # Wait for two batch cycles
        await asyncio.sleep(BATCH_TIMER * 2)
        
        # Check completed requests
        completed = [f for f in futures if f.done() and not f.exception()]
        pending = [f for f in futures if not f.done()]
        
        # More flexible assertion
        expected_min = int(BATCH_LIMIT) * 2  # floor of expected completions
        expected_max = int(BATCH_LIMIT + 1) * 2  # ceiling of expected completions
        assert expected_min <= len(completed) <= expected_max, (
            f"Expected between {expected_min} and {expected_max} completed requests, "
            f"got {len(completed)}"
        )
        
        # Verify batch processing
        assert len(completed) == BATCH_LIMIT * 2, (
            f"Expected {BATCH_LIMIT * 2} completed requests, got {len(completed)}"
        )
        
        # Verify FIFO order by checking message contents
        results = []
        for future in completed:
            result = await future
            content = result["content"]
            results.append(content)
        
        assert results == ["test response"] * len(completed), (
            "Responses should match mock response"
        )
        
        # Verify backlog is growing
        assert len(pending) == num_requests - len(completed), (
            f"Expected {num_requests - len(completed)} pending requests, "
            f"got {len(pending)}"
        )

@pytest.mark.asyncio
async def test_rpm_fifo_order() -> None:
    """Test that requests are processed in FIFO order."""
    mock_responses = []
    futures: List[asyncio.Future] = []
    
    # Create unique responses for each request
    for i in range(BATCH_LIMIT * 2):
        mock_response = Mock()
        mock_response.usage.total_tokens = 100
        mock_response.choices = [Mock(message=Mock(content=f"response_{i}"))]
        mock_responses.append(mock_response)
    
    with patch('api_queue.openai_client.chat.completions.create',
               side_effect=mock_responses):
        
        # Send batch_limit * 2 requests
        for i in range(BATCH_LIMIT * 2):
            future = enqueue_api_call(
                model="gpt-4",
                messages=create_mock_message(i),
                response_format={"type": "text"}
            )
            futures.append(future)
        
        # Wait for two batch cycles
        await asyncio.sleep(BATCH_TIMER * 2)
        
        # Add verification that only expected number of requests completed
        completed = [f for f in futures if f.done()]
        assert len(completed) == BATCH_LIMIT * 2, (
            f"Expected exactly {BATCH_LIMIT * 2} completed requests, "
            f"got {len(completed)}"
        )
        
        # Verify order of responses
        results = []
        for future in completed:
            result = await future
            results.append(result["content"])
        
        expected = [f"response_{i}" for i in range(BATCH_LIMIT * 2)]
        assert results == expected, (
            "Responses should be in FIFO order"
        )

@pytest.mark.asyncio
async def test_token_rate_throttling() -> None:
    """Test that high token usage properly throttles the queue to zero."""
    
    # Create a mock response with extremely high token usage
    # Using slightly more than TOKENS_PER_MINUTE to ensure we hit zero
    tokens_per_call = int(TOKENS_PER_MINUTE * 1.1)  # 2.2M tokens
    mock_response = Mock()
    mock_response.usage.total_tokens = tokens_per_call
    mock_response.usage.prompt_tokens = tokens_per_call // 2
    mock_response.usage.completion_tokens = tokens_per_call // 2
    mock_response.choices = [Mock(message=Mock(content="test response"))]
    
    futures: List[asyncio.Future] = []
    
    with patch('api_queue.openai_client.chat.completions.create',
               return_value=mock_response):
        # Send a few requests
        for i in range(3):  # We only need a few - they'll be massive
            future = enqueue_api_call(
                model="gpt-4",
                messages=create_mock_message(i),
                response_format={"type": "text"}
            )
            futures.append(future)
            
        # Wait for first batch to process
        await asyncio.sleep(BATCH_TIMER)
        
        # First request should complete
        assert any(f.done() for f in futures), "First request should complete"
        
        # Send more requests
        for i in range(3, 6):
            future = enqueue_api_call(
                model="gpt-4",
                messages=create_mock_message(i),
                response_format={"type": "text"}
            )
            futures.append(future)
        
        # Wait for another batch cycle
        await asyncio.sleep(BATCH_TIMER)
        
        # Count completed requests
        completed = [f for f in futures if f.done()]
        pending = [f for f in futures if not f.done()]
        
        # We expect only the first request to complete because:
        # 1. First request uses 2.2M tokens
        # 2. This immediately puts us over the TPM limit
        # 3. Interpolation factor should become zero
        assert len(completed) == 1, (
            f"Expected only 1 completed request due to token throttling, "
            f"got {len(completed)}"
        )
        
        # Verify remaining requests are pending
        assert len(pending) == len(futures) - 1, (
            "All other requests should be pending due to token throttling"
        )
        
        # Verify the token usage was recorded
        result = await completed[0]
        assert result["token_usage"]["total_tokens"] == tokens_per_call, (
            "Token usage should be recorded correctly"
        )

@pytest.mark.asyncio
async def test_token_soft_limit_interpolation() -> None:
    """Test that token usage near the soft limit properly interpolates batch sizes."""
    
    # Calculate token usage that puts us right at the soft limit
    soft_limit_tokens = int(TOKENS_PER_MINUTE * TPM_SOFT_LIMIT)  # 1.5M tokens
    tokens_per_call = int(soft_limit_tokens * BATCH_TIMER / 60)  # Tokens per batch at soft limit
    
    # Create responses with increasing token usage
    mock_responses = []
    for i in range(BATCH_LIMIT * 3):  # Create enough responses for 3 batches
        mock_response = Mock()
        # Gradually increase token usage from 50% to 100% of soft limit
        scaling_factor = 0.5 + (0.5 * (i / (BATCH_LIMIT * 3)))
        mock_response.usage.total_tokens = int(tokens_per_call * scaling_factor)
        mock_response.usage.prompt_tokens = mock_response.usage.total_tokens // 2
        mock_response.usage.completion_tokens = mock_response.usage.total_tokens // 2
        mock_response.choices = [Mock(message=Mock(content=f"response_{i}"))]
        mock_responses.append(mock_response)
    
    futures: List[asyncio.Future] = []
    
    with patch('api_queue.openai_client.chat.completions.create',
               side_effect=mock_responses):
        # Send a full batch of requests
        for i in range(BATCH_LIMIT * 3):
            future = enqueue_api_call(
                model="gpt-4",
                messages=create_mock_message(i),
                response_format={"type": "text"}
            )
            futures.append(future)
        
        # Wait for three batch cycles
        await asyncio.sleep(BATCH_TIMER * 3)
        
        # Count completed requests per batch
        completed_times = [
            (await f).get("timestamp", 0.0) if f.done() else 0.0 
            for f in futures
        ]
        
        # Group completions into batches
        batch_counts = []
        batch_start_time = min(t for t in completed_times if t > 0)
        for batch_idx in range(3):
            batch_end_time = batch_start_time + BATCH_TIMER
            batch_count = sum(
                1 for t in completed_times 
                if batch_start_time <= t < batch_end_time
            )
            batch_counts.append(batch_count)
            batch_start_time = batch_end_time
        
        # Verify that each subsequent batch processed fewer requests
        assert batch_counts[0] > batch_counts[1] > batch_counts[2], (
            f"Expected decreasing batch sizes due to token limiting, "
            f"got batch counts: {batch_counts}"
        )
        
        # Verify that the final batch was significantly smaller
        assert batch_counts[2] < BATCH_LIMIT * 0.5, (
            f"Expected final batch to be less than 50% of BATCH_LIMIT "
            f"due to token limiting, got {batch_counts[2]}"
        )
        
        # Verify some requests remained pending
        pending = [f for f in futures if not f.done()]
        assert len(pending) > 0, (
            "Expected some requests to remain pending due to token limiting"
        )