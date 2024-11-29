#!/bin/bash

# Function to handle PyTorch installation
install_pytorch() {
    # Detect OS
    OS=$(case "$(uname -s)" in
        Linux*)     echo 'Linux';;
        Darwin*)    echo 'Mac';;
        MINGW*|MSYS*|CYGWIN*) echo 'Windows';;
        *)         echo 'Unknown';;
    esac)

    # Check for CUDA on Linux and Windows (informational only)
    if [ "$OS" = "Linux" ] || [ "$OS" = "Windows" ]; then
        if command -v nvidia-smi &> /dev/null; then
            CUDA_VERSION=$(nvidia-smi | grep -oP "CUDA Version: \K[0-9\.]+")
            if [ ! -z "$CUDA_VERSION" ]; then
                echo -e "\033[32m>> CUDA Version: \033[34m$CUDA_VERSION\033[0m"
            else
                echo -e "\033[33m>> Automatic CUDA detection failed\033[0m"
            fi
        else
            echo -e "\033[33m>> Automatic CUDA detection failed\033[0m"
        fi
    fi
    
    echo -e "\033[32m>> Select PyTorch installation type:\033[0m"
    if [ "$OS" = "Linux" ]; then
        options=("CUDA 11.8" "CUDA 12.1" "CUDA 12.4" "ROCm 6.2" "CPU-only" "SKIP")
    elif [ "$OS" = "Windows" ]; then
        options=("CUDA 11.8" "CUDA 12.1" "CUDA 12.4" "CPU-only" "SKIP")
    else  # Mac
        options=("Default" "SKIP")
    fi
    
    select CHOICE in "${options[@]}"; do
        if [[ " ${options[@]} " =~ " ${CHOICE} " ]]; then
            break
        fi
        echo "Invalid option. Please try again."
    done
    
    if [ "$CHOICE" = "SKIP" ]; then
        echo -e "\033[33m>> Skipping PyTorch installation\033[0m"
        return 1
    fi
    
    echo -e "\033[32m>> Installing PyTorch for: \033[34m$CHOICE\033[0m"
    case $OS in
        "Linux")
            case $CHOICE in
                "CUDA 11.8")
                    python3 -m pip install torch --index-url https://download.pytorch.org/whl/cu118
                    ;;
                "CUDA 12.1")
                    python3 -m pip install torch --index-url https://download.pytorch.org/whl/cu121
                    ;;
                "CUDA 12.4")
                    python3 -m pip install torch
                    ;;
                "ROCm 6.2")
                    python3 -m pip install torch --index-url https://download.pytorch.org/whl/rocm6.2
                    ;;
                "CPU-only")
                    python3 -m pip install torch --index-url https://download.pytorch.org/whl/cpu
                    ;;
            esac
            ;;
        "Windows")
            case $CHOICE in
                "CUDA 11.8")
                    python3 -m pip install torch --index-url https://download.pytorch.org/whl/cu118
                    ;;
                "CUDA 12.1")
                    python3 -m pip install torch --index-url https://download.pytorch.org/whl/cu121
                    ;;
                "CUDA 12.4")
                    python3 -m pip install torch --index-url https://download.pytorch.org/whl/cu124
                    ;;
                "CPU-only")
                    python3 -m pip install torch
                    ;;
            esac
            ;;
        "Mac")
            python3 -m pip install torch torchvision torchaudio
            ;;
    esac
    return 0
}

# Pretty startup banner
echo ""
echo -e "\033[32m╔════════════════════════════════════════╗\033[0m"
echo -e "\033[32m║        Initializing \033[34mCyberOrganism\033[32m      ║\033[0m"
echo -e "\033[32m╚════════════════════════════════════════╝\033[0m"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

echo -e "\033[32m>> Runtime: \033[34mPython $PYTHON_VERSION\033[0m"
echo -e "\033[32m>> Environment: Development\033[0m"

