"""Manages model registration and access."""
from typing import Dict, Optional, Any, List
import logging
import traceback

logger = logging.getLogger(__name__)

class ModelRegistry:
    """Central registry for model configuration and access."""
    
    # List of required model configuration keys
    REQUIRED_MODELS: List[str] = [
        "CHAT_AGENT_MODEL",
        "TAG_EXTRACTION_MODEL",
        "PROGRESSIVE_SUMMARY_MODEL",
        "REVISION_MODEL"
    ]
    
    def __init__(self):
        self._chat_agent_model = "Model registry not initialized"
        self._tag_extraction_model = "Model registry not initialized"
        self._progressive_summary_model = "Model registry not initialized"
        self._revision_model = "Model registry not initialized"
        self._initialized = False
    
    def __getitem__(self, key: str) -> str:
        """Get a model by its key (e.g. 'chat_agent' or 'CHAT_AGENT_MODEL')."""
        try:
            if not self._initialized:
                raise RuntimeError("Model registry not initialized")
                
            # Convert snake_case to UPPER_CASE if needed
            if not key.isupper():
                key = f"{key.upper()}_MODEL"
                
            # Convert UPPER_CASE_MODEL to snake_case_model
            prop_name = f"_{key.lower()}"
            if not hasattr(self, prop_name):
                raise KeyError(f"Unknown model key: {key}")
                
            value = getattr(self, prop_name)
            if value is None:
                raise ValueError(f"Model {key} is not properly initialized")
                
            return value
        except Exception as e:
            logger.error(f"Error accessing model {key}: {str(e)}\n{traceback.format_exc()}")
            raise
    
    @property
    def chat_agent_model(self) -> str:
        if not self._initialized:
            return "Model registry not initialized"
        return self._chat_agent_model
        
    @property
    def tag_extraction_model(self) -> str:
        if not self._initialized:
            return "Model registry not initialized"
        return self._tag_extraction_model
        
    @property
    def progressive_summary_model(self) -> str:
        if not self._initialized:
            return "Model registry not initialized"
        return self._progressive_summary_model
        
    @property
    def revision_model(self) -> str:
        if not self._initialized:
            return "Model registry not initialized"
        return self._revision_model
    
    def initialize(self, model_config: Dict[str, str]) -> None:
        """Initialize the model registry with configuration."""
        missing = [model for model in self.REQUIRED_MODELS if model not in model_config]
        if missing:
            raise ValueError(f"Missing required models in config: {missing}")
            
        logger.debug(f"Initializing model registry with config: {model_config}")
        logger.debug(f"Before initialization: _initialized={self._initialized}, _chat_agent_model={self._chat_agent_model}")
        
        self._chat_agent_model = model_config["CHAT_AGENT_MODEL"]
        self._tag_extraction_model = model_config["TAG_EXTRACTION_MODEL"]
        self._progressive_summary_model = model_config["PROGRESSIVE_SUMMARY_MODEL"]
        self._revision_model = model_config["REVISION_MODEL"]
        self._initialized = True
        
        logger.debug(f"After initialization: _initialized={self._initialized}, _chat_agent_model={self._chat_agent_model}")

# Global instance
registry = ModelRegistry()
