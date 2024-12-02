import json
from typing import Set
from agents.chat_agent import get_response, ChatHistory, validate_tool_args
from constants import ToolName
from custom_dataclasses import ChatMessage
from shared_resources import logger

async def test_tool_loop():
    # Create a chat history with a simple user message
    chat_history = ChatHistory()
    chat_history.add_message("user", "Let's think about this carefully.")
    
    # Set up mock messages that will be returned by execute_call
    # Note: Messages are in reverse order since they'll be popped from the end
    
    # First message will be for exit_loop
    exit_message = "After careful consideration, here's what I think..."
    exit_tool_call = {
        "tool_call_results": {
            "1": {
                "tool_name": "exit_loop",
                "arguments": {
                    "exit_message": exit_message
                }
            }
        }
    }
    
    # Second message will be for contemplate
    contemplate_tool_call = {
        "tool_call_results": {
            "1": {
                "tool_name": "contemplate",
                "arguments": {
                    "question": "What should we consider here?"
                }
            }
        }
    }
    
    # Create mock messages in reverse order (they'll be popped from the end)
    mock_messages = [
        ChatMessage(role="assistant", content=json.dumps(exit_tool_call)),
        ChatMessage(role="assistant", content=json.dumps(contemplate_tool_call))
    ]
    
    # Call get_response with mock data
    response = await get_response(
        chat_history=chat_history,
        tools={ToolName.CONTEMPLATE_LOOP},  # Only need contemplate tool
        mock=True,
        mock_messages=mock_messages
    )
    
    # Verify the response matches our exit message
    assert response == exit_message, f"Expected '{exit_message}', but got '{response}'"

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
        "contemplate",
        {},
        {ToolName.MESSAGE_SELF}  # Only message_self available
    )
    assert args is None
    assert error is not None and "not in the available tools list" in error

    # Test 3: Missing required parameters
    args, error = validate_tool_args(
        "contemplate",
        {},  # Missing 'question' parameter
        {ToolName.CONTEMPLATE_LOOP}
    )
    assert args is None
    assert error is not None and "Missing required parameters" in error

    # Test 4: Unrecognized arguments
    args, error = validate_tool_args(
        "contemplate",
        {"question": "test", "invalid_arg": "value"},
        {ToolName.CONTEMPLATE_LOOP}
    )
    assert args is None
    assert error is not None and "Unrecognized arguments" in error

    # Test 5: Valid case for comparison
    args, error = validate_tool_args(
        "contemplate",
        {"question": "test"},
        {ToolName.CONTEMPLATE_LOOP}
    )
    assert args == {"question": "test"} and error is None

async def test_token_budget():
    # Create a chat history with a simple user message
    chat_history = ChatHistory()
    chat_history.add_message("user", "Let's think about this carefully.")
    
    # Create a message that will exceed the token budget
    token_budget = 2000
    long_message = "- " * token_budget  # Each dash and space is a token
    
    # Set up mock messages that will be returned by execute_call
    # First message will be message_self with the long message
    message_self_call = {
        "tool_call_results": {
            "1": {
                "tool_name": "message_self",
                "arguments": {
                    "message": long_message
                }
            }
        }
    }
    
    # Second message will be for contemplate
    contemplate_tool_call = {
        "tool_call_results": {
            "1": {
                "tool_name": "contemplate",
                "arguments": {
                    "question": "What should we consider here?"
                }
            }
        }
    }
    
    # Create mock messages in reverse order (they'll be popped from the end)
    mock_messages = [
        ChatMessage(role="assistant", content=json.dumps(message_self_call)),
        ChatMessage(role="assistant", content=json.dumps(contemplate_tool_call))
    ]
    
    # Call get_response with mock data and token budget
    response = await get_response(
        chat_history=chat_history,
        tools={ToolName.CONTEMPLATE_LOOP},
        token_budget=token_budget,
        mock=True,
        mock_messages=mock_messages
    )
    
    # Verify we get the token budget exceeded message
    assert response == "Sorry, my token budget has been exceeded during a tool call."

async def run_agent_tool_tests() -> tuple[int, int]:
    """Execute all agent tool tests sequentially.
    Returns: Tuple of (passed_tests, failed_tests)"""
    tests = [
        test_tool_loop,
        test_arg_validation,
        test_token_budget
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        logger.info(f"Running {test.__name__}...")
        try:
            await test()
            logger.info(f"✓ {test.__name__} passed\n")
            passed += 1
        except Exception as e:
            logger.error(f"✗ {test.__name__} failed: {str(e)}\n")
            failed += 1
    
    return passed, failed