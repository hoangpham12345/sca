import os
import datetime
import math
import urllib.request
import urllib.parse
import socket
import ipaddress
import json
import inspect
from typing import Dict, Any, Callable

# Tool registry
TOOL_REGISTRY: Dict[str, Callable] = {}
TOOL_DEFINITIONS = []

# Canonical workspace root: strictly anchored to <project_root>/workspace
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace"))
os.makedirs(WORKSPACE_ROOT, exist_ok=True)


def sanitize_workspace_dir(workspace_dir: str = "./workspace") -> str:
    """
    Sanitizes and clamps the workspace directory so that it is always strictly
    contained within the project's './workspace' root directory.
    Prevents path traversal ('..') and arbitrary filesystem access ('C:\\', '/etc').
    """
    os.makedirs(WORKSPACE_ROOT, exist_ok=True)
    if not workspace_dir or workspace_dir.strip() in ("", ".", "./"):
        return WORKSPACE_ROOT

    clean_dir = workspace_dir.strip()
    norm_slash = clean_dir.replace("\\", "/").rstrip("/")
    if norm_slash in ("workspace", "./workspace"):
        return WORKSPACE_ROOT
    if norm_slash.startswith("./workspace/"):
        sub = norm_slash[len("./workspace/"):]
        target = os.path.abspath(os.path.join(WORKSPACE_ROOT, sub))
    elif norm_slash.startswith("workspace/"):
        sub = norm_slash[len("workspace/"):]
        target = os.path.abspath(os.path.join(WORKSPACE_ROOT, sub))
    elif norm_slash.startswith(("/", "\\")) or (len(norm_slash) > 1 and norm_slash[1] == ":"):
        abs_candidate = os.path.abspath(clean_dir)
        if abs_candidate == WORKSPACE_ROOT or abs_candidate.startswith(WORKSPACE_ROOT + os.sep):
            target = abs_candidate
        else:
            target = WORKSPACE_ROOT
    else:
        target = os.path.abspath(os.path.join(WORKSPACE_ROOT, clean_dir))

    if not (target == WORKSPACE_ROOT or target.startswith(WORKSPACE_ROOT + os.sep)):
        return WORKSPACE_ROOT

    os.makedirs(target, exist_ok=True)
    return target


def register_tool(name: str, description: str, parameters: dict):
    """Decorator to register a function as an agent tool."""
    def decorator(func: Callable):
        TOOL_REGISTRY[name] = func
        TOOL_DEFINITIONS.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters
            }
        })
        return func
    return decorator


def resolve_workspace_path(file_path: str, workspace_dir: str = "./workspace") -> str:
    """Ensures file paths are safely sandboxed inside the selected workspace directory."""
    abs_ws = sanitize_workspace_dir(workspace_dir)
    os.makedirs(abs_ws, exist_ok=True)
    norm_path = os.path.normpath(file_path).lstrip("/\\")
    full_path = os.path.abspath(os.path.join(abs_ws, norm_path))
    if not (full_path == abs_ws or full_path.startswith(abs_ws + os.sep)):
        raise ValueError(f"Path '{file_path}' traverses outside the workspace directory '{abs_ws}'.")
    return full_path


