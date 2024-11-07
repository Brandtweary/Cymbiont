{ pkgs ? import <nixpkgs> { config = { allowUnfree = true; }; } }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python39
    python39Packages.pip
    python39Packages.virtualenv
    stdenv.cc.cc.lib
    git
    wget
    cmake
    ninja
    cudaPackages_11.cudatoolkit
  ];

  shellHook = ''
    # Add libstdc++ to library path
    export LD_LIBRARY_PATH=/run/opengl-driver/lib:${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH
    export CUDA_PATH=${pkgs.cudaPackages_11.cudatoolkit}

    echo ""
    echo -e "\033[32m╔════════════════════════════════════════╗\033[0m"
    echo -e "\033[32m║        Initializing \033[34mCyberOrganism\033[32m      ║\033[0m"
    echo -e "\033[32m╚════════════════════════════════════════╝\033[0m"
    echo -e "\033[32m>> Runtime: \033[34mPython $(python --version 2>&1 | cut -d' ' -f2)\033[0m"
    echo -e "\033[32m>> Environment: Development\033[0m"
    
    # Create and activate virtual environment
    if [ ! -d ".venv" ]; then
      echo -e "\033[32m>> Creating virtual environment...\033[0m"
      virtualenv .venv
    fi
    source .venv/bin/activate
    
    # Check internet connectivity
    if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        echo -e "\033[32m>> Network Status: \033[32mOnline\033[0m"
    else
        echo -e "\033[32m>> Network Status: \033[31mOffline\033[0m"
        echo -e "\033[31m>> Warning: Internet connection required \033[0m"
    fi
    
    # Load environment variables from .env if it exists
    if [ -f .env ]; then
      export $(cat .env | xargs)
      echo -e "\033[32m>> Environment file: \033[32mLoaded\033[0m"
    fi
    
    # Check for API keys (will work with .env loaded keys)
    if [ -z "$OPENAI_API_KEY" ]; then
      echo -e "\033[31m>> Warning: OPENAI_API_KEY not set\033[0m"
    else
      echo -e "\033[32m>> OpenAI API Key: Configured\033[0m"
    fi

    # More robust dependency installation check
    if [ ! -f "requirements.txt" ]; then
      echo -e "\033[31m>> Error: requirements.txt not found\033[0m"
      return 1
    fi

    # Check if dependencies are actually installed
    if [ ! -f ".venv/req_installed" ] || [ ! -d ".venv/lib/python3.9/site-packages" ]; then
      echo -e "\033[32m>> Installing Python dependencies...\033[0m"
      if pip install -r requirements.txt; then
        echo -e "\033[32m>> Dependencies installed successfully\033[0m"
        touch .venv/req_installed
      else
        echo -e "\033[31m>> Error: Failed to install dependencies\033[0m"
        rm -f .venv/req_installed  # Remove marker if installation failed
        return 1
      fi
    else
      echo -e "\033[32m>> Dependencies already installed\033[0m"
    fi

    # Check CUDA availability
    python3 -c "import torch; print('\033[32m>> CUDA Status:\033[0m', '\033[32mAvailable\033[0m' if torch.cuda.is_available() else '\033[31mNot Available\033[0m')"
    
    echo ""
  '';
}