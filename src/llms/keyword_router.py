from typing import Dict, List, Optional
from .llm_types import ContextPart, ToolName
from shared_resources import logger, PROJECT_ROOT
from nltk.stem import PorterStemmer
import nltk
import string
from agents.agent import Agent
import os
from dotenv import load_dotenv, set_key

def _initialize_nltk():
    """Initialize NLTK data if not already downloaded"""
    load_dotenv()  # Ensure we have latest env vars
    if os.getenv('NLTK_DOWNLOADED') != 'true':
        try:
            nltk.data.find('corpora/wordnet')
        except LookupError:
            logger.info("Downloading required NLTK data...")
            nltk.download('wordnet')
            nltk.download('averaged_perceptron_tagger')
            logger.info("NLTK data download complete")
        
        # Mark as downloaded in .env
        env_path = PROJECT_ROOT / '.env'
        set_key(str(env_path), 'NLTK_DOWNLOADED', 'true')

# Initialize NLTK on module import
_initialize_nltk()

class KeywordRouter:
    """Routes user input to relevant context parts based on keyword matching"""
    
    def __init__(self, shell_commands: Optional[list[str]] = None) -> None:
        """Initialize the keyword router
        
        Args:
            shell_commands: Optional list of shell command names to add to shell_command_docs keywords
        """
        self.context_parts: Dict[str, ContextPart] = {}
        self.stemmer = PorterStemmer()
            
        # Initialize with default context parts
        self._initialize_default_contexts(shell_commands)
    
    def _clean_word(self, word: str) -> str:
        """Remove punctuation and convert to lowercase"""
        return word.lower().strip(string.punctuation)
    
    def _stem(self, word: str) -> str:
        """Convert a word to its stem form"""
        return self.stemmer.stem(self._clean_word(word))
        
    def _initialize_default_contexts(self, shell_commands: Optional[list[str]] = None):
        """Initialize the default context parts based on system prompt parts"""
        shell_phrases = []
        # Filter out 'help' from exact matching to avoid false positives
        exact_commands = [cmd for cmd in (shell_commands or []) if cmd != 'help']
        
        if shell_commands:
            # Convert snake_case commands to natural phrases for exact matching
            shell_phrases.extend(cmd.replace('_', ' ') for cmd in exact_commands)
            
        default_contexts = [
            ContextPart(
                name="chat_agent_base_prompt",
                keywords=["identity", "purpose"],
                key_phrases=["chat agent", "cybernetic organism"],
                system_prompt_parts=["chat_agent_base_prompt"],
                tools=[]
            ),
            ContextPart(
                name="cymbiont_agent_overview",
                keywords=["consciousness", "autonomy", "sovereignty", "symbiotic"],
                key_phrases=["free will"],
                system_prompt_parts=["cymbiont_agent_overview"],
                tools=[]
            ),
            ContextPart(
                name="biographical",
                keywords=["biography", "introduction", "introduce"],  # word lemmatization is not perfect
                key_phrases=["tell me about yourself"],
                system_prompt_parts=["biographical"],
                tools=[]
            ),
            ContextPart(
                name="shell_command_docs",
                keywords=["command", "argument", "shell", "execute"], 
                key_phrases=["can you run"],
                system_prompt_parts=["shell_command_docs"],
                tools=[ToolName.EXECUTE_SHELL_COMMAND],
                exact_keywords=exact_commands or [],  # Shell commands stay exact
                exact_key_phrases=shell_phrases  # Natural phrases stay exact
            ),
            ContextPart(
                name="response_guidelines",
                keywords=[],
                key_phrases=["response guidelines", "response format"],
                system_prompt_parts=["response_guidelines"],
                tools=[]
            ),
            ContextPart(
                name="taskpad",
                keywords=["taskpad", "task", "objective", "todo"],
                key_phrases=[],
                system_prompt_parts=["taskpad"],
                tools=[ToolName.ADD_TASK, ToolName.ADD_TASK_DEPENDENCY, ToolName.COMPLETE_TASK, ToolName.EDIT_TASK, ToolName.FOLD_TASK, ToolName.UNFOLD_TASK]
            )
        ]
        
        for context in default_contexts:
            self.add_context_part(context)
    
    def add_context_part(self, context_part: ContextPart) -> None:
        """Add a context part to the router"""
        self.context_parts[context_part.name] = context_part
        
    def route(self, query: str) -> List[ContextPart]:
        """Find relevant context parts for a given query based on keyword matching
        
        Args:
            query: The user's query to route
            
        Returns:
            List of ContextPart objects that match the query
        """
        # Clean and stem the full query for phrase matching
        stemmed_query = ' '.join(self._stem(word) for word in query.split())
        query_lower = query.lower()
        
        # Split query into words and stem each for keyword matching
        query_words = {word: self._stem(word) for word in query_lower.split()}
        query_stems = set(query_words.values())
        matches = []
        
        for context in self.context_parts.values():
            context_matched = False
            
            # Check stemmed keywords
            for keyword in context.keywords:
                stemmed_keyword = self._stem(keyword)
                if stemmed_keyword in query_stems:
                    context_matched = True
                    break
            
            # Check stemmed key phrases
            for phrase in context.key_phrases:
                stemmed_phrase = ' '.join(self._stem(word) for word in phrase.split())
                if stemmed_phrase in stemmed_query:
                    context_matched = True
                    break
            
            # Check exact keywords
            for keyword in context.exact_keywords:
                if keyword.lower() in query_lower:
                    context_matched = True
                    break
            
            # Check exact key phrases
            for phrase in context.exact_key_phrases:
                if phrase.lower() in query_lower:
                    context_matched = True
                    break
            
            if context_matched:
                matches.append(context)
        
        return matches
    
    def toggle_context(self, query: str, agent: Agent) -> None:
        """Route a query and update the agent's temporary context.
        
        This method uses the route method to find potential matches based on the query
        and updates the agent's temporary context with the matching context parts.
        Context parts will expire after a default number of turns.
        
        Args:
            query: The user's query to route
            agent: The agent instance whose temporary_context should be updated
        """
        matches = self.route(query)
        agent.update_temporary_context(matches)