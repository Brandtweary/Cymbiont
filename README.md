# CyberOrganism

An autonomous LLM agent with long-term memory.

## Setup Instructions

### Option 1: Using Nix (Linux)

The `shell.nix` file automatically sets up a complete development environment, including Python, CUDA, and all dependencies. It creates an isolated environment that won't interfere with your system packages.

1. Install the Nix package manager:
   ```bash
   # Install Nix
   curl -L https://nixos.org/nix/install | sh
   
   # Restart your terminal or run:
   source ~/.nix-profile/etc/profile.d/nix.sh
   ```

2. Download this repository:
   ```bash
   # Install git if you don't have it
   sudo apt install git  # Ubuntu/Debian
   sudo dnf install git  # Fedora
   
   # Clone the repository
   git clone https://github.com/Brandtweary/CyberOrganism.git
   
   # Enter the project directory
   cd CyberOrganism
   ```

3. Start the development environment:
   ```bash
   # With CUDA/GPU support (default)
   nix-shell

   # Or create a CPU-only configuration:
   echo '{ withCuda = false; }' > config.nix
   nix-shell
   ```

This will:
- Set up Python
- Install dependencies as nix packages
- Create a virtual environment and pip install remaining dependencies
- Configure environment variables from `.env` file

If something goes wrong:
- Check the error messages in the startup banner
- For GPU support: ensure you have NVIDIA drivers installed
- Configurations and paths can be modified in `shell.nix`

If you are using VSCode, you can use the `Nix Environment Selector` extension to automatically activate the nix shell when you open the IDE. 

### Option 2: Traditional Setup (All Platforms)

1. Install Python 3.13:
   - Windows: Download from [python.org](https://www.python.org/downloads/)
   - Mac: `brew install python@3.13`
   - Linux: `sudo apt install python3.13` (Ubuntu/Debian)

2. Download this repository:
   ```bash
   # Install git if you don't have it
   # Windows: Download from https://git-scm.com/download/win
   # Mac: brew install git
   # Linux: sudo apt install git
   
   git clone https://github.com/Brandtweary/CyberOrganism.git
   cd CyberOrganism
   ```

3. Create and activate a virtual environment:
   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate
   
   # Mac/Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install PyTorch:
   Visit [pytorch.org/get-started/locally](https://pytorch.org/get-started/locally/) and select your platform preferences. For GPU support on Windows/Linux, you'll also need to:
   1. Install NVIDIA drivers for your GPU
   2. Install CUDA from [developer.nvidia.com/cuda-downloads](https://developer.nvidia.com/cuda-downloads)

5. Install remaining dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Environment Variables

Create a `.env` file in the project root:
```bash
OPENAI_API_KEY=your_api_key_here
```
