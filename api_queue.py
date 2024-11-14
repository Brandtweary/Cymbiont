import asyncio
import time
from typing import Any, Callable, Optional

RATE_LIMIT_PER_MINUTE = 5000
RATE_LIMIT_TOKENS_PER_MINUTE = 2_000_000
MAX_CONCURRENT_REQUESTS = 16

# Calculate requests per 0.1 seconds
REQUESTS_PER_TENTH_SECOND = RATE_LIMIT_PER_MINUTE / 600  # ≈8.33

# Token usage tracking
token_usage: list[tuple[float, int]] = []  # List of (timestamp, tokens)

async def rate_limit():
    # Throttle based on RPM
    while True:
        current_time = time.time()
        # Remove calls older than 60 seconds
        while token_usage and token_usage[0][0] < current_time - 60:
            token_usage.pop(0)
        
        # Calculate tokens used in the last minute
        tokens_last_minute = sum(tokens for _, tokens in token_usage)
        
        if tokens_last_minute >= RATE_LIMIT_TOKENS_PER_MINUTE:
            sleep_time = 1  # Wait a second before rechecking
            await asyncio.sleep(sleep_time)
            continue
        
        break

async def worker(queue: asyncio.Queue, semaphore: asyncio.Semaphore):
    while True:
        priority, func, args, kwargs, callback = await queue.get()
        await rate_limit()
        async with semaphore:
            try:
                result = await func(*args, **kwargs)
                if callback:
                    callback(result)
            except Exception as e:
                if callback:
                    callback(e)
        queue.task_done()

async def initialize_queue():
    queue = asyncio.PriorityQueue()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    for _ in range(MAX_CONCURRENT_REQUESTS):
        asyncio.create_task(worker(queue, semaphore))
    return queue

async_queue: Optional[asyncio.PriorityQueue] = None

def enqueue_api_call(
    func: Callable[..., Any],
    *args: Any,
    priority: int = 1,  # Lower numbers indicate higher priority
    callback: Optional[Callable[[Any], None]] = None,
    **kwargs: Any
) -> None:
    if async_queue is None:
        raise RuntimeError("API queue not initialized. Call `start_api_queue` first.")
    async_queue.put_nowait((priority, func, args, kwargs, callback))

async def start_api_queue():
    global async_queue
    if async_queue is None:
        async_queue = await initialize_queue()