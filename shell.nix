{ pkgs ? import <nixpkgs> { config = { allowUnfree = true; }; } }:

let
  # Import configuration from config.nix if it exists, otherwise use defaults
  configFile = ./config.nix;
  config = if builtins.pathExists configFile
    then import configFile
    else { withCuda = true; };

  pythonEnv = pkgs.buildFHSUserEnv {
    name = "cyberorganism-env";
    targetPkgs = pkgs: (with pkgs; [
      # Python and core ML packages
      python312
      python312Packages.pip
      python312Packages.virtualenv
      (if config.withCuda then python312Packages.torchWithCuda else python312Packages.torch)
      
      # Basic development tools
      git
      curl
      wget
      
      # Build essentials (for potential pip packages)
      gcc
      binutils
      cmake
      zlib
      stdenv.cc
      
    ] ++ (if config.withCuda then [
      # CUDA-specific packages
      cudaPackages.cudatoolkit
    ] else []));

    multiPkgs = pkgs: with pkgs; [ zlib ];
    
    profile = ''
      ${if config.withCuda then ''
        # Set CUDA environment
        export CUDA_PATH=${pkgs.cudaPackages.cudatoolkit}
        export CUDA_HOME=$CUDA_PATH
        export PATH=$CUDA_PATH/bin:$PATH
        export CUDA_CACHE_PATH="$HOME/.cache/cuda"
        export CUDA_CACHE_MAXSIZE=2147483648
      '' else ""}
      
      # Cache configuration
      export CUDA_CACHE_PATH="$HOME/.cache/cuda"
      export CUDA_CACHE_MAXSIZE=2147483648  # 2GB cache size
      
      # Pretty startup banner
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
      
      # Load environment variables from .env
      if [ -f .env ]; then
        export $(cat .env | xargs)
        echo -e "\033[32m>> Environment file: \033[32mLoaded\033[0m"
      fi
      
      # Check for API keys
      if [ -z "$OPENAI_API_KEY" ]; then
        echo -e "\033[31m>> Warning: OPENAI_API_KEY not set\033[0m"
      else
        echo -e "\033[32m>> OpenAI API Key: Configured\033[0m"
      fi

      # Dependency installation check
      if [ ! -f "requirements.txt" ]; then
        echo -e "\033[31m>> Error: requirements.txt not found\033[0m"
        return 1
      fi

      # Set NIX_MANAGED flag for requirements.txt conditional installs
      export NIX_MANAGED=1
      
      if [ ! -f ".venv/req_installed" ] || [ ! -d ".venv/lib/python3.12/site-packages" ]; then
        echo -e "\033[32m>> Installing Python dependencies...\033[0m"
        if pip install -r requirements.txt --no-deps --ignore-installed; then
          echo -e "\033[32m>> Dependencies installed successfully\033[0m"
          touch .venv/req_installed
        else
          echo -e "\033[31m>> Error: Failed to install dependencies\033[0m"
          rm -f .venv/req_installed
          return 1
        fi
      else
        echo -e "\033[32m>> Dependencies already installed\033[0m"
      fi

      # Enhanced CUDA check
      python3 -c '
      import torch
      cuda_available = torch.cuda.is_available()
      device_count = torch.cuda.device_count() if cuda_available else 0
      print("\033[32m>> CUDA Status:\033[0m", "\033[32mAvailable\033[0m" if cuda_available else "\033[31mNot Available\033[0m")
      if cuda_available:
          print("\033[32m>> CUDA Devices:\033[0m", "\033[32m" + str(device_count) + "\033[0m")
          print("\033[32m>> CUDA Version:\033[0m", "\033[34m" + torch.version.cuda + "\033[0m")
      '
    '';
  };
in
  pythonEnv.env