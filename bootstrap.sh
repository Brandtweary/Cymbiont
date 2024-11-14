#!/bin/bash

# Pretty startup banner
echo ""
echo -e "\033[32m╔════════════════════════════════════════╗\033[0m"
echo -e "\033[32m║        Initializing \033[34mCyberOrganism\033[32m      ║\033[0m"
echo -e "\033[32m╚════════════════════════════════════════╝\033[0m"

# Check Python version
PYTHON_VERSION=$(python --version 2>&1 | cut -d' ' -f2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

echo -e "\033[32m>> Runtime: \033[34mPython $PYTHON_VERSION\033[0m"
echo -e "\033[32m>> Environment: Development\033[0m"

# Check Python version compatibility
if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -gt 12 ]; then
    echo -e "\033[31m>> Warning: PyTorch may not be compatible with Python $PYTHON_VERSION\033[0m"
    echo -e "\033[31m>> PyTorch currently supports Python versions up to 3.12\033[0m"
    echo -e "\033[31m>> Please consider using Python 3.12 or earlier\033[0m"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo -e "\033[32m>> Creating virtual environment...\033[0m"
    python -m venv .venv
fi

# Activate venv only if not already in one
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "\033[32m>> Activating virtual environment...\033[0m"
    source .venv/bin/activate
else
    echo -e "\033[32m>> Using active virtual environment: \033[34m$VIRTUAL_ENV\033[0m"
fi

# Check internet connectivity
if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
    echo -e "\033[32m>> Network Status: \033[32mOnline\033[0m"
else
    echo -e "\033[32m>> Network Status: \033[31mOffline\033[0m"
    echo -e "\033[31m>> Warning: Internet connection required \033[0m"
fi

# Load environment variables from .env
if [ -f .env ]; then
    set -o allexport
    source .env
    set +o allexport
    echo -e "\033[32m>> Environment file: \033[32mLoaded\033[0m"
fi

# Check for API keys
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "\033[31m>> Warning: OPENAI_API_KEY not set\033[0m"
else
    echo -e "\033[32m>> OpenAI API Key: Configured\033[0m"
fi

# Install dependencies
if [ ! -f "requirements.txt" ]; then
    echo -e "\033[31m>> Error: requirements.txt not found\033[0m"
    exit 1
fi

echo -e "\033[32m>> Installing Python dependencies...\033[0m"
if pip install -r requirements.txt --no-deps --upgrade-strategy only-if-needed; then
    echo -e "\033[32m>> Dependencies installed successfully\033[0m"
else
    echo -e "\033[31m>> Error: Failed to install dependencies\033[0m"
    exit 1
fi

# Function to detect OS
get_os() {
    case "$(uname -s)" in
        Linux*)     echo 'Linux';;
        Darwin*)    echo 'Mac';;
        MINGW*|MSYS*|CYGWIN*) echo 'Windows';;
        *)         echo 'Unknown';;
    esac
}

# Track if we explicitly skipped PyTorch installation
PYTORCH_SKIPPED=false

# Check if PyTorch is already installed
if python3 -c "import torch" &> /dev/null; then
    echo -e "\033[32m>> PyTorch is already installed\033[0m"
else
    # Execute appropriate install command
    if [ "$CHOICE" = "SKIP" ]; then
        echo -e "\033[33m>> Skipping PyTorch installation\033[0m"
        PYTORCH_SKIPPED=true
    else
        echo -e "\033[32m>> Installing PyTorch for: \033[34m$CHOICE\033[0m"
        
        case $OS in
            "Linux")
                case $CHOICE in
                    "CUDA 11.8")
                        pip3 install torch --index-url https://download.pytorch.org/whl/cu118
                        ;;
                    "CUDA 12.1")
                        pip3 install torch --index-url https://download.pytorch.org/whl/cu121
                        ;;
                    "CUDA 12.4")
                        pip3 install torch
                        ;;
                    "ROCm 6.2")
                        pip3 install torch --index-url https://download.pytorch.org/whl/rocm6.2
                        ;;
                    "CPU-only")
                        pip3 install torch --index-url https://download.pytorch.org/whl/cpu
                        ;;
                esac
                ;;
            "Windows")
                case $CHOICE in
                    "CUDA 11.8")
                        pip3 install torch --index-url https://download.pytorch.org/whl/cu118
                        ;;
                    "CUDA 12.1")
                        pip3 install torch --index-url https://download.pytorch.org/whl/cu121
                        ;;
                    "CUDA 12.4")
                        pip3 install torch --index-url https://download.pytorch.org/whl/cu124
                        ;;
                    "CPU-only")
                        pip3 install torch
                        ;;
                esac
                ;;
            "Mac")
                pip3 install torch torchvision torchaudio
                ;;
        esac
    fi
fi

# Check CUDA availability if PyTorch wasn't explicitly skipped
if ! $PYTORCH_SKIPPED; then
    if python3 -c "import torch" &> /dev/null; then
        echo -e "\033[32m>> Checking CUDA availability...\033[0m"
        python3 -c '
import torch
cuda_available = torch.cuda.is_available()
device_count = torch.cuda.device_count() if cuda_available else 0
print("\033[32m>> CUDA Status:\033[0m", "\033[32mAvailable\033[0m" if cuda_available else "\033[31mNot Available\033[0m")
if cuda_available:
    print("\033[32m>> CUDA Devices:\033[0m", "\033[32m" + str(device_count) + "\033[0m")
    print("\033[32m>> CUDA Version:\033[0m", "\033[34m" + torch.version.cuda + "\033[0m")
'
    else
        echo -e "\033[31m>> PyTorch import failed, skipping CUDA check\033[0m"
    fi
fi