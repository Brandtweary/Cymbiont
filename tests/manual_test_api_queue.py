import asyncio
from api_queue import start_api_queue, stop_api_queue, enqueue_api_call
from unittest.mock import patch, Mock

async def test_api_queue():
    print("Starting API queue...")
    await start_api_queue()
    
    # Setup mock response
    mock_response = Mock()
    mock_response.usage.total_tokens = 100
    mock_response.choices = [Mock(message=Mock(content="test response"))]
    
    # Track futures
    futures = []
    
    with patch('api_queue.openai_client.chat.completions.create', return_value=mock_response):
        # Send some test requests
        for i in range(5):
            future = enqueue_api_call(
                model="gpt-4",
                messages=[{"role": "user", "content": f"Test message {i}"}],
                response_format={"type": "text"}
            )
            futures.append(future)
        
        # Wait for results
        print("Waiting for results...")
        results = await asyncio.gather(*futures)
        
        # Check results
        for i, result in enumerate(results):
            print(f"Result {i}: {result}")
    
    print("Stopping API queue...")
    await stop_api_queue()

if __name__ == "__main__":
    asyncio.run(test_api_queue())