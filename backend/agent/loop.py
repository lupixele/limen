"""Autonomous Decide-Act-Observe Agent Loop with Function Calling."""
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
    return f"{url}/chat/completions"


async def run_agent_loop(
    instruction: str,
    registry: ToolRegistry,
    provider_url: str,
    api_key: str,
    model: str,
    session_id: Optional[str] = None,
    max_steps: int = 8,
    timeout: float = 60.0,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Executes the autonomous agent loop.
    Emits structured event dicts: tool_call, plan_artifact, final_answer, done, error.
    """
    endpoint = _resolve_endpoint(provider_url)
    headers = {
        "Content-Type": "application/json",
    }
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    tool_schemas = registry.get_schemas()
    system_prompt = build_system_prompt(tool_schemas)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruction},
    ]

    session_tag = session_id or f"sess_{uuid.uuid4().hex[:8]}"
    converged = False

    async with httpx.AsyncClient(timeout=timeout) as client:
        for step in range(1, max_steps + 1):
            payload: Dict[str, Any] = {
                "model": model,
                "messages": messages,
            }
            if tool_schemas:
                payload["tools"] = tool_schemas
                payload["tool_choice"] = "auto"

            try:
                resp = await client.post(endpoint, headers=headers, json=payload)
            except Exception as net_err:
                yield {
                    "type": "error",
                    "step": step,
                    "message": f"Network error contacting LLM provider: {str(net_err)}",
                }
                yield {"type": "done", "session_id": session_tag, "converged": False}
                return

            if resp.status_code != 200:
                yield {
                    "type": "error",
                    "step": step,
                    "message": f"LLM provider error (status {resp.status_code}): {resp.text}",
                }
                yield {"type": "done", "session_id": session_tag, "converged": False}
                return

            try:
                resp_json = resp.json()
            except Exception as parse_err:
                yield {
                    "type": "error",
                    "step": step,
                    "message": f"Failed to parse JSON response from LLM provider: {str(parse_err)}",
                }
                yield {"type": "done", "session_id": session_tag, "converged": False}
                return

            choices = resp_json.get("choices", [])
            if not choices:
                yield {
                    "type": "error",
                    "step": step,
                    "message": "LLM response contained no choices.",
                }
                yield {"type": "done", "session_id": session_tag, "converged": False}
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
                    "step": step,
                    "content": reasoning,
                }

            # If the model requested tool calls
            if tool_calls:
                # Add assistant message with tool calls to history
                messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls,
                })

                for call in tool_calls:
                    call_id = call.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                    fn = call.get("function", {})
                    tool_name = fn.get("name", "")
                    raw_args = fn.get("arguments", "{}")

                    if isinstance(raw_args, str):
                        try:
                            args = json.loads(raw_args)
                        except Exception:
                            args = {"raw": raw_args}
                    elif isinstance(raw_args, dict):
                        args = raw_args
                    else:
                        args = {}

                    # 1. Emit tool_call running
                    yield {
                        "type": "tool_call",
                        "step": step,
                        "tool_name": tool_name,
                        "status": "running",
                        "args": args,
                        "result_summary": "",
                    }

                    # 2. Execute tool via registry
                    tool_result: ToolResult = await registry.run_tool(tool_name, **args)

                    # 3. Check for tool-produced artifact
                    if tool_result.artifact and isinstance(tool_result.artifact, dict):
                        cols = tool_result.artifact.get("columns")
                        rows = tool_result.artifact.get("rows")
                        if isinstance(cols, list) and isinstance(rows, list):
                            yield {
                                "type": "plan_artifact",
                                "columns": cols,
                                "rows": rows,
                            }

                    # 4. Emit tool_call result
                    llm_content = tool_result.to_llm_content()
                    summary = (llm_content[:197] + "...") if len(llm_content) > 200 else llm_content
                    yield {
                        "type": "tool_call",
                        "step": step,
                        "tool_name": tool_name,
                        "status": "success" if tool_result.success else "error",
                        "args": args,
                        "result_summary": summary,
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
                    "columns": artifact["columns"],
                    "rows": artifact["rows"],
                }

            yield {
                "type": "final_answer",
                "step": step,
                "content": content,
                "converged": True,
            }
            yield {
                "type": "done",
                "session_id": session_tag,
                "converged": True,
            }
            return

        # If loop exited without converging
        if not converged:
            yield {
                "type": "final_answer",
                "step": max_steps,
                "content": f"Agent reached maximum execution steps ({max_steps}) without reaching a final conclusion.",
                "converged": False,
            }
            yield {
                "type": "done",
                "session_id": session_tag,
                "converged": False,
            }
