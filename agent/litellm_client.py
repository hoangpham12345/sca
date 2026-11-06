import os
import json
from typing import List, Dict, Any, Generator, Optional, Tuple
import litellm
from agent.tools import TOOL_DEFINITIONS, execute_tool_call

# Suppress telemetry logs
litellm.telemetry = False

class AgentEvent:
    def __init__(self, event_type: str, content: Any = None):
        self.type = event_type  # "chunk", "tool_call", "tool_result", "status", "error"
        self.content = content


def get_sandbox(sandbox_type: str, workspace_dir: str = "./workspace"):
    """
    Creates a sandbox instance based on LiteLLM's sandbox specification.
    Supports 'local' (host subprocess in workspace directory) and 'docker'.
    """
    if sandbox_type == "none" or not sandbox_type:
        return None
        
    abs_workspace = os.path.abspath(workspace_dir)
    os.makedirs(abs_workspace, exist_ok=True)
    
    try:
        from litellm import sandbox
        if sandbox_type == "local":
            return sandbox.local(abs_workspace)
        elif sandbox_type == "docker":
            return sandbox.docker("python:3.13", mounts={abs_workspace: "/workspace"}, workdir="/workspace")
    except Exception as e:
        raise RuntimeError(f"Failed to initialize '{sandbox_type}' sandbox: {str(e)}")
        
    return None


def normalize_model_for_proxy(model: str, api_base: Optional[str]) -> str:
    """
    If routing via an OpenAI-compatible proxy,
    prefix model with 'openai/' if not already prefixed, ensuring LiteLLM
    treats the endpoint as an OpenAI-compatible proxy and routes correctly.
    """
    if api_base and ("/v1" in api_base or "proxy" in api_base or ":4000" in api_base):
        if not (model.startswith("openai/") or model.startswith("custom/")):
            return f"openai/{model}"
    return model


def run_agent_turn(
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    tools_enabled: bool = True,
    max_tool_iterations: int = 5,
    reasoning_effort: Optional[str] = None,
    workspace_dir: str = "./workspace"
) -> Generator[AgentEvent, None, List[Dict[str, Any]]]:
    """
    Executes an interactive agent turn using LiteLLM.
    Handles tool-calling loops and yields streaming text chunks or tool status updates.
    """
    current_messages = list(messages)
    target_model = normalize_model_for_proxy(model, api_base)
    kwargs: Dict[str, Any] = {
        "model": target_model,
        "temperature": temperature,
    }
    if reasoning_effort and reasoning_effort.lower() in ("low", "medium", "high"):
        kwargs["reasoning_effort"] = reasoning_effort.lower()
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base

    tools = TOOL_DEFINITIONS if tools_enabled else None

    iteration = 0
    while iteration < max_tool_iterations:
        iteration += 1
        call_kwargs = dict(kwargs)
        call_kwargs["messages"] = current_messages
        if tools:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"

        try:
            if tools:
                response = litellm.completion(**call_kwargs)
                response_msg = response.choices[0].message
                tool_calls = getattr(response_msg, "tool_calls", None)

                # Capture usage metrics for tool turns
                resp_usage = getattr(response, "usage", None)
                if resp_usage:
                    cost_val = getattr(resp_usage, "cost", None)
                    if cost_val is None:
                        try:
                            cost_val = litellm.completion_cost(completion_response=response)
                        except Exception:
                            cost_val = None

                    cached_val = 0
                    pt_details = getattr(resp_usage, "prompt_tokens_details", None)
                    if pt_details:
                        if isinstance(pt_details, dict):
                            cached_val = pt_details.get("cached_tokens", 0) or 0
                        else:
                            cached_val = getattr(pt_details, "cached_tokens", 0) or 0
                    if not cached_val and hasattr(resp_usage, "cache_read_input_tokens"):
                        cached_val = getattr(resp_usage, "cache_read_input_tokens", 0) or 0

                    turn_usage = {
                        "prompt_tokens": getattr(resp_usage, "prompt_tokens", 0) or 0,
                        "cached_tokens": cached_val,
                        "completion_tokens": getattr(resp_usage, "completion_tokens", 0) or 0,
                        "total_tokens": getattr(resp_usage, "total_tokens", 0) or 0,
                        "cost": cost_val
                    }
                    yield AgentEvent("usage", turn_usage)

                if tool_calls:
                    assistant_msg = {
                        "role": "assistant",
                        "content": response_msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            }
                            for tc in tool_calls
                        ]
                    }
                    current_messages.append(assistant_msg)

                    for tc in tool_calls:
                        func_name = tc.function.name
                        try:
                            args = json.loads(tc.function.arguments)
                        except Exception:
                            args = {"raw": tc.function.arguments}

                        yield AgentEvent("tool_call", {
                            "tool_name": func_name,
                            "arguments": args,
                            "id": tc.id
                        })

                        result = execute_tool_call(func_name, args, workspace_dir=workspace_dir)

                        yield AgentEvent("tool_result", {
                            "tool_name": func_name,
                            "result": result,
                            "id": tc.id
                        })

                        current_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": func_name,
                            "content": result
                        })

                    continue

                else:
                    final_content = response_msg.content or ""
                    chunk_size = 4
                    for i in range(0, len(final_content), chunk_size):
                        yield AgentEvent("chunk", final_content[i:i + chunk_size])

                    current_messages.append({
                        "role": "assistant",
                        "content": final_content
                    })
                    return current_messages

            else:
                call_kwargs["stream"] = True
                call_kwargs["stream_options"] = {"include_usage": True}
                stream_resp = litellm.completion(**call_kwargs)
                full_text = []
                turn_usage = None

                for chunk in stream_resp:
                    chunk_usage = getattr(chunk, "usage", None)
                    if chunk_usage:
                        cost_val = getattr(chunk_usage, "cost", None)
                        if cost_val is None:
                            try:
                                cost_val = litellm.completion_cost(completion_response=chunk)
                            except Exception:
                                cost_val = None

                        cached_val = 0
                        pt_details = getattr(chunk_usage, "prompt_tokens_details", None)
                        if pt_details:
                            if isinstance(pt_details, dict):
                                cached_val = pt_details.get("cached_tokens", 0) or 0
                            else:
                                cached_val = getattr(pt_details, "cached_tokens", 0) or 0
                        if not cached_val and hasattr(chunk_usage, "cache_read_input_tokens"):
                            cached_val = getattr(chunk_usage, "cache_read_input_tokens", 0) or 0

                        turn_usage = {
                            "prompt_tokens": getattr(chunk_usage, "prompt_tokens", 0) or 0,
                            "cached_tokens": cached_val,
                            "completion_tokens": getattr(chunk_usage, "completion_tokens", 0) or 0,
                            "total_tokens": getattr(chunk_usage, "total_tokens", 0) or 0,
                            "cost": cost_val
                        }

                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        content = getattr(delta, "content", "") or ""
                        if content:
                            full_text.append(content)
                            yield AgentEvent("chunk", content)

                if turn_usage:
                    yield AgentEvent("usage", turn_usage)

                current_messages.append({
                    "role": "assistant",
                    "content": "".join(full_text)
                })
                return current_messages

        except Exception as e:
            yield AgentEvent("error", str(e))
            return current_messages

    return current_messages