# Load config
echo -e "\033[32m>> Loading configuration...\033[0m"
MANAGE_VENV=$(python3 -c '
import tomllib
with open("config.toml", "rb") as f:
    config = tomllib.load(f)
print(config.get("environment", {}).get("manage_venv", True))
')

if [ "$MANAGE_VENV" = "False" ]; then
    PYTHON_PATH=$(which python3)
    echo -e "\033[33m>> Virtual environment management is disabled\033[0m"
    echo -e "\033[33m>> Using system Python at: $PYTHON_PATH\033[0m"
    echo -e "\033[33m>> Dependencies will be installed to this Python environment\033[0m"
    echo -e -n "\033[34m>> Continue with dependency installation? (y/n): \033[0m"
    read answer
    
    case ${answer:0:1} in
        y|Y )
            # Install dependencies
            echo -e "\033[32m>> Installing dependencies...\033[0m"
            if python3 -m pip install -r requirements.txt -q; then
                echo -e "\033[32m>> Dependencies installed successfully\033[0m"
                
                # Only ask about PyTorch if dependencies were installed
                echo -e -n "\033[34m>> Would you like to install PyTorch? (y/n): \033[0m"
                read pytorch_answer
                case ${pytorch_answer:0:1} in
                    y|Y )
                        if install_pytorch; then
                            PYTORCH_INSTALLED=true
                        fi
                        ;;
                    * )
                        echo -e "\033[33m>> Skipping PyTorch installation\033[0m"
                        echo -e "\033[33m>> See: https://pytorch.org/get-started/locally/\033[0m"
                        ;;
                esac
            else
                echo -e "\033[31m>> Error: Failed to install dependencies\033[0m"
                exit 1
            fi
            ;;
        * )
            echo -e "\033[33m>> Skipping all package installation\033[0m"
            ;;
    esac
else
    # Check for virtual environment
    VENV_DIR=".venv"
    if [ ! -d "$VENV_DIR" ]; then
        echo -e "\033[33m>> Virtual environment not found\033[0m"
        echo -e "\033[32m>> Creating new virtual environment...\033[0m"
        python3 -m venv "$VENV_DIR"
        if [ $? -ne 0 ]; then
            echo -e "\033[31m>> Failed to create virtual environment\033[0m"
            exit 1
        fi
        echo -e "\033[32m>> Virtual environment created successfully\033[0m"
    fi

    # Activate virtual environment
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
        if [ $? -ne 0 ]; then
            echo -e "\033[31m>> Failed to activate virtual environment\033[0m"
            exit 1
        fi
        echo -e "\033[32m>> Virtual environment activated\033[0m"
    else
        echo -e "\033[31m>> Virtual environment activation script not found\033[0m"
        exit 1
    fi

    # Install dependencies in the virtual environment
    echo -e "\033[32m>> Installing dependencies in virtual environment...\033[0m"
    if python3 -m pip install -r requirements.txt -q; then
        echo -e "\033[32m>> Dependencies installed successfully\033[0m"
    else
        echo -e "\033[31m>> Error: Failed to install dependencies\033[0m"
        exit 1
    fi

    # Check if PyTorch is already installed
    if python3 -c "import torch" &> /dev/null; then
        echo -e "\033[32m>> PyTorch is already installed\033[0m"
        PYTORCH_INSTALLED=true
    else
        if install_pytorch; then
            PYTORCH_INSTALLED=true
        fi
    fi
fi

# CUDA check (only if PyTorch was installed or was already present)
if [ "$PYTORCH_INSTALLED" = true ]; then
    if python -c "import torch" &> /dev/null; then
    echo -e "\033[32m>> Checking CUDA availability...\033[0m"
        python -c '
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

# After all setup is successful
if [ $? -eq 0 ]; then
    echo -e "\033[32m>> Setup complete.\033[0m"
    echo -e -n "\033[34m>> Would you like to launch Cymbiont? (y/n): \033[0m"
    read answer

    case ${answer:0:1} in
        y|Y )
            echo -e "\033[32m>> Launching Cymbiont...\033[0m"
            python3 cymbiont.py
            ;;
        * )
            echo -e "\033[32m>> Setup completed successfully.\033[0m"
            echo -e "\033[32m>> To run Cymbiont:\033[0m"
            echo -e "\033[34m>>   python cymbiont.py\033[0m"
            echo -e "\033[32m>> See README.md for alternative environment options\033[0m"
            ;;
    esac
fi