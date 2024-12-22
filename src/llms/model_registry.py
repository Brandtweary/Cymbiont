"""Manages model registration and access."""
from typing import Dict, Optional, Any, List

class UninitializedModel(str):
    """Special string type for uninitialized models that can be used as a string but warns when accessed."""
    def __new__(cls):
        return super().__new__(cls, "Model registry not initialized")

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
        self._chat_agent_model = UninitializedModel()
        self._tag_extraction_model = UninitializedModel()
        self._progressive_summary_model = UninitializedModel()
        self._revision_model = UninitializedModel()
        self._initialized = False
    
    def __getitem__(self, key: str) -> str:
        """Get a model by its key (e.g. 'chat_agent' or 'CHAT_AGENT_MODEL')."""
        if not self._initialized:
            raise RuntimeError("Model registry not initialized")
            
        # Convert snake_case to UPPER_CASE if needed
        if not key.isupper():
            key = f"{key.upper()}_MODEL"
            
        # Convert to property name
        prop_name = key.lower().replace('_model', '_model')
        if not hasattr(self, prop_name):
            raise KeyError(f"Unknown model key: {key}")
            
        return getattr(self, prop_name)
    
    @property
    def chat_agent_model(self) -> str:
        return self._chat_agent_model
        
    @property
    def tag_extraction_model(self) -> str:
        return self._tag_extraction_model
        
    @property
    def progressive_summary_model(self) -> str:
        return self._progressive_summary_model
        
    @property
    def revision_model(self) -> str:
        return self._revision_model
    
    def initialize(self, model_config: Dict[str, str]) -> None:
        """Initialize the model registry with configuration."""
        missing = [model for model in self.REQUIRED_MODELS if model not in model_config]
        if missing:
            raise ValueError(f"Missing required models in config: {missing}")
            
        self._chat_agent_model = model_config["CHAT_AGENT_MODEL"]
        self._tag_extraction_model = model_config["TAG_EXTRACTION_MODEL"]
        self._progressive_summary_model = model_config["PROGRESSIVE_SUMMARY_MODEL"]
        self._revision_model = model_config["REVISION_MODEL"]
        self._initialized = True

# Global instance
registry = ModelRegistry()
