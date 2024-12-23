"""Manages model registration and access."""
from typing import Dict, List
from shared_resources import logger


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
        self._models: Dict[str, str] = {}
        self._initialized = False
    
    @property
    def chat_agent_model(self) -> str:
        if not self._initialized:
            raise RuntimeError("Model registry not initialized")
        return self._models["CHAT_AGENT_MODEL"]
    
    @property
    def tag_extraction_model(self) -> str:
        if not self._initialized:
            raise RuntimeError("Model registry not initialized")
        return self._models["TAG_EXTRACTION_MODEL"]
    
    @property
    def progressive_summary_model(self) -> str:
        if not self._initialized:
            raise RuntimeError("Model registry not initialized")
        return self._models["PROGRESSIVE_SUMMARY_MODEL"]
    
    @property
    def revision_model(self) -> str:
        if not self._initialized:
            raise RuntimeError("Model registry not initialized")
        return self._models["REVISION_MODEL"]
    
    def initialize(self, model_config: Dict[str, str]) -> None:
        """Initialize the model registry with configuration."""
        missing = [model for model in self.REQUIRED_MODELS if model not in model_config]
        if missing:
            raise ValueError(f"Missing required models in config: {missing}")
                    
        self._models = model_config.copy()  # Make a copy to avoid external mutations
        self._initialized = True
        
# Global instance
registry = ModelRegistry()
