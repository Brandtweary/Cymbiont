if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path
    
    # Get path to cymbiont.py
    project_root = Path(__file__).parent.parent
    cymbiont_path = project_root / 'cymbiont.py'
    
    # Re-run through cymbiont
    os.execv(sys.executable, [sys.executable, str(cymbiont_path), '--test', 'progressive_summarization'])
else:
    # Normal imports for when the module is imported properly
    from agents.chat_history import ChatHistory
    from shared_resources import logger

async def run_progressive_summarization_test() -> None:
    """Test that progressive summarization works correctly with mock API"""
    try:
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
        
        # Verify we got the correct summary
        assert summary == "Progressive summary: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10", \
            f"Expected summary to be 'Progressive summary: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10', but got '{summary}'"
        
        # Verify buffer messages length
        assert len(messages) == 1, \
            f"Expected 1 message in buffer, but got {len(messages)}"
        
        # Verify message content
        assert messages[0].content == overflow_message, \
            f"Expected message to be the overflow message, but got '{messages[0].content}'"
    except Exception as e:
        logger.error(f"Progressive summarization test failed: {str(e)}")