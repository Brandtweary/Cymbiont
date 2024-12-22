import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import logging
import sys
from pathlib import Path
import pynvml
import signal
import asyncio

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

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out after 60 seconds")

async def main():
    try:
        # Initialize
        model_name = "meta-llama/Llama-3.3-70B-Instruct"
        model_path = Path(__file__).parent.parent / "local_models" / model_name.split("/")[-1]
        
        if not model_path.exists():
            raise RuntimeError(f"Model not found at {model_path}")
            
        logger.info("=== CUDA and Device Information ===")
        logger.info(f"CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            logger.info(f"Current CUDA device: {torch.cuda.current_device()}")
            logger.info(f"Device name: {torch.cuda.get_device_name()}")
        log_gpu_memory()
        
        # Load tokenizer and model
        tokenizer = AutoTokenizer.from_pretrained(
            str(model_path),
            local_files_only=True
        )
        
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16
        )
        
        logger.info("\n=== Loading Model ===")
        model = AutoModelForCausalLM.from_pretrained(
            str(model_path),
            device_map="auto",
            local_files_only=True,
            torch_dtype=torch.bfloat16,
            quantization_config=quantization_config
        )
        logger.info(f"Model device: {next(model.parameters()).device}")
        log_gpu_memory()
        
        # Prepare input
        messages = [{"role": "user", "content": "Please suggest what I should cook for dinner tonight."}]
        input_text = tokenizer.apply_chat_template(messages, tokenize=False)
        
        logger.info("\n=== Tensor Device Tracking ===")
        input_ids = tokenizer(input_text, return_tensors="pt").input_ids
        logger.info(f"Input tensor device before move: {input_ids.device}")
        input_ids = input_ids.to("cuda")
        logger.info(f"Input tensor device after move: {input_ids.device}")
        
        # Generate
        logger.info("\n=== Starting Inference ===")
        log_gpu_memory()
        
        # Set 60 second timeout for inference
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(60)
        
        with torch.inference_mode():
            output = model.generate(
                input_ids,
                max_new_tokens=50,
                temperature=0.7,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id
            )
            logger.info(f"Output tensor device: {output.device}")
            
        # Clear timeout
        signal.alarm(0)
        
        logger.info("\n=== Inference Complete ===")
        logger.info("\nGenerated text:")
        logger.info(tokenizer.decode(output[0][len(input_ids[0]):]))
        
        log_gpu_memory()
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
