import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import logging
import sys
import signal
import asyncio
from pathlib import Path
import pynvml
from typing import Dict, Any

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Global model storage (mimicking the main script)
llama_models = {}

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out after 30 seconds")

def load_local_model(model_name: str) -> Dict[str, Any]:
    """Load a local transformers model and tokenizer."""
    try:
        model_path = Path(__file__).parent.parent / "local_models" / model_name.split("/")[-1]
        if not model_path.exists():
            raise RuntimeError(f"Model not found at {model_path}")
            
        logger.info(f"Loading model from {model_path}")
        
        # Load tokenizer
        tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True)
        
        # Load model with 4-bit quantization
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16
        )
        
        # Initialize pynvml once
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        total_gb = int(pynvml.nvmlDeviceGetMemoryInfo(handle).total) / (1024**3)
        
        # Log GPU memory before loading
        try:
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            free_gb = int(info.free) / (1024**3)
            logger.info(f"GPU Memory before loading - Free: {free_gb:.2f}GB / Total: {total_gb:.2f}GB")
        except Exception as e:
            logger.error(f"Failed to get GPU memory info: {e}")
        
        model = AutoModelForCausalLM.from_pretrained(
            str(model_path),
            device_map="auto",
            local_files_only=True,
            torch_dtype=torch.bfloat16,
            quantization_config=quantization_config
        )
        
        # Detailed device map logging
        logger.info("=== Detailed Device Map ===")
        for key, device in model.hf_device_map.items():
            logger.info(f"{key}: {device}")
        logger.info("=== End Device Map ===")
        
        # Log GPU memory after loading
        try:
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            free_gb = int(info.free) / (1024**3)
            logger.info(f"GPU Memory after loading - Free: {free_gb:.2f}GB / Total: {total_gb:.2f}GB")
        except Exception as e:
            logger.error(f"Failed to get GPU memory info: {e}")
        
        logger.info(f"First layer device: {next(model.parameters()).device}")
        
        return {"model": model, "tokenizer": tokenizer}
        
    except Exception as e:
        logger.error(f"Failed to load model {model_name}: {str(e)}", exc_info=True)
        return {"model": None, "tokenizer": None}

def format_llama_input(tokenizer, messages, system_message=None):
    """Format input for LLaMA models using the chat template."""
    if system_message:
        messages = [{"role": "system", "content": system_message}] + messages
        
    input_text = tokenizer.apply_chat_template(messages, tokenize=False)
    assert isinstance(input_text, str), f"Expected string from chat template but got {type(input_text)}"
    
    input_ids = tokenizer(input_text, return_tensors="pt").input_ids
    input_ids = input_ids.to("cuda")
    
    return input_ids

async def generate_completion(model_name: str, messages: list, system_message: str = ''):
    """Generate a completion using a local LLaMA model."""
    try:
        # Get or load model
        if model_name not in llama_models:
            model_info = load_local_model(model_name)
            if not model_info["model"] or not model_info["tokenizer"]:
                raise RuntimeError(f"Failed to load {model_name}")
            llama_models[model_name] = model_info
            
        model = llama_models[model_name]["model"]
        tokenizer = llama_models[model_name]["tokenizer"]
        
        # Format input
        formatted_input = format_llama_input(
            tokenizer=tokenizer,
            messages=messages,
            system_message=system_message
        )
        
        logger.debug("Running model inference...")
        
        # Set 30 second timeout
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)
        
        try:
            with torch.inference_mode():
                # Check that input tensor is on same device as model
                model_device = next(model.parameters()).device
                logger.info(f"Model device map: {model.hf_device_map}")
                logger.info(f"Model first layer device: {model_device}")
                logger.info(f"Input tensor device: {formatted_input.device}")
                assert formatted_input.device == model_device, f"Input tensor on {formatted_input.device} but model on {model_device}"
                
                outputs = model.generate(
                    formatted_input,
                    max_new_tokens=100,  # Hardcoded for testing
                    temperature=0.7,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                )
                
            # Clear timeout after successful generation
            signal.alarm(0)
            
        except TimeoutError:
            raise TimeoutError("Model inference timed out after 30 seconds")
            
        finally:
            # Always clear the alarm
            signal.alarm(0)
            
        # Decode only the new tokens
        response = tokenizer.decode(
            outputs[0][len(formatted_input[0]):],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error in generate_completion: {str(e)}", exc_info=True)
        raise

async def main():
    try:
        model_name = "meta-llama/Llama-3.3-70B-Instruct"
        system_message = "You are a helpful AI assistant."
        messages = [{"role": "user", "content": "Please suggest what I should cook for dinner tonight."}]
        
        response = await generate_completion(
            model_name=model_name,
            messages=messages,
            system_message=system_message
        )
        
        logger.info("\nGenerated response:")
        logger.info(response)
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
