#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import tomllib

def ensure_venv() -> None:
    """Ensure we're running in a virtual environment if enabled."""
    # Load config first
    with open("config.toml", "rb") as f:
        config = tomllib.load(f)
    
    if not config.get("environment", {}).get("manage_venv", True):
        return  # Venv management disabled
    
    if not sys.prefix == sys.base_prefix:
        return  # Already in a virtual environment
        
    venv_path = Path('.venv')
    if not venv_path.exists():
        print("\033[31mError: No virtual environment found. Please run bootstrap.sh first.\033[0m")
        sys.exit(1)

    # Re-execute using the venv's Python
    if sys.platform == 'win32':
        python = venv_path / 'Scripts' / 'python.exe'
    else:
        python = venv_path / 'bin' / 'python'

    if not python.exists():
        print("\033[31mError: Virtual environment appears corrupted. Try running bootstrap.sh again.\033[0m")
        sys.exit(1)

    # Replace current process with one using the venv's Python
    os.execv(str(python), [str(python), __file__])

if __name__ == "__main__":
    ensure_venv()
    
    try:
        from src.main import main
        main()
    except ImportError as e:
        print(f"\033[31mError importing main: {e}\033[0m")
        print("\033[34mTip: Run bootstrap.sh to install dependencies\033[0m")
        sys.exit(1)