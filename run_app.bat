@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [ERROR] .venv not found. Please create a virtual environment first:
    echo   python -m venv .venv
    echo   pip install -r requirements.txt
    exit /b 1
)

echo Starting SME Workflow Navigator on http://127.0.0.1:8000
python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000 --reload
