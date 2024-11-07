{ pkgs ? import <nixpkgs> { config = { allowUnfree = true; }; } }:

let
  pythonEnv = pkgs.buildFHSUserEnv {
    name = "hipporag-env";
    targetPkgs = pkgs: (with pkgs; [
      # Python and core build tools
      python39
      python39Packages.pip
      python39Packages.virtualenv
      git
      gitRepo
      gnupg
      autoconf
      curl
      procps
      gnumake
      util-linux
      m4
      gperf
      unzip
      wget
      cmake
      ninja
      gcc
      binutils
      
      # CUDA and graphics
      cudaPackages_11.cudatoolkit
      linuxPackages.nvidia_x11
      libGLU libGL
      xorg.libXi xorg.libXmu freeglut
      xorg.libXext xorg.libX11 xorg.libXv xorg.libXrandr
      
      # Common C libraries
      zlib
      ncurses5
      stdenv.cc
      binutils
    ]);

    multiPkgs = pkgs: with pkgs; [ zlib ];
    
    profile = ''
      export CUDA_PATH=${pkgs.cudaPackages_11.cudatoolkit}
      export LD_LIBRARY_PATH=/usr/lib:/run/opengl-driver/lib:${pkgs.linuxPackages.nvidia_x11}/lib:$LD_LIBRARY_PATH
      export EXTRA_LDFLAGS="-L/lib -L${pkgs.linuxPackages.nvidia_x11}/lib"
      export EXTRA_CCFLAGS="-I/usr/include"
      
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

      if [ ! -f ".venv/req_installed" ] || [ ! -d ".venv/lib/python3.9/site-packages" ]; then
        echo -e "\033[32m>> Installing Python dependencies...\033[0m"
        if pip install -r requirements.txt; then
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

      # Check CUDA availability
      python3 -c "import torch; print('\033[32m>> CUDA Status:\033[0m', '\033[32mAvailable\033[0m' if torch.cuda.is_available() else '\033[31mNot Available\033[0m')"
      
      echo ""
    '';
  };
in
  pythonEnv.env