@register_tool(
    name="list_workspace_files",
    description="List files and directories in the workspace. Returns relative paths, sizes, and file types.",
    parameters={
        "type": "object",
        "properties": {
            "subpath": {
                "type": "string",
                "description": "Optional relative subdirectory within the workspace (defaults to root: '')"
            }
        }
    }
)
def list_workspace_files(subpath: str = "", workspace_dir: str = "./workspace") -> str:
    """List files in the workspace directory."""
    try:
        target_dir = resolve_workspace_path(subpath, workspace_dir)
        if not os.path.exists(target_dir):
            return json.dumps({"error": f"Directory '{subpath}' does not exist in workspace."})
        
        items = []
        abs_ws = os.path.abspath(workspace_dir)
        for root, dirs, files in os.walk(target_dir):
            for d in dirs:
                full_d = os.path.join(root, d)
                rel_d = os.path.relpath(full_d, abs_ws).replace("\\", "/")
                items.append({"path": rel_d, "type": "directory", "name": d})
            for f in files:
                full_f = os.path.join(root, f)
                rel_f = os.path.relpath(full_f, abs_ws).replace("\\", "/")
                try:
                    sz = os.path.getsize(full_f)
                except OSError:
                    sz = 0
                items.append({"path": rel_f, "type": "file", "name": f, "size_bytes": sz})
        
        return json.dumps({"workspace": os.path.relpath(abs_ws), "items": items, "total_items": len(items)}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="read_workspace_file",
    description="Read the text content of a file in the workspace.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Relative path of the file to read, e.g. 'main.py' or 'src/utils.py'"
            }
        },
        "required": ["file_path"]
    }
)
def read_workspace_file(file_path: str, workspace_dir: str = "./workspace") -> str:
    """Read file contents safely from the workspace."""
    try:
        full_path = resolve_workspace_path(file_path, workspace_dir)
        if not os.path.exists(full_path):
            return f"Error: File '{file_path}' does not exist."
        if os.path.isdir(full_path):
            return f"Error: '{file_path}' is a directory, not a file."
        
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            if len(content) > 10000:
                return content[:10000] + f"\n\n...[truncated remainder of {len(content)} total characters]"
            return content
    except Exception as e:
        return f"Error reading file '{file_path}': {str(e)}"


@register_tool(
    name="write_workspace_file",
    description="Create a new file or completely overwrite an existing file in the workspace with content. Automatically creates parent directories.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Relative path of the file to write, e.g. 'app.py' or 'components/header.js'"
            },
            "content": {
                "type": "string",
                "description": "Full file content to write"
            }
        },
        "required": ["file_path", "content"]
    }
)
def write_workspace_file(file_path: str, content: str, workspace_dir: str = "./workspace") -> str:
    """Write or overwrite file in the workspace."""
    try:
        full_path = resolve_workspace_path(file_path, workspace_dir)
        parent_dir = os.path.dirname(full_path)
        os.makedirs(parent_dir, exist_ok=True)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        byte_len = len(content.encode("utf-8"))
        return f"Success: Wrote {byte_len} bytes to '{file_path}' in workspace."
    except Exception as e:
        return f"Error writing file '{file_path}': {str(e)}"


@register_tool(
    name="edit_workspace_file",
    description="Modify an existing file in the workspace by replacing target_string with replacement_string.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Relative path of the file to modify"
            },
            "target_string": {
                "type": "string",
                "description": "Exact text sequence to be replaced"
            },
            "replacement_string": {
                "type": "string",
                "description": "New text to substitute in place of target_string"
            }
        },
        "required": ["file_path", "target_string", "replacement_string"]
    }
)
def edit_workspace_file(file_path: str, target_string: str, replacement_string: str, workspace_dir: str = "./workspace") -> str:
    """Replace content in an existing file."""
    try:
        full_path = resolve_workspace_path(file_path, workspace_dir)
        if not os.path.exists(full_path):
            return f"Error: File '{file_path}' does not exist."
            
        with open(full_path, "r", encoding="utf-8") as f:
            orig = f.read()
            
        if target_string not in orig:
            return f"Error: target_string was not found in '{file_path}'. Make sure whitespace and formatting match exactly."
            
        modified = orig.replace(target_string, replacement_string, 1)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(modified)
            
        return f"Success: Replaced target_string in '{file_path}'."
    except Exception as e:
        return f"Error editing file '{file_path}': {str(e)}"


@register_tool(
    name="delete_workspace_file",
    description="Delete a file from the workspace.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Relative path of the file to delete"
            }
        },
        "required": ["file_path"]
    }
)
def delete_workspace_file(file_path: str, workspace_dir: str = "./workspace") -> str:
    """Delete a file in the workspace."""
    try:
        full_path = resolve_workspace_path(file_path, workspace_dir)
        if not os.path.exists(full_path):
            return f"Error: File '{file_path}' does not exist."
        if os.path.isdir(full_path):
            return f"Error: '{file_path}' is a directory, not a file."
        os.remove(full_path)
        return f"Success: Deleted file '{file_path}' from workspace."
    except Exception as e:
        return f"Error deleting file '{file_path}': {str(e)}"


