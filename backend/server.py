import os
import json
import asyncio
import urllib.request
import yaml
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import LiteLLM client runner & tools
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from agent.litellm_client import run_agent_turn, normalize_model_for_proxy
from agent.tools import TOOL_DEFINITIONS, sanitize_workspace_dir, resolve_workspace_path

app = FastAPI(title="SME Workflow Navigator API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_ALLOWED_MODELS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "allowed_models.yaml")

# ----------------- TICKET & WORKFLOW MOCK DATA -----------------
TICKETS_DATA = [
    {
        "id": "SMS-22220",
        "title": "[ALB/Theory] SMEPLN22003BL09 シーズン別事業別チャネル別G部門別前期売上実績",
        "code": "SMS-22220",
        "tags": ["CR", "In Progress", "pin"],
        "active_stage": "DESIGN",
        "completed_subtasks": 2,
        "total_subtasks": 5
    },
    {
        "id": "SMS-22219",
        "title": "[ALB/Theory] SMEPLN22003BL08 売上実績データ集計処理",
        "code": "SMS-22219",
        "tags": ["CR", "Done", "pin"],
        "active_stage": "DEPLOY",
        "completed_subtasks": 5,
        "total_subtasks": 5
    },
    {
        "id": "SMS-22237",
        "title": "[ALB/Theory] SMEPLN22003BL10 共通マスター検証",
        "code": "SMS-22237",
        "tags": ["Bug", "To Do"],
        "active_stage": "REQ",
        "completed_subtasks": 0,
        "total_subtasks": 4
    }
]

WORKFLOW_STAGES = [
    {
        "id": "REQ",
        "name": "REQ",
        "label": "Requirements",
        "count": "1/1",
        "status": "completed",
        "code": "SMS-22960",
        "badge": "Done",
        "subcard_desc": "[Req] Requirements analysis",
        "console_title": "Requirements Analysis",
        "console_subtitle": "REQ-ANALYSIS · SMS-22960 — Q&A to clarify requirements scope, then write a user story with acceptance criteria",
        "preset_prompt": "/dev-req-analysis req-analysis SMS-22220",
        "subtasks": [
            {"id": "req-1", "name": "Requirements Analysis", "status": "Done"}
        ]
    },
    {
        "id": "PLAN",
        "name": "PLAN",
        "label": "Plan",
        "count": "3/3",
        "status": "completed",
        "code": "SMS-22962",
        "badge": "Done",
        "subcard_desc": "[Plan] Planning",
        "console_title": "Plan Creation",
        "console_subtitle": "PLAN · SMS-22962 — Research the codebase to understand the main scope of the ticket and create an implementation plan",
        "preset_prompt": "/dev-plan plan-creation SMS-22220",
        "subtasks": [
            {"id": "plan-1", "name": "Plan Creation", "status": "Done"},
            {"id": "plan-2", "name": "Impact Analysis", "status": "Done"},
            {"id": "plan-3", "name": "Task Breakdown", "status": "Done"}
        ]
    },
    {
        "id": "DESIGN",
        "name": "DESIGN",
        "label": "Design",
        "count": "0/2",
        "status": "active",
        "code": "SMS-23005",
        "badge": "To Do",
        "subcard_desc": "[Design] Write spec: Batch — SMEPLN22003BL20 previous-year sales actuals by channel",
        "console_title": "Write Spec",
        "console_subtitle": "DESIGN · SMS-23005 — Q&A to clarify design scope, then research context and write spec documents",
        "preset_prompt": "/dev-design spec-creation SMS-23005",
        "subtasks": [
            {"id": "des-1", "name": "Write Spec", "status": "To Do"},
            {"id": "des-2", "name": "Review Spec", "status": "To Do"}
        ]
    },
    {
        "id": "IMPL",
        "name": "IMPL",
        "label": "Implementation",
        "count": "0/3",
        "status": "pending",
        "code": "SMS-23006",
        "badge": "To Do",
        "subcard_desc": "[Impl] Batch: SMEPLN22003BL20 previous-year sales actuals by channel",
        "console_title": "Implement",
        "console_subtitle": "IMPL · SMS-23006 — Implement core batch logic and business services based on spec",
        "preset_prompt": "/dev-impl code-implementation SMS-23006",
        "subtasks": [
            {"id": "imp-1", "name": "Implement", "status": "To Do"},
            {"id": "imp-2", "name": "Unit Tests", "status": "To Do"},
            {"id": "imp-3", "name": "Review", "status": "To Do"}
        ]
    },
    {
        "id": "E2E",
        "name": "E2E",
        "label": "E2E Test",
        "count": "-",
        "status": "pending",
        "code": "SMS-23010",
        "badge": "To Do",
        "subcard_desc": "[E2E] End-to-End Regression & Integration Suite",
        "console_title": "Create E2E Test Cases",
        "console_subtitle": "E2E · SMS-23010 — Prepare end-to-end regression suites and execution scripts",
        "preset_prompt": "/dev-e2e test-cases SMS-23010",
        "subtasks": [
            {"id": "e2e-1", "name": "Create E2E Test Cases", "status": "To Do"},
            {"id": "e2e-2", "name": "E2E Test Execution", "status": "To Do"}
        ]
    },
    {
        "id": "DEPLOY",
        "name": "DEPLOY",
        "label": "Deployment",
        "count": "0/1",
        "status": "pending",
        "code": "SMS-23012",
        "badge": "To Do",
        "subcard_desc": "[Deploy] Staging deployment pipeline and health check",
        "console_title": "Deploy Staging",
        "console_subtitle": "DEPLOY · SMS-23012 — Trigger staging deployment pipeline and verification checks",
        "preset_prompt": "/dev-deploy staging SMS-23012",
        "subtasks": [
            {"id": "dep-1", "name": "Deploy Staging", "status": "To Do"}
        ]
    },
    {
        "id": "WRAP",
        "name": "WRAP",
        "label": "Wrap Up",
        "count": "0/1",
        "status": "pending",
        "code": "SMS-23015",
        "badge": "To Do",
        "subcard_desc": "[Wrap] Documentation, test artifacts & ticket signoff",
        "console_title": "Close Ticket & Docs",
        "console_subtitle": "WRAP · SMS-23015 — Finalize documentation, attach test artifacts, and resolve ticket",
        "preset_prompt": "/dev-wrap finalize SMS-23015",
        "subtasks": [
            {"id": "wrap-1", "name": "Close Ticket & Docs", "status": "To Do"}
        ]
    }
]

# ----------------- API ENDPOINTS -----------------

@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "SME Workflow Navigator API"}


