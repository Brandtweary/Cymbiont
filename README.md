# CyberOrganism

An autonomous LLM agent with long-term memory.

## Setup Instructions

### Quick Setup (All Platforms)

1. Install Python:
   - Windows: Download from [python.org](https://www.python.org/downloads/)
   - Mac: `brew install python@3.12`
   - Linux: `sudo apt install python3.12` (Ubuntu/Debian)

   **Note:** Python 3.12 is recommended. Newer versions may be incompatible with PyTorch.

2. Clone and enter the repository:
   ```bash
   git clone https://github.com/Brandtweary/CyberOrganism.git
   cd CyberOrganism
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
- Configure environment variables
- Verify CUDA availability (if applicable)

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