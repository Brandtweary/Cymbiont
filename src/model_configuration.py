from enum import Enum
import os
from typing import Optional
from shared_resources import config, logger
from constants import LLM, MODEL_PROVIDERS


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
        if model_value not in MODEL_PROVIDERS:
            raise ValueError(f"Invalid model {model_value} specified in config")
            
        provider = MODEL_PROVIDERS[model_value]
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

# Export the configured models
CHAT_AGENT_MODEL = model_config["CHAT_AGENT_MODEL"]
TAG_EXTRACTION_MODEL = model_config["TAG_EXTRACTION_MODEL"]
PROGRESSIVE_SUMMARY_MODEL = model_config["PROGRESSIVE_SUMMARY_MODEL"]
REVISION_MODEL = model_config["REVISION_MODEL"]