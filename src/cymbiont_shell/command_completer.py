from prompt_toolkit.completion import Completer, Completion, WordCompleter
from typing import Callable, Dict


class CommandCompleter(Completer):
    def __init__(self, commands: Dict[str, Callable]) -> None:
        self.commands = commands
        # Create a word completer for command arguments
        self.arg_completions: Dict[str, WordCompleter] = {
            'help': WordCompleter(list(commands.keys()), ignore_case=True),
            # Add more command-specific completers as needed
        }

    def get_completions(self, document, complete_event):
        text_before_cursor: str = document.text_before_cursor
        words: list[str] = text_before_cursor.split()
        
        # If no words yet, show all commands
        if not words:
            for command in self.commands:
                yield Completion(command, start_position=0)
            return
            
        # If we're still typing the first word (no space after it)
        if len(words) == 1 and not text_before_cursor.endswith(' '):
            word_before_cursor: str = words[0]
            for command in self.commands:
                if command.startswith(word_before_cursor.lower()):
                    yield Completion(command, start_position=-len(word_before_cursor))
            return
            
        # Handle argument completion using WordCompleter
        first_word: str = words[0].lower()
        if first_word in self.commands and first_word in self.arg_completions:
            # Get the word completer for this command
            word_completer = self.arg_completions[first_word]
            # Delegate to the word completer
            yield from word_completer.get_completions(document, complete_event)
