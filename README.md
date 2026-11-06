# Enterprise AI Agent & SME Workflow Navigator

A lightweight, enterprise-ready AI chat interface and autonomous workflow agent built with **FastAPI**, **Tailwind CSS**, and **LiteLLM**, connected directly to any OpenAI-compatible **LiteLLM Proxy Gateway**.

---

## 🌟 Key Features

### 1. Dual Mode Interface
Seamlessly toggle between conversational and project workflow modes from the top bar:
- **💬 Chat Mode**:
  - Full-featured multi-turn conversational AI interface.
  - Dynamic model selector filtered against enterprise-authorized models in `allowed_models.yaml`.
  - Configurable reasoning effort levels (`Low`, `Medium`, `High`) for supported reasoning models.
  - Real-time token streaming via Server-Sent Events (SSE) with typing indicators.
  - Rich Markdown rendering (code syntax highlighting, one-click copy, tables, lists).
  - Multi-conversation thread management with server-side disk persistence.
  - Real-time token pre-computation and per-turn cost tracking.
  - Light and Dark color themes with automatic preference retention.
- **⚡ Workflow Mode (SME Workflow Navigator)**:
  - Multi-ticket tabbed workspace (`SMS-22219`, `SMS-22220`, `SMS-22237`, etc.).
  - Ticket metadata banners with status tags.
  - Horizontal delivery pipeline stepper (`REQ` → `PLAN` → `DESIGN` → `IMPL` → `E2E` → `DEPLOY` → `WRAP`).
  - Execution console with stage task sidebar, prompt presets, and live agent terminal output.

### 2. Sandboxed Agent Workspace & Tools
- **Filesystem Tools**: The AI agent can inspect, create, edit, and organize project files using built-in sandboxed tools (`read_workspace_file`, `write_workspace_file`, `edit_workspace_file`, `list_workspace_files`, `delete_workspace_file`).
- **Path Traversal Sandboxing**: All agent file operations and workspace requests are strictly anchored to the project's `./workspace` directory, safely preventing traversal (`../`) or access to arbitrary host system paths.
- **Interactive File Explorer**: Explore, view, and inspect generated workspace files directly from the UI sidebar.

### 3. Security & Corporate Network Hardening
- **Localhost Only**: Binds strictly to `127.0.0.1` by default, preventing unintended network exposure across local intranets.
- **SSRF Protection**: The built-in `fetch_web_content` tool strictly validates destination URLs:
  - Restricts schemes to `http` and `https`.
  - Blocks requests to loopback addresses (`127.0.0.1`, `localhost`, `::1`).
  - Blocks private RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
  - Blocks cloud provider instance metadata services (`169.254.169.254`).
  - Protects against open-redirect SSRF bypasses.
- **100% Offline & Firewall-Safe**: All frontend vendor assets (Tailwind CSS, Lucide icons, Marked markdown parser) are bundled locally under `frontend/vendor/`. No external CDNs, fonts, or tracking scripts are requested.
- **Zero Build Step**: Pure HTML5/JavaScript Single Page Application served directly by FastAPI without requiring Node.js, npm, or frontend bundlers.

---

## 📁 Project Structure

```text
fr-litellm/
├── backend/
│   └── server.py             # FastAPI server with SSE streaming, workspace & chat APIs
├── frontend/
│   ├── index.html            # Single Page Application (Chat & Workflow interfaces)
│   └── vendor/               # Local vendor dependencies (Tailwind, Lucide, Marked)
├── agent/
│   ├── litellm_client.py     # LiteLLM streaming client & agent loop
│   ├── tools.py              # Sandboxed workspace tools & SSRF-safe web fetching
│   └── session_manager.py    # Session storage helpers
├── workspace/                # Sandboxed directory for agent file operations
├── data/
│   └── chats/                # Persisted conversation threads
├── allowed_models.yaml       # Authorized enterprise models catalogue
├── requirements.txt          # Python dependencies
├── .env.example              # Template environment configuration
├── setup.sh                  # Setup script for Linux / macOS / WSL
├── run_app.sh                # Launch script for Linux / macOS / WSL
└── README.md                 # Project documentation
```

---

## 🚀 Quickstart

### Prerequisites
- Python 3.11+
- Access to a LiteLLM Proxy endpoint (local or remote)

### 1. Environment Setup

#### Linux / macOS / WSL:
```bash
chmod +x setup.sh run_app.sh
./setup.sh
```

#### Windows (PowerShell / Command Prompt):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and specify your LiteLLM gateway details:

```env
LITELLM_ENDPOINT_URL=http://localhost:4000/v1
LITELLM_API_KEY=your_actual_key_here
```

### 3. Launch the Application

#### Linux / macOS / WSL:
```bash
./run_app.sh
```

#### Windows (PowerShell / Command Prompt):
```bat
run_app.bat
```
*(Or manually: `python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000 --reload`)*

Open your browser to:
```text
http://127.0.0.1:8000
```
