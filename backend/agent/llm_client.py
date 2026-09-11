"""Universal OpenAI-compatible client with live token and reasoning streaming support."""
import json
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx

from agent.prompt import SYSTEM_PROMPT, build_user_prompt


def extract_json(raw_text: str) -> Dict[str, Any]:
    """Robustly extracts JSON from raw LLM output even if surrounded by markdown or commentary."""
    text = raw_text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace : last_brace + 1])
        except Exception:
            pass

    raise ValueError(f"Could not parse valid JSON from LLM response:\n{text[:500]}")


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        url = base_url.rstrip("/")
        self.base_url = url
        self.api_key = api_key or ""

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"
        return headers

    def _get_endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    async def test_connection(self) -> Dict[str, Any]:
        """Pings provider models endpoint to check connectivity."""
        headers = self._get_headers()
        models_url = self.base_url
        if not models_url.endswith("/v1") and not models_url.endswith("/models"):
            models_url = f"{models_url}/v1/models"
        elif models_url.endswith("/v1"):
            models_url = f"{models_url}/models"

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.get(models_url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    model_ids = []
                    if "data" in data and isinstance(data["data"], list):
                        model_ids = [m.get("id") for m in data["data"] if m.get("id")]
                    return {
                        "ok": True,
                        "status": 200,
                        "message": "Connection successful!",
                        "discovered_models": model_ids[:20]
                    }
                else:
                    return {
                        "ok": False,
                        "status": res.status_code,
                        "message": f"Server status {res.status_code}: {res.text[:200]}"
                    }
            except Exception as e:
                return {
                    "ok": False,
                    "status": 0,
                    "message": f"Connection failed: {str(e)}"
                }

    async def stream_plan_generation(
        self,
        model: str,
        files: List[Dict[str, Any]],
        user_instruction: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        timeout: float = 120.0,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streams live reasoning and content deltas via SSE from the LLM provider.
        Handles both explicit `reasoning_content` (DeepSeek-R1 / Qwen) and inline `<think>...</think>` tags.
        """
        endpoint = self._get_endpoint()
        headers = self._get_headers()
        user_content = build_user_prompt(files, user_instruction)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if conversation_history:
            for turn in conversation_history[-6:]:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
        }

        full_content_chunks: List[str] = []
        full_thought_chunks: List[str] = []
        inside_think_tag = False
        buffer = ""

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    err_text = await response.aread()
                    raise RuntimeError(f"LLM Stream failed ({response.status_code}): {err_text.decode('utf-8', errors='ignore')}")

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                        except Exception:
                            continue

                        choices = data.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})

                        # 1. Check for dedicated reasoning_content (DeepSeek-R1, Qwen 2.5)
                        reasoning_delta = delta.get("reasoning_content") or delta.get("thought")
                        if reasoning_delta:
                            full_thought_chunks.append(reasoning_delta)
                            yield {"type": "thought", "text": reasoning_delta}

                        # 2. Check main content
                        content_delta = delta.get("content")
                        if content_delta:
                            buffer += content_delta

                            # Handle inline <think>...</think> tags if model embeds them
                            while True:
                                if not inside_think_tag:
                                    if "<think>" in buffer:
                                        pre, post = buffer.split("<think>", 1)
                                        if pre:
                                            full_content_chunks.append(pre)
                                            yield {"type": "content", "text": pre}
                                        inside_think_tag = True
                                        buffer = post
                                    else:
                                        # Yield safe prefix (keep small buffer in case '<think>' is split across chunks)
                                        if len(buffer) > 7:
                                            safe_chunk = buffer[:-7]
                                            buffer = buffer[-7:]
                                            full_content_chunks.append(safe_chunk)
                                            yield {"type": "content", "text": safe_chunk}
                                        break
                                else:
                                    if "</think>" in buffer:
                                        thought_part, post = buffer.split("</think>", 1)
                                        if thought_part:
                                            full_thought_chunks.append(thought_part)
                                            yield {"type": "thought", "text": thought_part}
                                        inside_think_tag = False
                                        buffer = post
                                    else:
                                        if len(buffer) > 8:
                                            safe_thought = buffer[:-8]
                                            buffer = buffer[-8:]
                                            full_thought_chunks.append(safe_thought)
                                            yield {"type": "thought", "text": safe_thought}
                                        break

        # Flush any remaining buffer
        if buffer:
            if inside_think_tag:
                full_thought_chunks.append(buffer)
                yield {"type": "thought", "text": buffer}
            else:
                full_content_chunks.append(buffer)
                yield {"type": "content", "text": buffer}

        complete_text = "".join(full_content_chunks)
        parsed_json = extract_json(complete_text)

        yield {
            "type": "final",
            "summary": parsed_json.get("summary", "Organization plan ready."),
            "moves": parsed_json.get("moves", []),
            "raw_text": complete_text,
            "thoughts": "".join(full_thought_chunks),
        }
