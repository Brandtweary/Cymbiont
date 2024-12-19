from enum import Enum
import os
from typing import Optional
from shared_resources import config, logger
from .llm_types import LLM
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

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
    }
}

# Initialize API clients
openai_client = AsyncOpenAI() if os.getenv("OPENAI_API_KEY") else None
anthropic_client = AsyncAnthropic() if os.getenv("ANTHROPIC_API_KEY") else None

def get_available_providers():
    """Return a set of available providers based on API keys in environment."""
    available = set()
    if os.getenv("OPENAI_API_KEY"):
        available.add("openai")
    if os.getenv("ANTHROPIC_API_KEY"):
        available.add("anthropic")
    return available

def get_fallback_model(desired_model: str, available_providers: set) -> Optional[str]:
    """Get a fallback model from an available provider."""
    if "openai" in available_providers:
        return LLM.GPT_4O.value
    elif "anthropic" in available_providers:
        return LLM.SONNET_3_5.value
    return None

def initialize_model_configuration():
    """Initialize model configuration based on config file and available API keys."""
    available_providers = get_available_providers()
    
    if not available_providers:
        raise RuntimeError(
            "No API keys configured. At least one of OPENAI_API_KEY or ANTHROPIC_API_KEY "
            "must be set in the environment."
        )

    # Initialize model configurations from config file
    model_configs = {
        "CHAT_AGENT_MODEL": config["models"]["CHAT_AGENT_MODEL"],
        "TAG_EXTRACTION_MODEL": config["models"]["TAG_EXTRACTION_MODEL"],
        "PROGRESSIVE_SUMMARY_MODEL": config["models"]["PROGRESSIVE_SUMMARY_MODEL"],
        "REVISION_MODEL": config["models"]["REVISION_MODEL"]
    }

    # Validate and potentially adjust each model based on available providers
    for model_key, model_value in model_configs.items():
        if model_value not in model_data:
            raise ValueError(f"Invalid model {model_value} specified in config")
            
        provider = model_data[model_value]["provider"]
        if provider not in available_providers:
            fallback = get_fallback_model(model_value, available_providers)
            if not fallback:
                raise RuntimeError(
                    f"No available provider for {model_value} and no fallback available"
                )
            logger.warning(
                f"{model_key}: Selected model {model_value} requires {provider} "
                f"API key which is not available. Falling back to {fallback}"
            )
            model_configs[model_key] = fallback

    return model_configs

# Initialize the models
model_config = initialize_model_configuration()

# Export the configured models and clients
CHAT_AGENT_MODEL = model_config["CHAT_AGENT_MODEL"]
TAG_EXTRACTION_MODEL = model_config["TAG_EXTRACTION_MODEL"]
PROGRESSIVE_SUMMARY_MODEL = model_config["PROGRESSIVE_SUMMARY_MODEL"]
REVISION_MODEL = model_config["REVISION_MODEL"]

__all__ = ['model_config', 'openai_client', 'anthropic_client']