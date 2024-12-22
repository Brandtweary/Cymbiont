from enum import Enum
import os
from typing import Optional, Dict, Any
from shared_resources import config, logger, PROJECT_ROOT
from .llm_types import LLM
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from pathlib import Path

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
        "total_tokens_per_minute": 5000000,  # arbitrary high value for local models
        "model_id": "meta-llama/Llama-3.3-70B-Instruct",
        "model": None,  # Will be populated during initialization
        "tokenizer": None  # Will be populated during initialization
    }
}

def load_local_model(model_id: str) -> Dict[str, Any]:
    """Load a local transformers model and tokenizer from the local_models directory.
    Returns None for both model and tokenizer if loading fails."""
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    import torch
    
    local_models_dir = PROJECT_ROOT / "local_models"
    model_dir = local_models_dir / model_id.split("/")[-1]
    
    if not model_dir.exists():
        logger.warning(f"Model directory not found: {model_dir}")
        return {"model": None, "tokenizer": None}
    
    # Get quantization configuration
    quant_setting = config.get("local_model_quantization", {}).get(model_id, "none")
    quant_config = None
    
    if quant_setting == "4-bit":
        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16
        )
    elif quant_setting == "8-bit":
        quant_config = BitsAndBytesConfig(
            load_in_8bit=True
        )
    
    try:
        model = AutoModelForCausalLM.from_pretrained(
            str(model_dir),
            device_map="auto",
            quantization_config=quant_config,
            local_files_only=True
        )
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        logger.info(f"Successfully loaded local model from {model_dir}")
        return {"model": model, "tokenizer": tokenizer}
    except Exception as e:
        logger.error(f"Failed to load local model {model_id}: {str(e)}")
        return {"model": None, "tokenizer": None}

def initialize_model_configuration():
    """Initialize model configuration based on config file and available API keys."""
    available_providers = get_available_providers()
    
    # Initialize model configurations from config file
    model_configs = {
        "CHAT_AGENT_MODEL": config["models"]["CHAT_AGENT_MODEL"],
        "TAG_EXTRACTION_MODEL": config["models"]["TAG_EXTRACTION_MODEL"],
        "PROGRESSIVE_SUMMARY_MODEL": config["models"]["PROGRESSIVE_SUMMARY_MODEL"],
        "REVISION_MODEL": config["models"]["REVISION_MODEL"]
    }

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
            if "model_id" not in model_info:
                logger.warning(f"No model_id specified for local model {model_value}")
                continue
                
            components = load_local_model(model_info["model_id"])
            if components["model"] and components["tokenizer"]:
                configured_models[model_key] = model_info.copy()
                configured_models[model_key].update(components)
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
            
        configured_models[model_key] = model_value  # Store just the model name, not the entire info dict
    
    if not configured_models:
        logger.warning("No models could be configured. Please check your config.toml")
    
    return configured_models

# Initialize the models
model_config = initialize_model_configuration()

# Export the configured models and clients
CHAT_AGENT_MODEL = model_config["CHAT_AGENT_MODEL"]
TAG_EXTRACTION_MODEL = model_config["TAG_EXTRACTION_MODEL"]
PROGRESSIVE_SUMMARY_MODEL = model_config["PROGRESSIVE_SUMMARY_MODEL"]
REVISION_MODEL = model_config["REVISION_MODEL"]

__all__ = ['model_config', 'openai_client', 'anthropic_client']