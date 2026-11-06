import os
import json
import urllib.request
import yaml
import streamlit as st
from dotenv import load_dotenv

# Load environment variables from .env file if available
load_dotenv()

from agent.litellm_client import run_agent_turn, run_deepagents_turn
from agent.tools import TOOL_DEFINITIONS
from agent.session_manager import (
    list_saved_sessions,
    save_session,
    load_session,
    delete_session
)

ALLOWED_MODELS_PATH = os.path.join(os.path.dirname(__file__), "allowed_models.yaml")

def load_allowed_models(config_path: str = ALLOWED_MODELS_PATH) -> list:
    """Reads the authorized model catalogue from allowed_models.yaml."""
    if not os.path.exists(config_path):
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            models = yaml.safe_load(f)
            return [m for m in models if isinstance(m, str) and m.strip()]
    except Exception as e:
        st.warning(f"Error loading allowed_models.yaml: {str(e)}")
        return []

def fetch_and_filter_models(base_url: str, api_key: str = "", config_path: str = ALLOWED_MODELS_PATH) -> list:
    """
    Queries the remote LiteLLM Proxy's GET /models endpoint and filters
    the returned list strictly against the enterprise-approved models in allowed_models.yaml.
    """
    allowed = load_allowed_models(config_path)
    if not base_url:
        return allowed

    url = f"{base_url.rstrip('/')}/models"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            live_models = []
            if "data" in payload and isinstance(payload["data"], list):
                for item in payload["data"]:
                    if isinstance(item, dict) and "id" in item:
                        live_models.append(item["id"])

            if live_models and allowed:
                # Intersect to ensure only approved models available on the proxy are shown
                filtered = [m for m in allowed if m in live_models]
                return filtered if filtered else allowed
            elif live_models:
                return live_models
    except Exception:
        pass

    return allowed


# Page Configuration
st.set_page_config(
    page_title="LiteLLM Agent UI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------- SESSION STATE INITIALIZATION -----------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_name" not in st.session_state:
    st.session_state.session_name = "New Conversation"

if "authorized_models" not in st.session_state:
    st.session_state.authorized_models = []


# ================================================================
# SINGLE LEFT SIDEBAR: SESSIONS & LITELLM PROXY SETTINGS
# ================================================================
with st.sidebar:
    st.title("📁 Chat Sessions")
    
    # 1. New Chat Button
    if st.button("➕ Start New Chat", use_container_width=True, type="primary"):
        st.session_state.messages = []
        st.session_state.session_name = "New Conversation"
        st.rerun()

    # 2. Current Session Management
    session_title = st.text_input("Session Title", value=st.session_state.session_name)
    col_save, col_export = st.columns(2)
    with col_save:
        save_clicked = st.button("Save Chat", use_container_width=True)
    with col_export:
        if st.session_state.messages:
            chat_export_json = json.dumps(st.session_state.messages, indent=2, ensure_ascii=False)
            st.download_button(
                label="Export JSON",
                data=chat_export_json,
                file_name=f"{st.session_state.session_name.replace(' ', '_')}.json",
                mime="application/json",
                use_container_width=True
            )
        else:
            st.button("Export JSON", disabled=True, use_container_width=True)

    # 3. Saved Conversations List
    st.subheader("📜 Saved Conversations")
    saved_files = list_saved_sessions()
    if not saved_files:
        st.caption("No saved conversations yet.")
    else:
        for fname in saved_files:
            clean_display_name = fname.replace(".json", "").replace("_", " ")
            is_active = (fname.replace(".json", "") == st.session_state.session_name.replace(" ", "_"))
            
            with st.container():
                c_name, c_load, c_del = st.columns([3, 1.2, 0.8])
                with c_name:
                    badge = "🔹 " if is_active else ""
                    st.write(f"{badge}**{clean_display_name}**")
                with c_load:
                    if st.button("Load", key=f"load_{fname}", use_container_width=True):
                        loaded = load_session(fname)
                        st.session_state.messages = loaded.get("messages", [])
                        st.session_state.session_name = loaded.get("title", clean_display_name)
                        st.rerun()
                with c_del:
                    if st.button("🗑️", key=f"del_{fname}", help=f"Delete {fname}"):
                        delete_session(fname)
                        st.rerun()

    st.markdown("---")

    # 4. Enterprise LiteLLM Proxy Endpoint
    st.subheader("⚙️ LiteLLM Gateway")

    target_base_url = st.text_input(
        "Gateway Endpoint URL",
        value=os.getenv("LITELLM_ENDPOINT_URL", "http://localhost:4000/v1"),
        help="Connects directly to the hosted LiteLLM Proxy."
    )

    api_key_override = st.text_input(
        "API Key",
        value=os.getenv("LITELLM_API_KEY", ""),
        type="password",
        help="Bearer token for the LiteLLM Proxy gateway."
    )

    # Fetch and filter authorized models on initial load
    if not st.session_state.authorized_models:
        st.session_state.authorized_models = fetch_and_filter_models(
            target_base_url,
            api_key_override.strip()
        )

    available_models = st.session_state.authorized_models

    # 5. Model Selection (Restricted strictly to authorized models)
    st.subheader("Authorized Model")
    if available_models:
        c_mod, c_refresh = st.columns([3.2, 0.8])
        with c_mod:
            model_id = st.selectbox(
                "Select Model",
                available_models,
                index=0,
                help="Only enterprise-approved models from allowed_models.yaml are shown."
            )
        with c_refresh:
            st.write("")
            if st.button("🔄", help="Sync models with LiteLLM proxy and filter by allowed_models.yaml"):
                with st.spinner("Syncing models..."):
                    st.session_state.authorized_models = fetch_and_filter_models(
                        target_base_url,
                        api_key_override.strip()
                    )
                    st.rerun()
    else:
        st.warning("No models found in allowed_models.yaml.")
        model_id = st.text_input("Model Identifier", value="google/gemini-3.8-flash")

    # 6. Execution Engine
    agent_mode = st.radio(
        "Agent Engine",
        ["Interactive Chat (Streaming)", "DeepAgents (Task Planning)"],
        index=0
    )

    # 7. Advanced Parameters
    with st.expander("🛠️ Advanced Settings", expanded=False):
        temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.05)
        system_prompt = st.text_area(
            "System Prompt",
            value="You are an intelligent, helpful AI assistant equipped with specialized tools.",
            height=80
        )
        enable_tools = st.checkbox("Enable Tools", value=True)
        sandbox_choice = "local"
        sandbox_dir = "./workspace"
        recursion_limit = 25

    if "temperature" not in locals():
        temperature = 0.7
        system_prompt = "You are an intelligent, helpful AI assistant."
        enable_tools = True
        sandbox_choice = "local"
        sandbox_dir = "./workspace"
        recursion_limit = 25

    # Handle Save Chat Session
    if save_clicked:
        st.session_state.session_name = session_title
        settings = {
            "model": model_id,
            "api_base": target_base_url,
            "temperature": temperature,
            "system_prompt": system_prompt,
            "tools_enabled": enable_tools
        }
        saved_file = save_session(session_title, st.session_state.messages, settings)
        st.sidebar.success("Session saved!")
        st.rerun()


