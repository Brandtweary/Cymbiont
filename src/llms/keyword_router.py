from typing import Dict, List
from .llm_types import ContextPart, ToolName
from shared_resources import logger
from nltk.stem import PorterStemmer
import nltk
import string
from agents.agent import Agent

class KeywordRouter:
    """Routes user input to relevant context parts based on keyword matching"""
    
    def __init__(self):
        self.context_parts: Dict[str, ContextPart] = {}
        self.stemmer = PorterStemmer()
        
        # Download required NLTK data if not already present
        try:
            nltk.data.find('corpora/wordnet')
        except LookupError:
            nltk.download('wordnet')
            nltk.download('averaged_perceptron_tagger')
        
        # Initialize with default context parts
        self._initialize_default_contexts()
    
    def _clean_word(self, word: str) -> str:
        """Remove punctuation and convert to lowercase"""
        return word.lower().strip(string.punctuation)
    
    def _stem(self, word: str) -> str:
        """Convert a word to its stem form"""
        return self.stemmer.stem(self._clean_word(word))
        
    def _initialize_default_contexts(self):
        """Initialize the default context parts based on system prompt parts"""
        default_contexts = [
            ContextPart(
                name="chat_agent_base_prompt",
                keywords=["identity", "purpose", "autonomous", "cybernetic"],
                key_phrases=["chat agent"],
                system_prompt_parts=["chat_agent_base_prompt"],
                tools=[]
            ),
            ContextPart(
                name="cymbiont_agent_overview",
                keywords=["consciousness", "symbiotic", "autonomy"],
                key_phrases=["free will"],
                system_prompt_parts=["cymbiont_agent_overview"],
                tools=[]
            ),
            ContextPart(
                name="biographical",
                keywords=["biography", "origin", "introduction", "introduce"],
                key_phrases=["tell me about yourself"],
                system_prompt_parts=["biographical"],
                tools=[]
            ),
            ContextPart(
                name="shell_command_docs",
                keywords=["command", "argument", "parameter", "shell", "execute"],
                key_phrases=[],
                system_prompt_parts=["shell_command_docs"],
                tools=[ToolName.EXECUTE_SHELL_COMMAND]
            ),
            ContextPart(
                name="response_guidelines",
                keywords=[],
                key_phrases=["response guidelines", "response format"],
                system_prompt_parts=["response_guidelines"],
                tools=[]
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
        
        # Split query into words and stem each for keyword matching
        query_words = {word: self._stem(word) for word in query.lower().split()}
        query_stems = set(query_words.values())
        matches = []
        
        for context_name, context in self.context_parts.items():
            context_matched = False
            
            # Check keywords
            for keyword in context.keywords:
                stemmed_keyword = self._stem(keyword)
                if stemmed_keyword in query_stems:
                    context_matched = True
            
            # Check phrases
            for phrase in context.key_phrases:
                # Stem each word in the phrase
                stemmed_phrase = ' '.join(self._stem(word) for word in phrase.split())
                if stemmed_phrase in stemmed_query:
                    context_matched = True
            
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