MODEL_EFFORT_MAP: Dict[str, List[str]] = {
    # Google Enterprise Agent Platform (Gemini Models)
    "google/gemini-3.8-flash": ["Low", "Medium", "High"],
    "google/gemini-3.5-flash": ["Low", "Medium", "High"],
    "google/gemini-3.1-pro-preview": ["Low", "Medium", "High"],
    "google/gemini-3.1-flash-lite": [],
    "google/gemini-4-argon": ["Low", "Medium", "High"],

    # Anthropic Claude Models
    "claude-sonnet-5-5": ["Low", "Medium", "High"],
    "claude-sonnet-5": ["Low", "Medium", "High"],
    "claude-opus-5-5": ["Low", "Medium", "High"],
    "claude-opus-5": ["Low", "Medium", "High"],
    "claude-haiku-5-5": [],
    "claude-haiku-4-5-20251001": [],

    # DeepSeek Models (DeepSeek V4 models only have Low, High effort)
    "deepseek/deepseek-v4-pro": ["Low", "High"],
    "deepseek/deepseek-v4-flash": ["Low", "High"],
    "deepseek/deepseek-V3.2": [],

    # OpenAI Models
    "gpt-5.5": ["Low", "Medium", "High"],
    "gpt-5.4-mini": ["Low", "Medium", "High"],
    "o4-mini": ["Low", "Medium", "High"],
}


@app.get("/api/models/effort-map")
def get_model_effort_map():
    """Returns mapping of models to their supported effort options (Low, Medium, High)."""
    return MODEL_EFFORT_MAP


@app.get("/api/models")
def get_models():
    """Returns the authorized models list from allowed_models.yaml."""
    if not os.path.exists(CONFIG_ALLOWED_MODELS):
        return ["google/gemini-3.8-flash", "claude-sonnet-5-5", "deepseek/deepseek-v4-pro", "gpt-5.5"]
    try:
        with open(CONFIG_ALLOWED_MODELS, "r", encoding="utf-8") as f:
            models = yaml.safe_load(f)
            return [m for m in models if isinstance(m, str) and m.strip()]
    except Exception:
        return ["google/gemini-3.8-flash", "claude-sonnet-5-5", "deepseek/deepseek-v4-pro"]