@register_tool(
    name="calculator",
    description="Evaluate a mathematical expression. Supports standard math operations, powers, sqrt, sin, cos, etc.",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The mathematical expression to evaluate, e.g., '24 * 3.5' or 'math.sqrt(144)'"
            }
        },
        "required": ["expression"]
    }
)
def calculator(expression: str) -> str:
    """Safe evaluation of mathematical expressions."""
    allowed_names = {
        k: v for k, v in math.__dict__.items() if not k.startswith("__")
    }
    allowed_names.update({"abs": abs, "round": round, "min": min, "max": max, "sum": sum, "pow": pow})
    try:
        # Evaluate in restricted namespace
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {str(e)}"


@register_tool(
    name="get_current_datetime",
    description="Get the current date, time, and timezone information.",
    parameters={
        "type": "object",
        "properties": {
            "dummy": {
                "type": "string",
                "description": "Optional dummy parameter"
            }
        }
    }
)
def get_current_datetime(dummy: str = "") -> str:
    """Returns the current local and UTC date and time."""
    now_local = datetime.datetime.now().astimezone()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    return json.dumps({
        "local_time": now_local.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "utc_time": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "day_of_week": now_local.strftime("%A")
    })


def validate_safe_url(url: str) -> None:
    """
    Validates that a URL is safe to fetch text content from.
    Prevents Server-Side Request Forgery (SSRF) by blocking:
    - Non-HTTP/HTTPS schemes (e.g. file://, gopher://, ftp://)
    - Localhost, loopback IPs (127.0.0.1, ::1)
    - Private network subnets (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, fc00::/7)
    - Link-local and cloud metadata addresses (169.254.169.254, fe80::/10)
    - Non-standard sensitive ports
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string.")

    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Restricted URL scheme '{parsed.scheme}'. Only 'http' and 'https' are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: No hostname specified.")

    lower_host = hostname.lower()
    if lower_host in ("localhost", "127.0.0.1", "::1") or lower_host.endswith(".local") or lower_host.endswith(".internal"):
        raise ValueError(f"Access to local or private destination '{hostname}' is restricted.")

    # Restrict destination port if explicitly given
    if parsed.port and parsed.port not in (80, 443, 8080, 8443):
        raise ValueError(f"Access to non-standard port {parsed.port} is restricted.")

    # Resolve hostname to all associated IP addresses and verify none are private/loopback/link-local
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve host '{hostname}': {e}")

    for item in addr_info:
        ip_str = item[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_unspecified
                or ip.is_multicast
            ):
                raise ValueError(f"Access to private/local/link-local address ({ip}) is restricted.")
        except ValueError as ve:
            if "restricted" in str(ve):
                raise
            raise ValueError(f"Invalid resolved IP address '{ip_str}' for host '{hostname}'.")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Custom redirect handler that validates target URLs against SSRF before following."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@register_tool(
    name="fetch_web_content",
    description="Fetch text content from a public URL using HTTP GET (useful for reading documentation, API docs, or raw text files).",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch content from"
            }
        },
        "required": ["url"]
    }
)
def fetch_web_content(url: str) -> str:
    """Fetch raw text content from a web URL with SSRF protection."""
    try:
        validate_safe_url(url)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LiteLLM-Agent/1.0"}
        )
        opener = urllib.request.build_opener(SafeRedirectHandler())
        with opener.open(req, timeout=10) as response:
            content = response.read().decode("utf-8", errors="replace")
            # Limit returned length to prevent context explosion
            if len(content) > 4000:
                return content[:4000] + "\n...[truncated remainder]"
            return content
    except Exception as e:
        return f"Error fetching URL: {str(e)}"


def execute_tool_call(tool_name: str, arguments: dict, workspace_dir: str = "./workspace") -> str:
    """Execute a registered tool by name with provided arguments, injecting workspace_dir if applicable."""
    func = TOOL_REGISTRY.get(tool_name)
    if not func:
        return f"Error: Tool '{tool_name}' not found."
    try:
        call_args = dict(arguments)
        sig = inspect.signature(func)
        if "workspace_dir" in sig.parameters and "workspace_dir" not in call_args:
            call_args["workspace_dir"] = workspace_dir
        return str(func(**call_args))
    except Exception as e:
        return f"Error running '{tool_name}': {str(e)}"
