from typing import Dict, Callable
from .shell_types import CommandArgType, CommandData
from .doc_processing_commands import (
    do_process_documents,
    do_create_data_snapshot,
    do_parse_documents,
    do_revise_document
)
from .test_commands import (
    do_test_api_queue,
    do_test_document_processing,
    do_test_logger,
    do_test_parsing,
    do_test_progressive_summarization,
    do_test_agent_tools,
    do_run_all_tests,
)

def create_commands(
    do_exit: Callable,
    do_help: Callable,
    do_hello_world: Callable,
    do_print_total_tokens: Callable
) -> Dict[str, CommandData]:
    """Create the command metadata mapping.
    
    Args:
        do_exit: Exit command function from shell
        do_help: Help command function from shell
        do_hello_world: Hello world command function from shell
        do_print_total_tokens: Print tokens command function from shell
    
    Returns:
        Dict mapping command names to their CommandData
    """
    return {
        'exit': CommandData(
            callable=do_exit,
            takes_args=False
        ),
        'help': CommandData(
            callable=do_help,
            takes_args=True,
            arg_types=[CommandArgType.COMMAND]
        ),
        'hello_world': CommandData(
            callable=do_hello_world,
            takes_args=False
        ),
        'process_documents': CommandData(
            callable=do_process_documents,
            takes_args=True,
            arg_types=[CommandArgType.ENTRY]
        ),
        'create_data_snapshot': CommandData(
            callable=do_create_data_snapshot,
            takes_args=True,
            arg_types=[CommandArgType.TEXT, CommandArgType.ENTRY]
        ),
        'parse_documents': CommandData(
            callable=do_parse_documents,
            takes_args=True,
            arg_types=[CommandArgType.FILENAME]
        ),
        'revise_document': CommandData(
            callable=do_revise_document,
            takes_args=True,
            arg_types=[CommandArgType.FILENAME, CommandArgType.TEXT]
        ),
        'test_api_queue': CommandData(
            callable=do_test_api_queue,
            takes_args=False,
            needs_shell=True  # Needs shell to update test results
        ),
        'test_document_processing': CommandData(
            callable=do_test_document_processing,
            takes_args=False,
            needs_shell=True  # Needs shell to update test results
        ),
        'test_logger': CommandData(
            callable=do_test_logger,
            takes_args=False,
            needs_shell=True  # Needs shell to update test results
        ),
        'test_parsing': CommandData(
            callable=do_test_parsing,
            takes_args=False,
            needs_shell=True  # Needs shell to update test results
        ),
        'test_progressive_summarization': CommandData(
            callable=do_test_progressive_summarization,
            takes_args=False,
            needs_shell=True  # Needs shell to update test results
        ),
        'test_agent_tools': CommandData(
            callable=do_test_agent_tools,
            takes_args=False,
            needs_shell=True  # Needs shell to update test results
        ),
        'run_all_tests': CommandData(
            callable=do_run_all_tests,
            takes_args=True,
            arg_types=[CommandArgType.FLAG],
            needs_shell=True  # Needs shell to update test results
        ),
        'print_total_tokens': CommandData(
            callable=do_print_total_tokens,
            takes_args=False
        )
    }
