from prompt_toolkit.completion import Completer, Completion, WordCompleter
from typing import Dict, List
from pathlib import Path
import os

from utils import get_paths
from shared_resources import DATA_DIR
from .shell_types import CommandArgType, CommandData


class CommandCompleter(Completer):
    def __init__(self, command_metadata: Dict[str, CommandData]) -> None:
        """Initialize the command completer.
        
        Args:
            command_metadata: Dictionary mapping command names to their CommandData
        """
        self.commands = command_metadata
        self.paths = get_paths(DATA_DIR)
        
        # Create a word completer for command arguments
        self.arg_completions: Dict[str, WordCompleter] = {
            'help': WordCompleter(list(command_metadata.keys()), ignore_case=True),
        }

    def _get_filepaths_completions(self, word_before_cursor: str) -> List[Completion]:
        """Get completions for filepaths in input_documents directory"""
        completions = []
        docs_dir = self.paths.docs_dir
        
        try:
            # Get all files and folders in input_documents
            items = []
            for root, dirs, files in os.walk(docs_dir):
                rel_root = os.path.relpath(root, docs_dir)
                if rel_root == '.':
                    items.extend(dirs + files)
                else:
                    items.extend([os.path.join(rel_root, d) for d in dirs])
                    items.extend([os.path.join(rel_root, f) for f in files])
            
            # Filter by .md and .txt files and directories
            items = [i for i in items if os.path.isdir(os.path.join(docs_dir, i)) or 
                    i.endswith(('.md', '.txt'))]
            
            # Sort items by how well they match the word_before_cursor
            word_lower = word_before_cursor.lower()
            def sort_key(item):
                item_lower = item.lower()
                # Exact matches first, then by number of matching characters
                if item_lower == word_lower:
                    return (0, 0)
                if item_lower.startswith(word_lower):
                    return (1, len(item))
                return (2, len(item))
            
            items.sort(key=sort_key)
            
            # Create completions for sorted items
            for item in items[:50]:  # Limit to 50 items to avoid overwhelming display
                completions.append(Completion(item, start_position=-len(word_before_cursor)))
                    
        except Exception as e:
            print(f"Error getting completions: {e}")
            
        return completions

    def _get_file_completions(self, word_before_cursor: str) -> List[Completion]:
        """Get completions for single files in input_documents directory"""
        completions = []
        docs_dir = self.paths.docs_dir
        
        try:
            # Get all files in input_documents (recursively)
            files = []
            for root, _, filenames in os.walk(docs_dir):
                rel_root = os.path.relpath(root, docs_dir)
                if rel_root == '.':
                    files.extend(filenames)
                else:
                    files.extend([os.path.join(rel_root, f) for f in filenames])
            
            # Filter by .md and .txt files
            files = [f for f in files if f.endswith(('.md', '.txt'))]
            
            # Sort files by how well they match the word_before_cursor
            word_lower = word_before_cursor.lower()
            def sort_key(file):
                file_lower = file.lower()
                # Exact matches first, then by number of matching characters
                if file_lower == word_lower:
                    return (0, 0)
                if file_lower.startswith(word_lower):
                    return (1, len(file))
                return (2, len(file))
            
            files.sort(key=sort_key)
            
            # Create completions for sorted files
            for file in files[:50]:  # Limit to 50 files to avoid overwhelming display
                completions.append(Completion(file, start_position=-len(word_before_cursor)))
                    
        except Exception as e:
            print(f"Error getting completions: {e}")
            
        return completions

    def get_completions(self, document, complete_event):
        """Get completions for the current input.
        
        This completer works in two modes:
        1. Command completion: When no command is typed or an incomplete command is typed
        2. Argument completion: When a valid command is typed and we're completing its arguments
        
        The completer will stop providing completions as soon as it detects any invalid command
        in the input. This is because non-commands are meant to be passed to the LLM agent.
        For example:
            'help' -> completes to available commands
            'help with' -> stops completing after 'with' since it's not a valid command
        """
        text_before_cursor: str = document.text_before_cursor
        words: list[str] = text_before_cursor.split()
        
        # If no words yet, show all commands
        if not words:
            for command in self.commands:
                yield Completion(command, start_position=0)
            return
        
        # Get first word (command) and check if it's valid for arg completion
        first_word = words[0].lower()
        if first_word in self.commands:
            # Try argument completion first
            cmd_data = self.commands[first_word]
            
            if cmd_data.arg_types:  # Only try arg completion if command has arg types defined
                # Get current argument index (subtract 1 for command itself)
                # If we're at a space, we're starting the next argument
                current_arg_idx = len(words) - 1
                if text_before_cursor.endswith(' '):
                    current_arg_idx = len(words)
                current_arg_idx -= 1  # Subtract 1 for the command itself
                
                # If we haven't exceeded the number of expected arguments
                if current_arg_idx < len(cmd_data.arg_types):
                    # Get completions based on the current argument type
                    if not text_before_cursor.endswith(' '):
                        word_before_cursor = words[-1]
                        arg_type = cmd_data.arg_types[current_arg_idx]
                        
                        if arg_type == CommandArgType.FILENAME:
                            yield from self._get_file_completions(word_before_cursor)
                            return
                        elif arg_type == CommandArgType.ENTRY:
                            yield from self._get_file_completions(word_before_cursor)
                            return
                        elif arg_type == CommandArgType.COMMAND:
                            # Complete with available commands
                            for command in self.commands:
                                if command.startswith(word_before_cursor.lower()):
                                    yield Completion(command, start_position=-len(word_before_cursor))
                            return
                        # text and flag types have no completions
            elif first_word in self.arg_completions:  # Fall back to basic WordCompleter
                yield from self.arg_completions[first_word].get_completions(document, complete_event)
                return
                
        # If we get here, try command completion
        # Check if all complete words are valid commands
        word_count = len(words) if text_before_cursor.endswith(' ') else len(words) - 1
        for i in range(word_count):
            if words[i].lower() not in self.commands:
                return  # Stop completion if any invalid command is found
            
        # If we're still typing a word (no space after it)
        if not text_before_cursor.endswith(' '):
            word_before_cursor = words[-1]
            # If this is the first word, complete with commands
            if len(words) == 1:
                for command in self.commands:
                    if command.startswith(word_before_cursor.lower()):
                        yield Completion(command, start_position=-len(word_before_cursor))
                return