def run_deepagents_turn(
    prompt: str,
    model: str,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    sandbox_type: str = "local",
    workspace_dir: str = "./workspace",
    recursion_limit: int = 50
) -> Generator[AgentEvent, None, str]:
    """
    Executes a task turn using LiteLLM's Harness.DEEPAGENTS with local sandbox support.
    """
    try:
        from litellm import Harness, DeepAgentsOptions
    except ImportError as e:
        yield AgentEvent("error", f"LiteLLM DeepAgents harness is not installed: {str(e)}. Ensure 'deepagents' and 'langchain-litellm' are installed.")
        return ""

    yield AgentEvent("status", f"Configuring {sandbox_type} sandbox in '{workspace_dir}'...")
    try:
        sb = get_sandbox(sandbox_type, workspace_dir)
    except Exception as e:
        yield AgentEvent("error", f"Sandbox error: {str(e)}")
        return ""

    target_model = normalize_model_for_proxy(model, api_base)
    yield AgentEvent("status", f"Invoking litellm.agent(Harness.DEEPAGENTS) on model '{target_model}'...")

    agent_kwargs: Dict[str, Any] = {
        "model": target_model,
        "options": DeepAgentsOptions(recursion_limit=recursion_limit)
    }
    if api_key:
        agent_kwargs["api_key"] = api_key
    if api_base:
        agent_kwargs["api_base"] = api_base
    if sb:
        agent_kwargs["sandbox"] = sb

    try:
        result = litellm.agent(
            Harness.DEEPAGENTS,
            prompt,
            **agent_kwargs
        )
        output_text = str(result)
        # Stream result to UI
        chunk_size = 8
        for i in range(0, len(output_text), chunk_size):
            yield AgentEvent("chunk", output_text[i:i + chunk_size])
        return output_text

    except Exception as e:
        yield AgentEvent("error", f"DeepAgents execution error: {str(e)}")
        return ""
