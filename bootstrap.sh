#!/bin/bash

# Detect OS early for system-specific operations
OS=$(case "$(uname -s)" in
    Linux*)     echo 'Linux';;
    Darwin*)    echo 'Mac';;
    MINGW*|MSYS*|CYGWIN*) echo 'Windows';;
    *)         echo 'Unknown';;
esac)

# Function to show progress
progress() {
    local msg="$1"
    local current="$2"
    local total="$3"
    local width=50
    local percentage=$((current * 100 / total))
    local completed=$((width * current / total))
    printf "\r%-100s" " "  # Clear line first
    printf "\r[%-${width}s] %d%% %s" "$(printf '#%.0s' $(seq 1 $completed))" "$percentage" "$msg"
}

# Function to start a new progress bar
start_progress() {
    printf "\r%-100s" " "  # Clear line once at the start
}

# Function to start PyTorch progress bar
start_pytorch_progress() {
    (
        start_progress
        total=100
        current=0
        while [ $current -lt $total ]; do
            progress "Installing PyTorch..." "$current" "$total"
            sleep 1
            ((current++))
        done
        echo  # New line after progress bar
    ) &
    PROGRESS_PID=$!
}

# Function to handle PyTorch installation
install_pytorch() {
    echo "Installing PyTorch..."
    
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
    
    # Do the installation quietly
    RESULT=0
    case $OS in
        "Linux")
            case $CHOICE in
                "CUDA 11.8")
                    start_pytorch_progress
                    python3 -m pip install torch -q --index-url https://download.pytorch.org/whl/cu118 || RESULT=1
                    ;;
                "CUDA 12.1")
                    start_pytorch_progress
                    python3 -m pip install torch -q --index-url https://download.pytorch.org/whl/cu121 || RESULT=1
                    ;;
                "CUDA 12.4")
                    start_pytorch_progress
                    python3 -m pip install torch -q || RESULT=1
                    ;;
                "ROCm 6.2")
                    start_pytorch_progress
                    python3 -m pip install torch -q --index-url https://download.pytorch.org/whl/rocm6.2 || RESULT=1
                    ;;
                "CPU-only")
                    start_pytorch_progress
                    python3 -m pip install torch -q --index-url https://download.pytorch.org/whl/cpu || RESULT=1
                    ;;
            esac
            ;;
        "Windows")
            case $CHOICE in
                "CUDA 11.8")
                    start_pytorch_progress
                    python3 -m pip install torch -q --index-url https://download.pytorch.org/whl/cu118 || RESULT=1
                    ;;
                "CUDA 12.1")
                    start_pytorch_progress
                    python3 -m pip install torch -q --index-url https://download.pytorch.org/whl/cu121 || RESULT=1
                    ;;
                "CUDA 12.4")
                    start_pytorch_progress
                    python3 -m pip install torch -q --index-url https://download.pytorch.org/whl/cu124 || RESULT=1
                    ;;
                "CPU-only")
                    start_pytorch_progress
                    python3 -m pip install torch -q || RESULT=1
                    ;;
            esac
            ;;
        "Mac")
            start_pytorch_progress
            python3 -m pip install torch torchvision torchaudio -q || RESULT=1
            ;;
    esac
    
    # Kill progress bar and check result
    kill $PROGRESS_PID 2>/dev/null
    wait $PROGRESS_PID 2>/dev/null
    if [ $RESULT -eq 0 ]; then
        progress "Installing PyTorch..." "100" "100"
        echo -e "\n\033[32m>> PyTorch installed successfully\033[0m"
        return 0
    else
        echo -e "\n\033[31m>> Error: Failed to install PyTorch\033[0m"
        return 1
    fi
}

