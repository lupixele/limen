"""Autonomous Decide-Act-Observe Agent Loop with Function Calling, Identity, and Provenance."""
import asyncio
import json
import re
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx

from agent.prompt import build_system_prompt
from core.tools import ToolRegistry, ToolResult


def _extract_plan_artifact(text: str) -> Optional[Dict[str, Any]]:
    """Inspects text for an embedded generalized plan_artifact table."""
    if not text:
        return None

    # Search for markdown json fences
    matches = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    for block in matches:
        try:
            data = json.loads(block.strip())
            if isinstance(data, dict) and "columns" in data and "rows" in data:
                if isinstance(data["columns"], list) and isinstance(data["rows"], list):
                    return {"columns": data["columns"], "rows": data["rows"]}
        except Exception:
            continue

    # Fallback search for bare json with columns and rows
    try:
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1 and last > first:
            data = json.loads(text[first : last + 1])
            if isinstance(data, dict) and "columns" in data and "rows" in data:
                if isinstance(data["columns"], list) and isinstance(data["rows"], list):
                    return {"columns": data["columns"], "rows": data["rows"]}
    except Exception:
        pass

    return None


def _resolve_endpoint(base_url: str) -> str:
    url = base_url.rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


async def run_agent_loop(
    instruction: str,
    registry: ToolRegistry,
    provider_url: str,
    api_key: str,
    model: str,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    prior_turns: Optional[List[Dict[str, Any]]] = None,
    max_steps: int = 8,
    timeout: float = 60.0,
    context: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Executes the autonomous agent loop.
    Emits structured event dicts: tool_call, plan_artifact, final_answer, done, error
    with explicit session_id, run_id, and invocation_id identities.
    Enforces trusted session tool binding: foreign session IDs cannot be accessed.
    """
    endpoint = _resolve_endpoint(provider_url)
    headers = {
        "Content-Type": "application/json",
    }
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    tool_schemas = registry.get_schemas()
    system_prompt = build_system_prompt(tool_schemas, context=context)

    session_tag = session_id or f"sess_{uuid.uuid4().hex[:8]}"
    active_run_id = run_id or f"run_{uuid.uuid4().hex[:8]}"

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt}
    ]

    # Incorporate conversational history from prior turns if provided
    if prior_turns:
        for pt in prior_turns[-6:]:  # Keep up to last 6 turns for context
            role = pt.get("role")
            content = pt.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": instruction})
    converged = False

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for step in range(1, max_steps + 1):
                payload: Dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2,
                }
                if tool_schemas:
                    payload["tools"] = tool_schemas
                    payload["tool_choice"] = "auto"

                try:
                    resp = await client.post(endpoint, headers=headers, json=payload)
                except asyncio.CancelledError:
                    raise
                except Exception as net_err:
                    yield {
                        "type": "error",
                        "session_id": session_tag,
                        "run_id": active_run_id,
                        "step": step,
                        "message": f"Network error contacting LLM provider: {str(net_err)}",
                    }
                    yield {
                        "type": "done",
                        "session_id": session_tag,
                        "run_id": active_run_id,
                        "converged": False,
                    }
                    return

                if resp.status_code != 200:
                    yield {
                        "type": "error",
                        "session_id": session_tag,
                        "run_id": active_run_id,
                        "step": step,
                        "message": f"LLM provider error (status {resp.status_code}): {resp.text}",
                    }
                    yield {
                        "type": "done",
                        "session_id": session_tag,
                        "run_id": active_run_id,
                        "converged": False,
                    }
                    return

                try:
                    resp_json = resp.json()
                except Exception as parse_err:
                    yield {
                        "type": "error",
                        "session_id": session_tag,
                        "run_id": active_run_id,
                        "step": step,
                        "message": f"Invalid JSON response from LLM provider: {str(parse_err)}",
                    }
                    yield {
                        "type": "done",
                        "session_id": session_tag,
                        "run_id": active_run_id,
                        "converged": False,
                    }
                    return

                choices = resp_json.get("choices", [])
                if not choices:
                    yield {
                        "type": "error",
                        "session_id": session_tag,
                        "run_id": active_run_id,
                        "step": step,
                        "message": "LLM response contained no choices.",
                    }
                    yield {
                        "type": "done",
                        "session_id": session_tag,
                        "run_id": active_run_id,
                        "converged": False,
                    }
                    return

                choice = choices[0]
                message = choice.get("message", {})
                content = message.get("content") or ""
                reasoning = message.get("reasoning") or message.get("thinking") or ""
                tool_calls = message.get("tool_calls") or []

                # Emit thoughts if present
                if reasoning:
                    yield {
                        "type": "thought",
                        "session_id": session_tag,
                        "run_id": active_run_id,
                        "step": step,
                        "content": reasoning,
                    }

                # If the model requested tool calls
                if tool_calls:
                    messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    })

                    for call in tool_calls:
                        call_id = call.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                        invocation_id = f"inv_{call_id}"
                        fn = call.get("function", {})
                        tool_name = fn.get("name", "")
                        raw_args = fn.get("arguments", "{}")

                        if isinstance(raw_args, str):
                            try:
                                args = json.loads(raw_args)
                            except Exception:
                                args = {"raw": raw_args}
                        elif isinstance(raw_args, dict):
                            args = dict(raw_args)
                        else:
                            args = {}

                        # Trusted session binding: force session_id to session_tag.
                        # Untrusted model arguments must not access or corrupt another session.
                        if session_tag:
                            args["session_id"] = session_tag

                        # 1. Emit tool_call running with explicit invocation_id
                        yield {
                            "type": "tool_call",
                            "session_id": session_tag,
                            "run_id": active_run_id,
                            "invocation_id": invocation_id,
                            "step": step,
                            "tool_name": tool_name,
                            "status": "running",
                            "args": args,
                            "result_summary": "",
                        }

                        # 2. Execute tool via registry
                        tool_result: ToolResult = await registry.run_tool(tool_name, **args)

                        # 3. Check for tool-produced tabular artifact
                        if tool_result.artifact and isinstance(tool_result.artifact, dict):
                            cols = tool_result.artifact.get("columns")
                            rows = tool_result.artifact.get("rows")
                            title = tool_result.artifact.get("title", f"{tool_name} Result")
                            if isinstance(cols, list) and isinstance(rows, list):
                                yield {
                                    "type": "plan_artifact",
                                    "session_id": session_tag,
                                    "run_id": active_run_id,
                                    "invocation_id": invocation_id,
                                    "title": title,
                                    "columns": cols,
                                    "rows": rows,
                                }

                        # 4. Emit tool_call result with full details and summary
                        llm_content = tool_result.to_llm_content()
                        summary = (llm_content[:197] + "...") if len(llm_content) > 200 else llm_content
                        yield {
                            "type": "tool_call",
                            "session_id": session_tag,
                            "run_id": active_run_id,
                            "invocation_id": invocation_id,
                            "step": step,
                            "tool_name": tool_name,
                            "status": "success" if tool_result.success else "error",
                            "args": args,
                            "result_summary": summary,
                            "output": tool_result.output,
                            "artifact": tool_result.artifact,
                        }

                        # 5. Append role: tool message to history
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": tool_name,
                            "content": llm_content,
                        })

                    # Proceed to next step to let model observe results
                    continue

                # If no tool calls, this is the final answer!
                converged = True
                artifact = _extract_plan_artifact(content)
                if artifact:
                    yield {
                        "type": "plan_artifact",
                        "session_id": session_tag,
                        "run_id": active_run_id,
                        "invocation_id": f"inv_art_{active_run_id}",
                        "columns": artifact["columns"],
                        "rows": artifact["rows"],
                    }

                yield {
                    "type": "final_answer",
                    "session_id": session_tag,
                    "run_id": active_run_id,
                    "step": step,
                    "content": content,
                    "converged": True,
                }
                yield {
                    "type": "done",
                    "session_id": session_tag,
                    "run_id": active_run_id,
                    "converged": True,
                }
                return

            # If loop exited without converging
            if not converged:
                yield {
                    "type": "final_answer",
                    "session_id": session_tag,
                    "run_id": active_run_id,
                    "step": max_steps,
                    "content": f"Agent reached maximum execution steps ({max_steps}) without fully completing.",
                    "converged": False,
                }
                yield {
                    "type": "done",
                    "session_id": session_tag,
                    "run_id": active_run_id,
                    "converged": False,
                }
    except asyncio.CancelledError:
        yield {
            "type": "error",
            "session_id": session_tag,
            "run_id": active_run_id,
            "message": "Agent run execution was cancelled.",
        }
        yield {
            "type": "done",
            "session_id": session_tag,
            "run_id": active_run_id,
            "converged": False,
            "cancelled": True,
        }
        raise