@app.get("/api/tickets")
def get_tickets():
    return TICKETS_DATA


@app.get("/api/tickets/{ticket_id}/workflow")
def get_workflow(ticket_id: str):
    ticket = next((t for t in TICKETS_DATA if t["id"] == ticket_id), None)
    if not ticket:
        # Support dynamically entered ticket codes like SMS-1234
        ticket = {
            "id": ticket_id,
            "title": f"[ALB/Theory] {ticket_id} Automated Workflow Specification",
            "code": ticket_id,
            "tags": ["CR", "In Progress", "pin"],
            "active_stage": "REQ",
            "completed_subtasks": 0,
            "total_subtasks": 5
        }
    return {
        "ticket": ticket,
        "stages": WORKFLOW_STAGES,
        "active_stage_id": ticket.get("active_stage", "DESIGN")
    }


class ExecutionRequest(BaseModel):
    ticket_id: str
    stage_id: str
    preset_prompt: str
    additional_instructions: Optional[str] = ""
    model: str = "google/gemini-3.8-flash"
    effort: str = "Medium"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: str = "google/gemini-3.8-flash"
    temperature: float = 0.7
    system_prompt: Optional[str] = "You are a helpful enterprise AI assistant."
    tools_enabled: bool = True
    effort: Optional[str] = None
    workspace_dir: Optional[str] = "./workspace"


class CountTokensRequest(BaseModel):
    messages: List[ChatMessage]
    model: str = "google/gemini-3.8-flash"
    system_prompt: Optional[str] = None
    tools_enabled: bool = False
    workspace_dir: Optional[str] = "./workspace"


