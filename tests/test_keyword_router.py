if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path
    
    # Get path to cymbiont.py
    project_root = Path(__file__).parent.parent
    cymbiont_path = project_root / 'cymbiont.py'
    
    # Re-run through cymbiont
    os.execv(sys.executable, [sys.executable, str(cymbiont_path), '--test', 'keyword_router'])
else:
    # Normal imports for when the module is imported properly
    from shared_resources import logger, get_shell

    def run_keyword_router_test() -> None:
        """Test the keyword router functionality"""
        try:
            # Initialize router
            router = get_shell().keyword_router
            
            # Test 1: Basic keyword matching
            query = "what arguments can I use?"
            matches = router.route(query)
            assert any(context.name == "shell_command_docs" for context in matches), f"Query '{query}' should match shell_command_docs"
            
            # Test 2: Stemming variations
            query = "tell me about your consciousness"
            matches = router.route(query)
            assert any(context.name == "cymbiont_agent_overview" for context in matches), f"Query '{query}' should match cymbiont_agent_overview"
            
            # Test 3: Phrase matching without keywords
            query = "do you have free will?"  # Should match "free will" phrase
            matches = router.route(query)
            assert any(context.name == "cymbiont_agent_overview" for context in matches), f"Query '{query}' should match cymbiont_agent_overview via phrase"
            
            # Test 4: No matches
            query = "what's the weather like?"
            matches = router.route(query)
            assert len(matches) == 0, f"Query '{query}' should not match any contexts"

        except Exception as e:
            logger.error(f"Keyword router test failed with error: {str(e)}")
            raise