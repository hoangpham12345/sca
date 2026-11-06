import os
import json
import datetime
from typing import List, Dict, Any

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions")

def ensure_session_dir():
    os.makedirs(SESSIONS_DIR, exist_ok=True)

def list_saved_sessions() -> List[str]:
    """List all saved session file names."""
    ensure_session_dir()
    files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(SESSIONS_DIR, f)), reverse=True)
    return files

def save_session(session_name: str, messages: List[Dict[str, Any]], settings: Dict[str, Any]) -> str:
    """Save messages and configuration settings to a JSON file."""
    ensure_session_dir()
    # Clean file name
    clean_name = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in session_name]).strip("_")
    if not clean_name:
        clean_name = f"chat_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    file_path = os.path.join(SESSIONS_DIR, f"{clean_name}.json")
    data = {
        "title": session_name,
        "saved_at": datetime.datetime.now().isoformat(),
        "settings": settings,
        "messages": messages
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return file_path

def load_session(filename: str) -> Dict[str, Any]:
    """Load conversation and settings from a JSON file."""
    ensure_session_dir()
    file_path = os.path.join(SESSIONS_DIR, filename)
    if not os.path.exists(file_path):
        return {"messages": [], "settings": {}}
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def delete_session(filename: str):
    """Delete a saved session file."""
    ensure_session_dir()
    file_path = os.path.join(SESSIONS_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
