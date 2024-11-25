from chat_history import ChatHistory


async def test_progressive_summarization() -> None:
    """Test that progressive summarization works correctly with mock API"""
    # Create chat history with mock enabled
    chat_history = ChatHistory()
    chat_history.mock = True
    
    # Add 10 messages with simple integer content
    for i in range(1, 11):
        chat_history.add_message("user", str(i))
    
    # Add message that exceeds buffer limit
    overflow_message = "- " * chat_history.buffer_word_limit
    chat_history.add_message("user", overflow_message)

    # Wait for any ongoing summarization
    await chat_history.wait_for_summary()
    
    # Get recent messages and verify results
    messages, summary = chat_history.get_recent_messages()
    
    # Verify we got a summary
    assert summary is not None, "Expected a summary to be generated"
    
    # Verify buffer messages length
    assert len(messages) == 1, \
        f"Expected 1 message in buffer, but got {len(messages)}"
    
    # Verify message content
    assert messages[0].content == overflow_message, \
        f"Expected message to be the overflow message, but got '{messages[0].content}'"