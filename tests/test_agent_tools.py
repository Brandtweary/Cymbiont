if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path
    
    # Get path to cymbiont.py
    project_root = Path(__file__).parent.parent
    cymbiont_path = project_root / 'cymbiont.py'
    
    # Re-run through cymbiont
    os.execv(sys.executable, [sys.executable, str(cymbiont_path), '--test', 'agent_tools'])
else:
    import json
    from typing import Set
    from agents.chat_agent import ChatAgent
    from agents.tool_agent import ToolAgent
    from agents.chat_history import ChatHistory
    from agents.tool_helpers import validate_tool_args
    from constants import ToolName
    from custom_dataclasses import ChatMessage
    from shared_resources import logger

    async def test_tool_loop():
        # Create a chat history with a simple user message
        chat_history = ChatHistory()
        chat_history.add_message("user", "Let's think about this carefully.")
        chat_agent = ChatAgent(chat_history)
        
        # Set up mock messages that will be returned by execute_call
        # Note: Messages are in reverse order since they'll be popped from the end
        
        # First message will be for exit_loop
        exit_message = "After careful consideration, here's what I think..."
        exit_tool_call = {
            "tool_calls": [{
                "function": {
                    "name": "exit_loop",
                    "arguments": json.dumps({"exit_message": exit_message})
                }
            }]
        }
        
        # Second message will be for message_self
        thought_message = "I should consider all angles of this problem..."
        message_self_tool_call = {
            "tool_calls": [{
                "function": {
                    "name": "message_self",
                    "arguments": json.dumps({"message": thought_message})
                }
            }]
        }
        
        mock_messages = [exit_tool_call, message_self_tool_call]
        
        # Run the contemplation loop with mock messages
        response = await chat_agent.get_chat_response(
            tools={ToolName.MESSAGE_SELF, ToolName.EXIT_LOOP},
            mock=True,
            mock_messages=mock_messages
        )
        
        # Check that the final response matches our exit message
        assert response == f"[CONTEMPLATION_LOOP] {exit_message}", \
            f"Expected '[CONTEMPLATION_LOOP] {exit_message}', got '{response}'"
        
        logger.info("✓ test_tool_loop passed")

    async def test_arg_validation():
        # Test 1: Invalid tool name
        args, error = validate_tool_args(
            "not_a_real_tool",
            {},
            {ToolName.CONTEMPLATE_LOOP}
        )
        assert args is None
        assert error is not None and "Invalid tool name" in error

        # Test 2: Tool not in available tools
        args, error = validate_tool_args(
            "contemplate_loop",
            {},
            {ToolName.MESSAGE_SELF}  # Only message_self available
        )
        assert args is None
        assert error is not None and "not in the available tools list" in error

        # Test 3: Missing required parameters
        args, error = validate_tool_args(
            "contemplate_loop",
            {},  # Missing 'question' parameter
            {ToolName.CONTEMPLATE_LOOP}
        )
        assert args is None
        assert error is not None and "Missing required parameters" in error

        # Test 4: Unrecognized arguments
        args, error = validate_tool_args(
            "contemplate_loop",
            {"question": "test", "invalid_arg": "value"},
            {ToolName.CONTEMPLATE_LOOP}
        )
        assert args is None
        assert error is not None and "Unrecognized arguments" in error

        # Test 5: Valid case for comparison
        args, error = validate_tool_args(
            "contemplate_loop",
            {"question": "test"},
            {ToolName.CONTEMPLATE_LOOP}
        )
        assert args == {"question": "test"} and error is None

    async def test_token_budget():
        # Create a chat history with a simple user message
        chat_history = ChatHistory()
        chat_history.add_message("user", "Let's think about this carefully.")
        chat_agent = ChatAgent(chat_history)
        
        # Set up mock messages with token usage that will exceed budget
        message_self_tool_call = {
            "tool_calls": [{
                "function": {
                    "name": "message_self",
                    "arguments": json.dumps({"message": "Thinking..."})
                }
            }],
            "token_usage": {
                "total_tokens": 15000  # High token usage
            }
        }
        
        mock_messages = [message_self_tool_call]
        
        # Run with a low token budget
        response = await chat_agent.get_chat_response(
            tools={ToolName.MESSAGE_SELF},
            token_budget=10000,  # Lower than the mock usage
            mock=True,
            mock_messages=mock_messages
        )
        
        # Verify we get the token budget exceeded message
        assert "token budget has been exceeded" in response.lower(), \
            f"Expected token budget exceeded message, got: {response}"
        
        logger.info("✓ test_token_budget passed")

    async def test_tool_agent():
        # Create a chat history with a simple user message
        chat_history = ChatHistory()
        chat_history.add_message("user", "Can you help me with this code?")
        tool_agent = ToolAgent(chat_history)
        
        # Set up mock tool call response
        tool_call = {
            "tool_calls": [{
                "function": {
                    "name": "introduce_self",
                    "arguments": "{}"
                }
            }]
        }
        
        mock_messages = [tool_call]
        
        # Run the tool agent with mock messages
        response = await tool_agent.get_tool_response(
            tools={ToolName.INTRODUCE_SELF},
            mock=True,
            mock_messages=mock_messages
        )
        
        # Verify we get a response (actual content will depend on introduce_self implementation)
        assert response is not None, "Expected a response from tool agent"
        
        logger.info("✓ test_tool_agent passed")

    async def run_agent_tool_tests() -> tuple[int, int]:
        """Execute all agent tool tests sequentially.

        Returns:
            Tuple of (passed_tests, failed_tests)
        """
        tests = [
            test_tool_loop,
            test_arg_validation,
            test_token_budget,
            test_tool_agent
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                await test()
                passed += 1
            except Exception as e:
                logger.error(f"Test {test.__name__} failed: {str(e)}")
                failed += 1
        
        return passed, failed