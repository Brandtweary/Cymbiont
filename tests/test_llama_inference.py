import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import logging
import sys
from pathlib import Path
import pynvml

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def log_gpu_memory():
    """Log current GPU memory usage."""
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        used_gb = int(info.used) / (1024**3)
        total_gb = int(info.total) / (1024**3)
        logger.info(f"GPU Memory: {used_gb:.2f}GB / {total_gb:.2f}GB")
    except Exception as e:
        logger.error(f"Failed to get GPU memory info: {e}")

def main():
    try:
        # Initialize
        model_name = "meta-llama/Llama-3.3-70B-Instruct"
        model_path = Path(__file__).parent.parent / "local_models" / model_name.split("/")[-1]
        
        if not model_path.exists():
            raise RuntimeError(f"Model not found at {model_path}")
            
        logger.info("Loading model and tokenizer...")
        log_gpu_memory()
        
        # Load tokenizer first
        tokenizer = AutoTokenizer.from_pretrained(
            str(model_path),
            local_files_only=True
        )
        logger.info("Tokenizer loaded")
        
        # Load model with 4-bit quantization
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16
        )
        
        model = AutoModelForCausalLM.from_pretrained(
            str(model_path),
            device_map="auto",
            local_files_only=True,
            quantization_config=quantization_config
        )
        logger.info("Model loaded")
        log_gpu_memory()
        
        # Prepare input
        input_text = "What are we having for dinner?"
        logger.info(f"Input text: {input_text}")
        
        input_ids = tokenizer(input_text, return_tensors="pt").input_ids
        if torch.cuda.is_available():
            input_ids = input_ids.to("cuda")
        logger.info(f"Input shape: {input_ids.shape}")
        
        # Generate
        logger.info("Starting inference...")
        with torch.inference_mode():
            output = model.generate(
                input_ids,
                max_new_tokens=10,
                temperature=0.7,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id
            )
        logger.info("Inference complete")
        log_gpu_memory()
        
        # Decode output
        result = tokenizer.decode(output[0], skip_special_tokens=True)
        logger.info(f"Output: {result}")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            log_gpu_memory()

if __name__ == "__main__":
    main()