# Pretty startup banner
echo ""
echo -e "\033[32m╔════════════════════════════════════════╗\033[0m"
echo -e "\033[32m║          Initializing \033[34mCymbiont\033[32m         ║\033[0m"
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
            # Upgrade pip first to avoid warnings
            echo -e "\033[32m>> Upgrading pip...\033[0m"
            python3 -m pip install --upgrade pip -q || {
                echo -e "\033[31m>> Warning: Failed to upgrade pip\033[0m"
                # Continue anyway since this is not critical
            }
            
            # Install dependencies
            echo -e "\033[32m>> Installing dependencies...\033[0m"
            
            # Count total packages
            total_packages=$(grep -v '^\s*#' requirements.txt | grep -v '^\s*$' | wc -l)
            current_package=0
            
            # Install packages one by one to track progress
            start_progress
            while IFS= read -r package || [ -n "$package" ]; do
                # Skip comments and empty lines
                [[ $package =~ ^[[:space:]]*# ]] && continue
                [[ -z "${package// }" ]] && continue
                
                ((current_package++))
                progress "Installing: $package" "$current_package" "$total_packages"
                
                if ! python3 -m pip install "$package" -q; then
                    echo -e "\n\033[31m>> Error: Failed to install $package\033[0m"
                    exit 1
                fi
            done < requirements.txt
            echo  # New line after progress bar
            echo -e "\033[32m>> Dependencies installed successfully\033[0m"
            
            # Check if PyTorch is already installed
            if python3 -c "import torch" &> /dev/null; then
                echo -e "\033[32m>> PyTorch is already installed\033[0m"
            else
                # Only ask about PyTorch if dependencies were installed and PyTorch is not already present
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

    # Upgrade pip first to avoid warnings
    echo -e "\033[32m>> Upgrading pip...\033[0m"
    python3 -m pip install --upgrade pip -q || {
        echo -e "\033[31m>> Warning: Failed to upgrade pip\033[0m"
        # Continue anyway since this is not critical
    }

    # Install dependencies in the virtual environment
    echo -e "\033[32m>> Installing dependencies in virtual environment...\033[0m"
    
    # Count total packages
    total_packages=$(grep -v '^\s*#' requirements.txt | grep -v '^\s*$' | wc -l)
    current_package=0
    
    # Install packages one by one to track progress
    start_progress
    while IFS= read -r package || [ -n "$package" ]; do
        # Skip comments and empty lines
        [[ $package =~ ^[[:space:]]*# ]] && continue
        [[ -z "${package// }" ]] && continue
        
        ((current_package++))
        progress "Installing: $package" "$current_package" "$total_packages"
        
        if ! python3 -m pip install "$package" -q; then
            echo -e "\n\033[31m>> Error: Failed to install $package\033[0m"
            exit 1
        fi
    done < requirements.txt
    echo  # New line after progress bar
    echo -e "\033[32m>> Dependencies installed successfully\033[0m"

    # Check if PyTorch is already installed
    if python3 -c "import torch" &> /dev/null; then
        echo -e "\033[32m>> PyTorch is already installed\033[0m"
    else
        # Only ask about PyTorch if dependencies were installed and PyTorch is not already present
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
    fi
fi

# Setup restricted user for enhanced security
echo -e "\033[34m>> Would you like to set up a restricted user for enhanced shell security? (y/n): \033[0m"
read setup_restricted

if [[ ${setup_restricted:0:1} =~ [yY] ]]; then
    if [ "$OS" = "Windows" ]; then
        echo -e "\033[33m>> Restricted user setup is not supported on Windows.\033[0m"
        echo -e "\033[33m>> While command validation is still active, there is no backup OS-level isolation.\033[0m"
    else
        echo -e "\033[32m>> Checking ACL support...\033[0m"
        if ! command -v setfacl &> /dev/null; then
            echo -e "\033[33m>> ACL support not found. Installing acl package (requires sudo)...\033[0m"
            if [ -f /etc/debian_version ]; then
                sudo apt-get update && sudo apt-get install -y acl
            elif [ -f /etc/redhat-release ]; then
                sudo yum install -y acl
            elif [ -f /etc/arch-release ]; then
                sudo pacman -S --noconfirm acl
            else
                echo -e "\033[31m>> Unsupported distribution. Please install 'acl' package manually.\033[0m"
                exit 1
            fi
        fi
        
        echo -e "\033[32m>> Setting up restricted user (requires sudo)...\033[0m"
        chmod +x ./scripts/setup_restricted_user.sh
        sudo ./scripts/setup_restricted_user.sh
        if [ $? -eq 0 ]; then
            echo -e "\033[32m>> Successfully set up restricted user\033[0m"
        else
            echo -e "\033[31m>> Failed to set up restricted user. Continuing without enhanced security...\033[0m"
        fi
    fi
else
    echo -e "\033[33m>> Skipping restricted user setup. You can run scripts/setup_restricted_user.sh later if needed.\033[0m"
fi

# Environment configuration
if [ -f .env ]; then
    echo -e "\033[32m>> Found existing .env file\033[0m"
    set -o allexport
    source .env
    set +o allexport
else
    echo -e "\033[34m>> No .env file found. Would you like to create one now? (y/n): \033[0m"
    read create_env

    if [[ ${create_env:0:1} =~ [yY] ]]; then
        echo -e "\033[32m>> Creating .env file...\033[0m"
        touch .env

        echo -e "\033[34m>> Do you have an Anthropic API key? (y/n): \033[0m"
        read has_anthropic
        if [[ ${has_anthropic:0:1} =~ [yY] ]]; then
            echo -e "\033[34m>> Please paste your Anthropic API key (Ctrl+Shift+V in most terminals): \033[0m"
            read anthropic_key
            # Check if key already has quotes
            if [[ $anthropic_key =~ ^\".*\"$ ]]; then
                echo "ANTHROPIC_API_KEY=$anthropic_key" >> .env
            else
                echo "ANTHROPIC_API_KEY=\"$anthropic_key\"" >> .env
            fi
            echo -e "\033[32m>> Anthropic API key saved. Please verify it was pasted correctly!\033[0m"
        fi

        echo -e "\033[34m>> Do you have an OpenAI API key? (y/n): \033[0m"
        read has_openai
        if [[ ${has_openai:0:1} =~ [yY] ]]; then
            echo -e "\033[34m>> Please paste your OpenAI API key (Ctrl+Shift+V in most terminals): \033[0m"
            read openai_key
            # Check if key already has quotes
            if [[ $openai_key =~ ^\".*\"$ ]]; then
                echo "OPENAI_API_KEY=$openai_key" >> .env
            else
                echo "OPENAI_API_KEY=\"$openai_key\"" >> .env
            fi
            echo -e "\033[32m>> OpenAI API key saved. Please verify it was pasted correctly!\033[0m"
        fi

        set -o allexport
        source .env
        set +o allexport
    else
        echo -e "\033[33m>> Skipping .env creation\033[0m"
    fi
fi

# Check API configuration status
if [ -f .env ] && { [ ! -z "$OPENAI_API_KEY" ] || [ ! -z "$ANTHROPIC_API_KEY" ]; }; then
    echo -e "\033[32m>> Model API: Configured\033[0m"
else
    echo -e "\033[31m>> Warning: No API key set\033[0m"
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