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
        
        # First will be exit_loop
        exit_message = "After careful consideration, here's what I think..."
        exit_tool_call = {
            "tool_call_results": {
                "exit_loop": {
                    "tool_name": "exit_loop",
                    "arguments": {
                        "exit_message": exit_message
                    }
                }
            }
        }
        
        # Second will be message_self
        thought_message = "I should consider all angles of this problem..."
        message_self_tool_call = {
            "tool_call_results": {
                "message_self": {
                    "tool_name": "message_self",
                    "arguments": {
                        "message": thought_message
                    }
                }
            }
        }

        # Third (popped last) will be contemplate_loop
        contemplate_tool_call = {
            "tool_call_results": {
                "contemplate_loop": {
                    "tool_name": "contemplate_loop",
                    "arguments": {
                        "question": "Let's think about this carefully."
                    }
                }
            }
        }
        
        mock_messages = [
            ChatMessage(role="assistant", content=json.dumps(exit_tool_call)),
            ChatMessage(role="assistant", content=json.dumps(message_self_tool_call)),
            ChatMessage(role="assistant", content=json.dumps(contemplate_tool_call))
        ]
        
        # Run the contemplation loop with mock messages
        response = await chat_agent.get_response(
            tools={ToolName.MESSAGE_SELF, ToolName.EXIT_LOOP, ToolName.CONTEMPLATE_LOOP},
            mock=True,
            mock_messages=mock_messages
        )
        
        # Check that the final response matches our exit message
        assert response == f"{exit_message}", \
            f"Expected '[CONTEMPLATION_LOOP] {exit_message}', got '{response}'"
        
        logger.info("✓ test_tool_loop passed")

    async def test_arg_validation():
        # Test 1: Invalid tool name
        args, error = validate_tool_args(
            "not_a_real_tool",
            {},
            {ToolName.CONTEMPLATE_LOOP}
        )
        assert args is None, "Expected args to be None for invalid tool"
        assert error is not None and "Unknown tool" in error, \
            f"Expected 'Unknown tool' error message, got: {error}"

        # Test 2: Tool not in available tools
        args, error = validate_tool_args(
            "contemplate_loop",
            {},
            {ToolName.MESSAGE_SELF}  # Only message_self available
        )
        assert args is None, "Expected args to be None for unavailable tool"
        assert error is not None and "not available in current context" in error, \
            f"Expected 'not available in current context' error message, got: {error}"

        # Test 3: Missing required parameters
        args, error = validate_tool_args(
            "contemplate_loop",
            {},  # Missing 'question' parameter
            {ToolName.CONTEMPLATE_LOOP}
        )
        assert args is None, "Expected args to be None for missing parameters"
        assert error is not None and "Missing required parameters" in error, \
            f"Expected 'Missing required parameters' error message, got: {error}"

        # Test 4: Unrecognized arguments
        args, error = validate_tool_args(
            "contemplate_loop",
            {"question": "test", "invalid_arg": "value"},
            {ToolName.CONTEMPLATE_LOOP}
        )
        assert args is None, "Expected args to be None for invalid arguments"
        assert error is not None and "Unrecognized arguments" in error, \
            f"Expected 'Unrecognized arguments' error message, got: {error}"

        # Test 5: Valid case for comparison
        args, error = validate_tool_args(
            "contemplate_loop",
            {"question": "test"},
            {ToolName.CONTEMPLATE_LOOP}
        )
        assert args == {"question": "test"} and error is None, \
            f"Expected valid args and no error, got args={args}, error={error}"
        
        logger.info("✓ test_arg_validation passed")

    async def test_token_budget():
        # Create a chat history with a simple user message
        chat_history = ChatHistory()
        chat_history.add_message("user", "Let's think about this carefully.")
        chat_agent = ChatAgent(chat_history)
        
        # Set up mock messages with token usage that will exceed budget
        exit_tool_call = {
            "tool_call_results": {
                "exit_loop": {
                    "tool_name": "exit_loop",
                    "arguments": {
                        "exit_message": "Token budget exceeded"
                    }
                }
            }
        }

        message_self_tool_call = {
            "tool_call_results": {
                "message_self": {
                    "tool_name": "message_self",
                    "arguments": {
                        "message": "Thinking..."
                    }
                }
            },
            "token_usage": {
                "total_tokens": 15000  # High token usage
            }
        }

        contemplate_tool_call = {
            "tool_call_results": {
                "contemplate_loop": {
                    "tool_name": "contemplate_loop",
                    "arguments": {
                        "question": "Let's think about this carefully."
                    }
                }
            }
        }
        
        mock_messages = [
            ChatMessage(role="assistant", content=json.dumps(exit_tool_call)),
            ChatMessage(role="assistant", content=json.dumps(message_self_tool_call)),
            ChatMessage(role="assistant", content=json.dumps(contemplate_tool_call))
        ]
        
        # Run with a low token budget
        response = await chat_agent.get_response(
            tools={ToolName.MESSAGE_SELF, ToolName.EXIT_LOOP, ToolName.CONTEMPLATE_LOOP},
            token_budget=10000,  # Lower than the mock usage
            mock=True,
            mock_messages=mock_messages
        )
        
        # Verify we get the token budget exceeded message
        assert "Token budget exceeded" in response, \
            f"Expected token budget exceeded message, got: {response}"
        
        logger.info("✓ test_token_budget passed")

    async def run_agent_tool_tests() -> tuple[int, int]:
        """Execute all agent tool tests sequentially.

        Returns:
            Tuple of (passed_tests, failed_tests)
        """
        tests = [
            test_tool_loop,
            test_arg_validation,
            test_token_budget
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