# ================================================================
# MAIN PAGE: FULL-WIDTH CLEAN CHAT CANVAS
# ================================================================
st.title("🤖 LiteLLM Agent UI")
endpoint_label = target_base_url.strip() if target_base_url.strip() else "LiteLLM Gateway"
st.caption(f"Active Model: `{model_id}` | Endpoint: `{endpoint_label}` | Engine: `{agent_mode.split(' ')[0]}`")

# Render previous messages
for msg in st.session_state.messages:
    role = msg.get("role")
    
    if role == "user":
        with st.chat_message("user"):
            st.markdown(msg.get("content", ""))
            
    elif role == "assistant":
        with st.chat_message("assistant"):
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    with st.expander(f"🛠️ Executed Tool: `{fn.get('name')}`", expanded=False):
                        st.json(fn.get("arguments"))
            if msg.get("content"):
                st.markdown(msg.get("content"))
                
    elif role == "tool":
        with st.expander(f"📥 Tool Output (`{msg.get('name', 'tool')}`)", expanded=False):
            st.code(msg.get("content", ""), language="text")

# User Input Handling
user_input = st.chat_input("Type your message or task description here...")

if user_input:
    # 1. Display user prompt immediately
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    # Prepare message payload including system prompt
    api_messages = []
    if system_prompt.strip():
        api_messages.append({"role": "system", "content": system_prompt.strip()})
    api_messages.extend(st.session_state.messages)

    # 2. Assistant response container
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response_text = ""

        clean_api_key = api_key_override.strip() or None
        clean_api_base = target_base_url.strip() or None

        # Mode A: DeepAgents Harness
        if "DeepAgents" in agent_mode:
            status_box = st.status("🧠 DeepAgents Planning & Executing...", expanded=True)
            
            try:
                stream = run_deepagents_turn(
                    prompt=user_input,
                    model=model_id,
                    api_key=clean_api_key,
                    api_base=clean_api_base,
                    sandbox_type=sandbox_choice,
                    workspace_dir=sandbox_dir,
                    recursion_limit=recursion_limit
                )
                for event in stream:
                    if event.type == "status":
                        status_box.write(f"ℹ️ {event.content}")
                    elif event.type == "chunk":
                        full_response_text += event.content
                        response_placeholder.markdown(full_response_text + "▌")
                    elif event.type == "error":
                        status_box.update(label="❌ DeepAgents Encountered an Error", state="error")
                        st.error(event.content)
                        full_response_text += f"\n\n*[Error: {event.content}]*"

                status_box.update(label="✅ DeepAgents Run Complete", state="complete", expanded=False)
                response_placeholder.markdown(full_response_text)
                
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response_text
                })

            except Exception as e:
                st.error(f"Error during DeepAgents run: {str(e)}")

        # Mode B: Interactive Chat Agent (Streaming + Tools)
        else:
            try:
                agent_stream = run_agent_turn(
                    model=model_id,
                    messages=api_messages,
                    temperature=temperature,
                    api_key=clean_api_key,
                    api_base=clean_api_base,
                    tools_enabled=enable_tools
                )

                for event in agent_stream:
                    if event.type == "tool_call":
                        tool_info = event.content
                        current_status = st.status(f"🛠️ Calling `{tool_info['tool_name']}`...", expanded=True)
                        current_status.write("**Arguments:**")
                        current_status.json(tool_info["arguments"])

                    elif event.type == "tool_result":
                        tool_res = event.content
                        if "current_status" in locals() and current_status:
                            current_status.write("**Result:**")
                            current_status.code(str(tool_res["result"]))
                            current_status.update(label=f"✅ Tool `{tool_res['tool_name']}` finished", state="complete", expanded=False)

                    elif event.type == "chunk":
                        full_response_text += event.content
                        response_placeholder.markdown(full_response_text + "▌")

                    elif event.type == "error":
                        st.error(f"LiteLLM Error: {event.content}")
                        full_response_text += f"\n\n*[Error: {event.content}]*"

                response_placeholder.markdown(full_response_text)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response_text
                })

            except Exception as e:
                st.error(f"An unexpected error occurred: {str(e)}")
