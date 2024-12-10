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
    from agents.chat_history import ChatHistory
    from agents.tool_helpers import validate_tool_args
    from llms.llm_types import ChatMessage, ToolName
    from shared_resources import logger

    async def test_arg_validation():
        # Test 1: Invalid tool name
        args, error = validate_tool_args(
            "not_a_real_tool",
            {},
            {ToolName.EXECUTE_SHELL_COMMAND}
        )
        assert args is None, "Expected args to be None for invalid tool"
        assert error is not None and "Unknown tool" in error, \
            f"Expected 'Unknown tool' error message, got: {error}"

        # Test 2: Tool not in available tools
        args, error = validate_tool_args(
            "execute_shell_command",
            {},
            {ToolName.MESSAGE_SELF}  # Only message_self available
        )
        assert args is None, "Expected args to be None for unavailable tool"
        assert error is not None and "not available in current context" in error, \
            f"Expected 'not available in current context' error message, got: {error}"

        # Test 3: Missing required parameters
        args, error = validate_tool_args(
            "execute_shell_command",
            {},  # Missing 'command' parameter
            {ToolName.EXECUTE_SHELL_COMMAND}
        )
        assert args is None, "Expected args to be None for missing parameters"
        assert error is not None and "Missing required parameters" in error, \
            f"Expected 'Missing required parameters' error message, got: {error}"

        # Test 4: Unrecognized arguments
        args, error = validate_tool_args(
            "execute_shell_command",
            {"command": "help", "invalid_arg": "value"},
            {ToolName.EXECUTE_SHELL_COMMAND}
        )
        assert args is None, "Expected args to be None for invalid arguments"
        assert error is not None and "Unrecognized arguments" in error, \
            f"Expected 'Unrecognized arguments' error message, got: {error}"

        # Test 5: Valid case for comparison
        args, error = validate_tool_args(
            "execute_shell_command",
            {"command": "help", "args": ["hello_world"]},
            {ToolName.EXECUTE_SHELL_COMMAND}
        )
        assert args == {"command": "help", "args": ["hello_world"]} and error is None, \
            f"Expected valid args and no error, got args={args}, error={error}"
        
        logger.info("✓ test_arg_validation passed")

    async def run_agent_tool_tests() -> tuple[int, int]:
        """Execute all agent tool tests sequentially.

        Returns:
            Tuple of (passed_tests, failed_tests)
        """
        tests = [
            test_arg_validation,
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