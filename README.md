# Cymbiont

An autonomous LLM agent with long-term memory.

## Setup Instructions

### Interactive Setup (Recommended)

1. Install Python:
   - Windows: Download from [python.org](https://www.python.org/downloads/)
   - Mac: `brew install python@3.12`
   - Linux: `sudo apt install python3.12` (Ubuntu/Debian)

   **Note:** Python 3.12 is recommended. Newer versions may be incompatible with PyTorch.

2. Clone and enter the repository:
   ```bash
   git clone https://github.com/Brandtweary/Cymbiont.git
   cd Cymbiont
   ```

3. Run the bootstrap script:
   ```bash
   # Windows
   ./bootstrap.sh

   # Mac/Linux
   bash bootstrap.sh  # Run with bash

   chmod +x bootstrap.sh # Or make executable first
   ./bootstrap.sh
   ```

The bootstrap script will:
- Create a Python virtual environment
- Install project dependencies
- Guide you through PyTorch installation
- Perform system status checks
- Optionally launch Cymbiont

The script will attempt to use the nvidia-smi tool to determine your CUDA version. If you don't have nvidia-smi, you can determine your CUDA version using a different method, or you can proceed if you already know which PyTorch compute platform you want (e.g. CPU, CUDA, ROCM). The PyTorch installation step can be skipped and performed later by running the bootstrap script again or [installing PyTorch manually](https://pytorch.org/get-started/locally/). 

### Manual Setup

1. Install Python and clone repo (steps 1 and 2 above).

2. Create and activate a virtual environment:
   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate
   
   # Mac/Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install PyTorch:
   Visit [pytorch.org/get-started/locally](https://pytorch.org/get-started/locally/) and follow the installation instructions for your platform and compute preferences.

## Environment Variables

Create a `.env` file in the project root and set the following variables:
```bash
OPENAI_API_KEY=your_api_key_here
```

## Running Cymbiont

### Quick Start
```bash
python cymbiont.py
```
Cymbiont will automatically use the virtual environment created during setup. If you are using an alternative environment manager, see the [Alternative Environment Managers](#alternative-environment-managers) section below.

### Environment Issues?
If you encounter any environment-related errors, you can re-run the bootstrap script:
```bash
./bootstrap.sh  # or: bash bootstrap.sh
```
This will repair the virtual environment and reinstall dependencies if needed.

### Configuration

Cymbiont uses `config.toml` for configuration. If this file doesn't exist, it will be automatically created from `config.example.toml` when you first run the program.

To customize settings before first run:
```bash
cp config.example.toml config.toml
# Edit config.toml with your preferred settings
```

### Alternative Environment Managers
If you prefer to use conda, poetry, or another environment manager:
1. Create your config file if you haven't done so already: `cp config.example.toml config.toml`
2. Set `manage_venv = false` in config.toml
3. Activate your preferred environment
4. Run `./bootstrap.sh` to install dependencies into that environment, or follow the manual setup instructions for steps 3 and 4.
5. Run `python cymbiont.py` from the activated environment.