@app.post("/api/chat/count-tokens")
def count_chat_tokens(req: CountTokensRequest):
    """
    Computes exact/proxy theoretical token count for a candidate message payload.
    Directly queries LiteLLM Proxy /utils/token_counter; falls back to litellm.token_counter.
    Includes workspace capabilities and tool schemas when tools_enabled is True.
    """
    endpoint_url = os.getenv("LITELLM_ENDPOINT_URL", "http://localhost:4000/v1")
    api_key = os.getenv("LITELLM_API_KEY", "")

    ws_display = req.workspace_dir or "./workspace"
    ws_dir = sanitize_workspace_dir(ws_display)

    base_sys_prompt = req.system_prompt.strip() if req.system_prompt and req.system_prompt.strip() else "You are a senior enterprise AI assistant."
    if req.tools_enabled:
        base_sys_prompt += (
            f"\n\n[WORKSPACE CAPABILITIES]\n"
            f"Active workspace directory: '{ws_display}'.\n"
            f"You have access to specialized tools to interact with this workspace:\n"
            f"- write_workspace_file(file_path, content): Create or overwrite files.\n"
            f"- read_workspace_file(file_path): Read file contents.\n"
            f"- edit_workspace_file(file_path, target_string, replacement_string): Modify existing code or text.\n"
            f"- list_workspace_files(subpath): Explore files and folders in the workspace.\n"
            f"- delete_workspace_file(file_path): Remove files.\n"
            f"Whenever asked to create, modify, inspect, or manage files or projects, invoke the appropriate workspace tools."
        )

    all_messages = [{"role": "system", "content": base_sys_prompt}]
    for m in req.messages:
        all_messages.append({"role": m.role, "content": m.content})

    target_model = normalize_model_for_proxy(req.model, endpoint_url)
    tools = TOOL_DEFINITIONS if req.tools_enabled else None

    # 1. Query LiteLLM Proxy /utils/token_counter
    proxy_counter_urls = []
    if endpoint_url:
        proxy_counter_urls.append(endpoint_url.replace("/v1", "") + "/utils/token_counter")
        proxy_counter_urls.append(endpoint_url.rstrip("/") + "/utils/token_counter")

    for url in proxy_counter_urls:
        try:
            payload: Dict[str, Any] = {"model": target_model, "messages": all_messages}
            if tools:
                payload["tools"] = tools
            req_data = json.dumps(payload).encode("utf-8")
            h = {"Content-Type": "application/json"}
            if api_key:
                h["Authorization"] = f"Bearer {api_key}"
            proxy_req = urllib.request.Request(url, data=req_data, headers=h)
            with urllib.request.urlopen(proxy_req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if "total_tokens" in data:
                        return {
                            "total_tokens": data["total_tokens"],
                            "source": "litellm_proxy"
                        }
        except Exception:
            continue

    # 2. Fallback to litellm.token_counter
    try:
        import litellm
        if tools:
            count = litellm.token_counter(model=target_model, messages=all_messages, tools=tools)
        else:
            count = litellm.token_counter(model=target_model, messages=all_messages)
        return {"total_tokens": count, "source": "litellm_sdk"}
    except Exception:
        total_chars = sum(len(m.get("content", "")) for m in all_messages)
        return {"total_tokens": max(1, total_chars // 4), "source": "heuristic"}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    Direct multi-turn AI Chat streaming endpoint via LiteLLM Proxy.
    Supports dynamic reasoning effort mapping, workspace file tools, and exact token/cost usage tracking.
    """
    endpoint_url = os.getenv("LITELLM_ENDPOINT_URL", "http://localhost:4000/v1")
    api_key = os.getenv("LITELLM_API_KEY", "")

    ws_display = req.workspace_dir or "./workspace"
    ws_dir = sanitize_workspace_dir(ws_display)
    os.makedirs(ws_dir, exist_ok=True)

    base_sys_prompt = req.system_prompt.strip() if req.system_prompt and req.system_prompt.strip() else "You are a senior enterprise AI assistant."
    if req.tools_enabled:
        base_sys_prompt += (
            f"\n\n[WORKSPACE CAPABILITIES]\n"
            f"Active workspace directory: '{ws_display}'.\n"
            f"You have access to specialized tools to interact with this workspace:\n"
            f"- write_workspace_file(file_path, content): Create or overwrite files.\n"
            f"- read_workspace_file(file_path): Read file contents.\n"
            f"- edit_workspace_file(file_path, target_string, replacement_string): Modify existing code or text.\n"
            f"- list_workspace_files(subpath): Explore files and folders in the workspace.\n"
            f"- delete_workspace_file(file_path): Remove files.\n"
            f"Whenever asked to create, modify, inspect, or manage files or projects, invoke the appropriate workspace tools."
        )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": base_sys_prompt}
    ]

    for m in req.messages:
        messages.append({"role": m.role, "content": m.content})

    async def chat_event_generator():
        effort_text = f" (Effort: {req.effort})" if req.effort else ""
        yield f"data: {json.dumps({'type': 'status', 'content': f'Connecting to {req.model}{effort_text}...'})}\n\n"
        await asyncio.sleep(0.01)

        last_usage = None
        try:
            generator = run_agent_turn(
                model=req.model,
                messages=messages,
                temperature=req.temperature,
                api_key=api_key or None,
                api_base=endpoint_url or None,
                tools_enabled=req.tools_enabled,
                reasoning_effort=req.effort,
                workspace_dir=ws_dir
            )

            for event in generator:
                if event.type == "chunk":
                    yield f"data: {json.dumps({'type': 'chunk', 'content': event.content})}\n\n"
                    await asyncio.sleep(0.005)
                elif event.type == "usage":
                    last_usage = event.content
                    yield f"data: {json.dumps({'type': 'usage', 'usage': event.content})}\n\n"
                elif event.type == "tool_call":
                    yield f"data: {json.dumps({'type': 'tool_call', 'content': event.content})}\n\n"
                elif event.type == "tool_result":
                    yield f"data: {json.dumps({'type': 'tool_result', 'content': event.content})}\n\n"
                elif event.type == "status":
                    yield f"data: {json.dumps({'type': 'status', 'content': event.content})}\n\n"
                elif event.type == "error":
                    yield f"data: {json.dumps({'type': 'error', 'content': event.content})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'usage': last_usage})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        chat_event_generator(),
        media_type="text/event-stream"
    )


@app.post("/api/execute/stream")
async def execute_agent_task(req: ExecutionRequest):
    """
    Executes the agent turn using LiteLLM connected directly to the LiteLLM Proxy gateway.
    Streams tokens and status as Server-Sent Events (SSE).
    """
    endpoint_url = os.getenv("LITELLM_ENDPOINT_URL", "http://localhost:4000/v1")
    api_key = os.getenv("LITELLM_API_KEY", "")

    full_prompt = req.preset_prompt
    if req.additional_instructions and req.additional_instructions.strip():
        full_prompt += f"\n\nAdditional user instructions:\n{req.additional_instructions.strip()}"

    system_instruction = (
        f"You are the SME Workflow Navigator Agent assisting with ticket {req.ticket_id} "
        f"in phase {req.stage_id}. Deliver precise, technical implementation plans, code specifications, "
        "and execution steps. Use available tools when necessary."
    )

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": full_prompt}
    ]

    async def event_generator():
        yield f"data: {json.dumps({'type': 'status', 'content': f'Initializing agent on {req.model} (Effort: {req.effort})...'})}\n\n"
        await asyncio.sleep(0.05)

        try:
            generator = run_agent_turn(
                model=req.model,
                messages=messages,
                temperature=0.7,
                api_key=api_key or None,
                api_base=endpoint_url or None,
                tools_enabled=True,
                reasoning_effort=req.effort
            )

            for event in generator:
                if event.type == "chunk":
                    yield f"data: {json.dumps({'type': 'chunk', 'content': event.content})}\n\n"
                    await asyncio.sleep(0.01)
                elif event.type == "tool_call":
                    yield f"data: {json.dumps({'type': 'tool_call', 'content': event.content})}\n\n"
                elif event.type == "tool_result":
                    yield f"data: {json.dumps({'type': 'tool_result', 'content': event.content})}\n\n"
                elif event.type == "error":
                    yield f"data: {json.dumps({'type': 'error', 'content': event.content})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'cost': '$1.246', 'session': '#1'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )

# ----------------- WORKSPACE MANAGEMENT ENDPOINTS -----------------
DEFAULT_WORKSPACES_ROOT = sanitize_workspace_dir("./workspace")
os.makedirs(DEFAULT_WORKSPACES_ROOT, exist_ok=True)


class WorkspaceCreateRequest(BaseModel):
    name: str


class WorkspaceFileWriteRequest(BaseModel):
    workspace: str = "./workspace"
    file_path: str
    content: str


@app.get("/api/workspaces")
def list_workspaces():
    """Returns available workspaces (root ./workspace and subdirectories)."""
    workspaces = [
        {
            "id": "default",
            "name": "workspace (default)",
            "path": "./workspace",
            "is_default": True
        }
    ]
    if os.path.exists(DEFAULT_WORKSPACES_ROOT):
        for entry in sorted(os.listdir(DEFAULT_WORKSPACES_ROOT)):
            full_p = os.path.join(DEFAULT_WORKSPACES_ROOT, entry)
            if os.path.isdir(full_p) and not entry.startswith("."):
                workspaces.append({
                    "id": f"ws-{entry}",
                    "name": entry,
                    "path": f"./workspace/{entry}",
                    "is_default": False
                })
    return {
        "active_workspace": "./workspace",
        "workspaces": workspaces
    }


@app.post("/api/workspaces")
def create_workspace(req: WorkspaceCreateRequest):
    """Creates a new workspace folder inside ./workspace."""
    clean_name = "".join(c for c in req.name if c.isalnum() or c in ("-", "_", " ", ".")).strip()
    if not clean_name or ".." in clean_name:
        raise HTTPException(status_code=400, detail="Invalid workspace name")
    
    target_path = sanitize_workspace_dir(os.path.join(DEFAULT_WORKSPACES_ROOT, clean_name))
    os.makedirs(target_path, exist_ok=True)
    rel_p = f"./workspace/{clean_name}"
    return {
        "status": "created",
        "id": f"ws-{clean_name}",
        "name": clean_name,
        "path": rel_p
    }


@app.get("/api/workspace/files")
def get_workspace_files(workspace: str = "./workspace"):
    """Lists all files and directories in the requested workspace."""
    abs_ws = sanitize_workspace_dir(workspace)
    if not os.path.exists(abs_ws):
        os.makedirs(abs_ws, exist_ok=True)
    
    file_list = []
    for root, dirs, files in os.walk(abs_ws):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for d in dirs:
            full_d = os.path.join(root, d)
            rel_d = os.path.relpath(full_d, abs_ws).replace("\\", "/")
            file_list.append({
                "path": rel_d,
                "name": d,
                "is_dir": True,
                "size": 0
            })
        for f in files:
            if f.startswith("."):
                continue
            full_f = os.path.join(root, f)
            rel_f = os.path.relpath(full_f, abs_ws).replace("\\", "/")
            try:
                sz = os.path.getsize(full_f)
                mtime = os.path.getmtime(full_f)
            except OSError:
                sz = 0
                mtime = 0
            file_list.append({
                "path": rel_f,
                "name": f,
                "is_dir": False,
                "size": sz,
                "mtime": mtime
            })
            
    return {
        "workspace": workspace,
        "total_files": sum(1 for item in file_list if not item["is_dir"]),
        "files": file_list
    }


@app.get("/api/workspace/file")
def get_workspace_file_content(file_path: str, workspace: str = "./workspace"):
    """Reads content of a specific file in the workspace."""
    from agent.tools import resolve_workspace_path
    try:
        full_p = resolve_workspace_path(file_path, workspace)
        if not os.path.exists(full_p):
            raise HTTPException(status_code=404, detail=f"File '{file_path}' not found")
        if os.path.isdir(full_p):
            raise HTTPException(status_code=400, detail="Cannot read a directory")
        with open(full_p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {
            "file_path": file_path,
            "content": content,
            "size": len(content.encode("utf-8"))
        }
    except ValueError as ve:
        raise HTTPException(status_code=403, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workspace/file")
def write_workspace_file_api(req: WorkspaceFileWriteRequest):
    """Directly creates or updates a file in the workspace."""
    from agent.tools import resolve_workspace_path
    try:
        full_p = resolve_workspace_path(req.file_path, req.workspace)
        os.makedirs(os.path.dirname(full_p), exist_ok=True)
        with open(full_p, "w", encoding="utf-8") as f:
            f.write(req.content)
        return {
            "status": "saved",
            "file_path": req.file_path,
            "size": len(req.content.encode("utf-8"))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/workspace/file")
def delete_workspace_file_api(file_path: str, workspace: str = "./workspace"):
    """Deletes a file from the workspace."""
    from agent.tools import resolve_workspace_path
    try:
        full_p = resolve_workspace_path(file_path, workspace)
        if os.path.exists(full_p):
            if os.path.isdir(full_p):
                import shutil
                shutil.rmtree(full_p)
            else:
                os.remove(full_p)
            return {"status": "deleted", "file_path": file_path}
        return {"status": "not_found", "file_path": file_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------- CHAT DISK PERSISTENCE -----------------
CHATS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chats")
os.makedirs(CHATS_DIR, exist_ok=True)


@app.get("/api/chats")
def list_chats():
    """Lists all chat threads saved on disk in data/chats/."""
    results = []
    if not os.path.exists(CHATS_DIR):
        return results
    for fname in os.listdir(CHATS_DIR):
        if fname.endswith(".json"):
            fpath = os.path.join(CHATS_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    results.append({
                        "id": data.get("id", fname[:-5]),
                        "title": data.get("title", "Untitled Chat"),
                        "createdAt": data.get("createdAt", ""),
                        "updatedAt": data.get("updatedAt", ""),
                        "messages_count": len(data.get("messages", [])),
                        "disk_path": f"data/chats/{fname}"
                    })
            except Exception:
                continue
    results.sort(key=lambda x: x.get("updatedAt") or x.get("createdAt") or "", reverse=True)
    return results


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str):
    """Loads a specific chat thread from disk."""
    safe_id = "".join(c for c in chat_id if c.isalnum() or c in ("-", "_"))
    fpath = os.path.join(CHATS_DIR, f"{safe_id}.json")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Chat not found on disk")
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
            data["disk_path"] = f"data/chats/{safe_id}.json"
            data.pop("abs_path", None)
            return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chats/{chat_id}")
def save_chat(chat_id: str, chat_data: Dict[str, Any]):
    """Saves or updates a chat thread on disk."""
    safe_id = "".join(c for c in chat_id if c.isalnum() or c in ("-", "_"))
    if not safe_id:
        raise HTTPException(status_code=400, detail="Invalid chat id")
    fpath = os.path.join(CHATS_DIR, f"{safe_id}.json")
    try:
        chat_data.pop("abs_path", None)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(chat_data, f, indent=2, ensure_ascii=False)
        return {
            "status": "saved",
            "id": safe_id,
            "disk_path": f"data/chats/{safe_id}.json"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str):
    """Deletes a chat thread file from disk."""
    safe_id = "".join(c for c in chat_id if c.isalnum() or c in ("-", "_"))
    fpath = os.path.join(CHATS_DIR, f"{safe_id}.json")
    if os.path.exists(fpath):
        os.remove(fpath)
        return {"status": "deleted", "id": safe_id}
    return {"status": "not_found", "id": safe_id}


# Mount dedicated frontend SPA
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host="127.0.0.1", port=8000, reload=True)
