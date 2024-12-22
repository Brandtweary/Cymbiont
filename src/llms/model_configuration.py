from enum import Enum
import os
from typing import Optional, Dict, Any
from shared_resources import config, logger, PROJECT_ROOT
from .llm_types import LLM
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from pathlib import Path
from .llama_models import load_local_model
from .model_registry import ModelRegistry

# Initialize API clients
openai_client = AsyncOpenAI() if os.getenv("OPENAI_API_KEY") else None
anthropic_client = AsyncAnthropic() if os.getenv("ANTHROPIC_API_KEY") else None

def get_available_providers() -> set:
    """Return a set of available providers based on API keys in environment."""
    providers = set()
    
    if os.getenv("ANTHROPIC_API_KEY"):
        providers.add("anthropic")
    if os.getenv("OPENAI_API_KEY"):
        providers.add("openai")
    if os.path.exists(PROJECT_ROOT / "local_models"):
        providers.add("huggingface_llama_local")
        
    return providers

def get_fallback_model(desired_model: str, available_providers: set, blacklisted_models: Optional[set] = None) -> Optional[str]:
    """Get a fallback model from an available provider.
    
    Args:
        desired_model: The model that needs a fallback
        available_providers: Set of available providers
        blacklisted_models: Optional set of model names (from LLM enum) to exclude from fallback options
    """
    blacklisted_models = blacklisted_models or set()
    
    if "anthropic" in available_providers and LLM.SONNET_3_5.value not in blacklisted_models:
        return LLM.SONNET_3_5.value
    if "openai" in available_providers and LLM.GPT_4O.value not in blacklisted_models:
        return LLM.GPT_4O.value
    if "huggingface_llama_local" in available_providers and LLM.LLAMA_70B.value not in blacklisted_models:
        return LLM.LLAMA_70B.value
    return None

# Rate limits are assuming tier 2 API access for both OpenAI and Anthropic
model_data = {
    LLM.SONNET_3_5.value: {
        "provider": "anthropic",
        "max_output_tokens": 200000,
        "requests_per_minute": 1000,
        "input_tokens_per_minute": 80000,
        "output_tokens_per_minute": 16000
    },
    LLM.HAIKU_3_5.value: {
        "provider": "anthropic",
        "max_output_tokens": 200000,
        "requests_per_minute": 1000,
        "input_tokens_per_minute": 100000,
        "output_tokens_per_minute": 20000
    },
    LLM.GPT_4O.value: {
        "provider": "openai",
        "max_output_tokens": 16384,
        "requests_per_minute": 5000,
        "total_tokens_per_minute": 450000
    },
    LLM.GPT_4O_MINI.value: {
        "provider": "openai",
        "max_output_tokens": 16384,
        "requests_per_minute": 5000,
        "total_tokens_per_minute": 2000000
    },
    LLM.O1_PREVIEW.value: {
        "provider": "openai",
        "max_output_tokens": 16384,
        "requests_per_minute": 5000,
        "total_tokens_per_minute": 450000
    },
    LLM.LLAMA_70B.value: {
        "provider": "huggingface_llama_local",
        "max_output_tokens": 2048,
        "requests_per_minute": 10000,  # arbitrary high value for local models
        "total_tokens_per_minute": 5000000  # arbitrary high value for local models
    }
}

def initialize_model_configuration() -> Optional[Dict[str, str]]:
    """Initialize model configuration based on config file and available API keys."""
    available_providers = get_available_providers()
    
    # Initialize model configurations from config file
    model_configs = {}
    
    # Check that all required models are in config
    for model_key in ModelRegistry.REQUIRED_MODELS:
        if model_key not in config["models"]:
            logger.error(f"Missing required model in config.toml: {model_key}")
            return None
        model_configs[model_key] = config["models"][model_key]

    configured_models = {}
    blacklisted_models = set()
    
    for model_key, model_value in model_configs.items():
        if model_value not in model_data:
            logger.warning(f"Invalid model {model_value} specified in config")
            continue
            
        model_info = model_data[model_value]
        provider = model_info["provider"]
        
        # Handle local models
        if provider == "huggingface_llama_local":
            components = load_local_model(model_value)
            if components["model"] and components["tokenizer"]:
                configured_models[model_key] = model_value  # Store the model name
                continue
            else:
                blacklisted_models.add(model_value)
                fallback = get_fallback_model(model_value, available_providers, blacklisted_models)
                if fallback:
                    logger.warning(f"Local model failed to load for {model_key}, falling back to {fallback}")
                    model_value = fallback
                    model_info = model_data[fallback]
                    provider = model_info["provider"]
                else:
                    logger.warning(f"No fallback available for failed local model {model_value}")
                    continue
        
        # Handle API-based models
        if provider not in available_providers:
            fallback = get_fallback_model(model_value, available_providers, blacklisted_models)
            if fallback:
                logger.warning(f"Provider {provider} not available for {model_key}, falling back to {fallback}")
                model_value = fallback
                model_info = model_data[fallback]
            else:
                continue
            
        configured_models[model_key] = model_value  # Store just the model name
    
    # Check that all required models were configured
    missing_models = [model for model in ModelRegistry.REQUIRED_MODELS if model not in configured_models]
    if missing_models:
        logger.error(f"Failed to configure required models: {missing_models}")
        return None
    
    return configured_models

# Export the configured models and clients
__all__ = ['model_data', 'openai_client', 'anthropic_client', 'initialize_model_configuration']