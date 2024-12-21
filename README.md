# Cymbiont

Cymbiont is an autonomous machine life framework designed to serve as a container for perpetual AI agents. It provides a sophisticated environment where AI agents can exist and operate continuously, whether deployed in the cloud or run locally (local deployment currently in development).

At its core, Cymbiont implements a graph-based RAG (Retrieval-Augmented Generation) system for long-term memory, enabling agents to maintain and utilize their experiences effectively over time. This advanced memory architecture allows for more coherent and context-aware interactions.

## Setup Instructions

### Setting up Hugging Face Access

1. Create a Hugging Face account at https://huggingface.co/
2. Create an access token at https://huggingface.co/settings/tokens
3. Run `huggingface-cli login` in your terminal
4. Paste your token when prompted
5. Select "no" when asked about git credentials (unless you need git access to private repos)

Note: You'll also need to request access to Llama-3.3-70B-Instruct at https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct before you can download it.

### Interactive Setup (Linux/Mac Only)

1. Install Python:
   - Linux: `sudo apt install python3.12` (Ubuntu/Debian)
   - Mac: `brew install python@3.12`

   **Note:** Python 3.12 is recommended. Newer versions may be incompatible with PyTorch.

2. Clone and enter the repository:
   ```bash
   git clone https://github.com/Brandtweary/Cymbiont.git
   cd Cymbiont
   ```

3. Run the bootstrap script:
   ```bash
   # Linux/Mac only
   bash bootstrap.sh  # Run with bash

   chmod +x bootstrap.sh # Or make executable first
   ./bootstrap.sh
   ```

The bootstrap script will:
- Create a Python virtual environment
- Install project dependencies
- Guide you through PyTorch installation
- Perform system status checks
- Optionally create a `.env` file and walk you through API key configuration
- Optionally set up a restricted user for enhanced security (Linux only)
- Optionally launch Cymbiont

The script will attempt to use the nvidia-smi tool to determine your CUDA version. If you don't have nvidia-smi, you can determine your CUDA version using a different method, or you can proceed if you already know which PyTorch compute platform you want (e.g. CPU, CUDA, ROCM). The PyTorch installation step can be skipped and performed later by running the bootstrap script again or [installing PyTorch manually](https://pytorch.org/get-started/locally/). 

### Manual Setup (All Platforms)

1. Install Python and clone repo (steps 1 and 2 above).

2. Create and activate a virtual environment:
   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate
   
   # Linux/Mac
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install PyTorch:
   Visit [pytorch.org/get-started/locally](https://pytorch.org/get-started/locally/) and follow the installation instructions for your platform and compute preferences.

5. (Optional) Set up restricted user for enhanced security:
   ```bash
   # Linux only - requires sudo
   
   # Install ACL support (probably on your system already)
   sudo apt-get install acl  # For Debian/Ubuntu
   sudo yum install acl      # For RHEL/CentOS
   sudo pacman -S acl        # For Arch Linux

   # Run the setup script
   chmod +x ./scripts/setup_restricted_user.sh
   sudo ./scripts/setup_restricted_user.sh
   ```

## API Keys

Create a `.env` file in the project root and set at least one of the following variables:
```bash
OPENAI_API_KEY="your_api_key_here"
ANTHROPIC_API_KEY="your_api_key_here"
```
The bootstrap script will walk you through this step if this file is not present.

## Running Cymbiont

### Quick Start
```bash
python cymbiont.py
```
Cymbiont will automatically use the virtual environment created during setup. If you are using an alternative environment manager, see the [Alternative Environment Managers](#alternative-environment-managers) section below.

### Environment Issues?
If you encounter any environment-related errors, you can re-run the bootstrap script:
```bash
# Linux/Mac
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

#### Shell Access Tiers

The `shell_access_tier` setting in `config.toml` determines the security level for shell commands that can be used by the agent. Available tiers:

1. **TIER_1_PROJECT_READ** (Default)
   - Read-only access to project files only
   - Cannot execute files or scripts
   - Cannot navigate outside project directory
   - Supports OS-level isolation via restricted user

2. **TIER_2_SYSTEM_READ**
   - Read-only access to system files
   - Cannot execute files or scripts
   - Can navigate and read outside project directory
   - Supports OS-level isolation via restricted user

3. **TIER_3_PROJECT_RESTRICTED_WRITE**
   - Read-only access to system files
   - Write access to agent notes directory only
   - Cannot execute files or scripts
   - Supports OS-level isolation via restricted user

4. **TIER_4_PROJECT_WRITE_EXECUTE**
   - Read-only access to system files
   - Write access to project files
   - Can execute files within project
   - Supports OS-level isolation via restricted user
   - **Not recommended**

5. **TIER_5_UNRESTRICTED**
   - Full system access
   - No restrictions on file operations
   - No OS-level isolation
   - **Not recommended**

You should run `sudo ./scripts/setup_restricted_user.sh` to create the necessary restricted users and set up filesystem ACLs for OS-level isolation.

**Note:** Restricted user setup is currently only supported on Linux. While command validation remains active on all platforms, there is no backup OS-level isolation on Windows or Mac. Docker containerization support is planned for future releases to provide proper cross-platform isolation.

## Testing

There are three ways to run tests in Cymbiont:

### 1. Interactive Shell Command
From within Cymbiont, use the shell command:
```
run_all_tests
```
This will run all tests and display the results. You can also run specific test modules with commands like `test_logger`, `test_api_queue`, etc.

### 2. Command Line Interface
You can run tests directly from the command line using a '--test' flag on the cymbiont executable:
```bash
# Run all tests
python cymbiont.py --test

# Run a specific test by including the suffix in the test module name as an argument
python cymbiont.py --test logger
python cymbiont.py --test api_queue
```

### 3. Module Execution
You can run test scripts using Python's module execution:
```bash
# Run all test modules
python -m tests

# Run a specific test module
python -m tests.test_logger
```
This will automatically route the test through the cymbiont executable to ensure proper environment setup.

### Alternative Environment Managers
If you prefer to use conda, poetry, or another environment manager:
1. Create your config file if you haven't done so already: `cp config.example.toml config.toml`
2. Set `manage_venv = false` in config.toml
3. Activate your preferred environment
4. Run `./bootstrap.sh` to install dependencies into that environment, or follow the manual setup instructions for steps 3 and 4.
5. Run `python cymbiont.py` from the activated environment.