#!/usr/bin/env bash
# ==============================================================================
# Cross-Platform SME Workflow Navigator Runner (FastAPI + Dedicated UI)
# ==============================================================================
set -e

cd "$(dirname "$0")"

# 1. Activate virtual environment (Linux bin/ vs Windows Git Bash Scripts/)
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
else
    echo -e "\033[1;31m[ERROR] .venv not found. Please run ./setup.sh first.\033[0m"
    exit 1
fi

# 2. Load .env file (stripping Windows \r carriage returns if created on Windows)
if [ -f .env ]; then
    set -a
    eval "$(grep -E -v '^\s*(#|$)' .env | tr -d '\r' | sed 's/^/export /')"
    set +a
fi

echo -e "\033[1;32m🚀 Starting SME Workflow Navigator on http://127.0.0.1:8000 (or http://localhost:8000)\033[0m"
echo -e "\033[1;36m📡 LiteLLM Gateway: ${LITELLM_ENDPOINT_URL:-http://localhost:4000/v1}\033[0m"
echo "Press Ctrl+C to stop."
echo ""

# 3. Launch FastAPI server hosting the dedicated UI and SSE streaming
exec python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000 --reload
