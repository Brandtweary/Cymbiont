#!/bin/bash

# Colors for pretty output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Checking CUDA environment...${NC}"
echo -e "${GREEN}CUDA_PATH=$CUDA_PATH${NC}"
echo -e "${GREEN}CUDA_HOME=$CUDA_HOME${NC}"
echo -e "${GREEN}LD_LIBRARY_PATH=$LD_LIBRARY_PATH${NC}"

# Check if torch can see CUDA
python3 -c '
import torch
import os
print("\nPython torch installation:")
print("Torch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
cuda_version = torch.version.cuda if torch.cuda.is_available() else "N/A"
print("Torch CUDA version:", cuda_version)
print("\nCUDA Environment vars:")
print("CUDA_PATH:", os.environ.get("CUDA_PATH", "Not set"))
print("LD_LIBRARY_PATH:", os.environ.get("LD_LIBRARY_PATH", "Not set"))
'