#!/usr/bin/env bash
# ==============================================================================
# Cross-Platform Setup Script (Native Linux, macOS, WSL, & Windows Git Bash)
# ==============================================================================
set -e

# Change to script directory
cd "$(dirname "$0")"

echo -e "\033[1;34m==================================================\033[0m"
echo -e "\033[1;34m  Setting up LiteLLM Chat Agent Environment       \033[0m"
echo -e "\033[1;34m==================================================\033[0m"

# 1. Detect Python 3.11+ interpreter
PYTHON_BIN=""
for cmd in python3 python python3.14 python3.13 python3.12 python3.11; do
    if command -v "$cmd" &> /dev/null; then
        # Check that it's Python 3
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
            PYTHON_BIN="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo -e "\033[1;31m[ERROR] Python 3.11+ is required but was not found.\033[0m"
    echo "On Debian/Ubuntu: sudo apt update && sudo apt install python3 python3-venv python3-pip"
    echo "On Fedora/RHEL:   sudo dnf install python3 python3-pip"
    echo "On Arch Linux:    sudo pacman -S python python-pip"
    echo "On macOS:         brew install python@3.11"
    exit 1
fi

echo -e "Using Python: \033[1;32m$($PYTHON_BIN --version)\033[0m ($PYTHON_BIN)"

# 2. Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv..."
    if ! "$PYTHON_BIN" -m venv .venv; then
        echo -e "\033[1;31m[ERROR] Failed to create virtual environment.\033[0m"
        echo "If you are on Debian/Ubuntu, run: sudo apt install python3-venv"
        exit 1
    fi
else
    echo "Virtual environment .venv already exists."
fi

# 3. Activate virtual environment (detects Linux/macOS bin/ vs Windows Git Bash Scripts/)
if [ -f ".venv/bin/activate" ]; then
    # Native Linux / macOS
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    # Windows Git Bash / Cygwin / MSYS
    source .venv/Scripts/activate
else
    echo -e "\033[1;31m[ERROR] Cannot locate activation script in .venv.\033[0m"
    exit 1
fi

# 4. Prepare .env file from .env.example if missing
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "Creating .env from .env.example template..."
        cp .env.example .env
    else
        touch .env
    fi
fi

# 5. Upgrade pip & install dependencies
echo "Installing project dependencies from requirements.txt..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo ""
echo -e "\033[1;32m==================================================\033[0m"
echo -e "\033[1;32m  Setup completed successfully!                   \033[0m"
echo -e "\033[1;32m==================================================\033[0m"
echo "Next steps:"
echo "  1. Verify your API key in .env (LITELLM_API_KEY=...)"
echo "  2. Launch the application: ./run_app.sh"
