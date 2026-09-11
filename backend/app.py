"""FastAPI Server for Autonomous Agent Harness with SSE Streaming."""
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.llm_client import OpenAICompatibleClient
from agent.loop import run_agent_loop
from core.sessions import SessionStore
from core.tools import CalculatorTool, MockLookupTool, ToolRegistry

PROJECT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = PROJECT_DIR / "config.json"
STATIC_DIR = PROJECT_DIR / "static"

app = FastAPI(title="Autonomous Agent Harness", version="3.0.0")
session_store = SessionStore()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    example_path = PROJECT_DIR / "config.example.json"
    if example_path.exists():
        try:
            with open(example_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "provider_url": "http://localhost:20128/v1",
        "api_key": "",
        "active_model": "antigravity/gemini-3.8-flash-tiered",
        "custom_models": ["antigravity/gemini-3.8-flash-tiered", "auto/best-fast", "gpt-4o-mini"],
        "max_steps": 8,
    }


def save_config(cfg: Dict[str, Any]):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# Request & Response Schemas
class ConfigUpdateRequest(BaseModel):
    provider_url: Optional[str] = None
    api_key: Optional[str] = None
    active_model: Optional[str] = None
    custom_models: Optional[List[str]] = None
    max_steps: Optional[int] = None
    default_target_folder: Optional[str] = None


class StreamRequest(BaseModel):
    instruction: str
    session_id: Optional[str] = None
    folder_path: Optional[str] = None
    model: Optional[str] = None


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    folder_path: Optional[str] = ""


class ArtifactStatusRequest(BaseModel):
    status: str


# System & Config Endpoints
@app.get("/api/config")
def get_config():
    cfg = load_config()
    return {
        "provider_url": cfg.get("provider_url", "http://localhost:20128/v1"),
        "active_model": cfg.get("active_model", ""),
        "custom_models": cfg.get("custom_models", []),
        "max_steps": cfg.get("max_steps", 8),
        "default_target_folder": cfg.get("default_target_folder", ""),
        "has_api_key": bool(cfg.get("api_key", "").strip()),
        "api_key_masked": (
            (cfg.get("api_key", "")[:3] + "..." + cfg.get("api_key", "")[-4:])
            if len(cfg.get("api_key", "")) > 7
            else ("••••••••" if cfg.get("api_key") else "")
        ),
    }


@app.post("/api/config")
def update_config(req: ConfigUpdateRequest):
    cfg = load_config()
    if req.provider_url is not None:
        cfg["provider_url"] = req.provider_url.strip()
    if req.api_key is not None:
        cfg["api_key"] = req.api_key.strip()
    if req.active_model is not None:
        cfg["active_model"] = req.active_model.strip()
    if req.max_steps is not None:
        cfg["max_steps"] = max(1, min(req.max_steps, 50))
    if req.custom_models is not None:
        deduped = []
        for m in req.custom_models:
            m_clean = m.strip()
            if m_clean and m_clean not in deduped:
                deduped.append(m_clean)
        cfg["custom_models"] = deduped
    if req.default_target_folder is not None:
        cfg["default_target_folder"] = req.default_target_folder.strip()

    save_config(cfg)
    return {"status": "ok", "message": "Settings saved successfully."}


@app.post("/api/test-connection")
async def test_connection():
    cfg = load_config()
    client = OpenAICompatibleClient(
        base_url=cfg.get("provider_url", "http://localhost:20128/v1"),
        api_key=cfg.get("api_key", ""),
    )
    result = await client.test_connection()
    return result


# Session Persistence Endpoints
@app.get("/api/sessions")
def list_sessions():
    return session_store.list_sessions()


@app.post("/api/sessions")
def create_session(req: CreateSessionRequest):
    return session_store.create_session(title=req.title, folder_path=req.folder_path or "")


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    sess = session_store.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    success = session_store.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok", "message": "Session deleted"}


@app.post("/api/sessions/{session_id}/artifact/{artifact_id}")
def update_artifact_status(session_id: str, artifact_id: str, req: ArtifactStatusRequest):
    updated = session_store.update_artifact_status(session_id, artifact_id, req.status)
    return {"status": "ok" if updated else "not_found"}


# Autonomous Agent Streaming Endpoint (Server-Sent Events)
@app.post("/api/agent/stream")
async def stream_agent(req: StreamRequest):
    """
    Executes the autonomous decide-act-observe agent loop, streaming events via SSE.
    """
    cfg = load_config()
    model_to_use = (req.model or cfg.get("active_model", "")).strip()
    if not model_to_use:
        raise HTTPException(status_code=400, detail="No model ID selected. Configure in Settings.")

    session_id = req.session_id or f"session_{uuid.uuid4().hex[:12]}"
    active_session = session_store.get_session(session_id)
    if not active_session:
        active_session = session_store.create_session(
            title=req.instruction[:36] + ("..." if len(req.instruction) > 36 else ""),
            folder_path=req.folder_path or "",
        )
        session_id = active_session["id"]

    # Record user turn
    user_turn = {
        "id": f"turn_u_{uuid.uuid4().hex[:8]}",
        "role": "user",
        "timestamp": time.time(),
        "content": req.instruction,
        "folder_path": req.folder_path or "",
    }
    session_store.append_turn(session_id, user_turn)

    # Initialize Tool Registry with default tools
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(MockLookupTool())

    provider_url = cfg.get("provider_url", "http://localhost:20128/v1")
    api_key = cfg.get("api_key", "")
    max_steps = int(cfg.get("max_steps", 8))

    async def event_generator():
        assistant_turn_id = f"turn_a_{uuid.uuid4().hex[:8]}"
        tool_records: List[Dict[str, Any]] = []
        full_thoughts: List[str] = []
        final_answer_text = ""
        plan_artifact: Optional[Dict[str, Any]] = None

        try:
            async for event in run_agent_loop(
                instruction=req.instruction,
                registry=registry,
                provider_url=provider_url,
                api_key=api_key,
                model=model_to_use,
                session_id=session_id,
                max_steps=max_steps,
            ):
                ev_type = event.get("type")
                if ev_type == "tool_call" and event.get("status") in ("success", "error"):
                    tool_records.append(event)
                elif ev_type == "thought":
                    full_thoughts.append(event.get("content", ""))
                elif ev_type == "final_answer":
                    final_answer_text = event.get("content", "")
                elif ev_type == "plan_artifact":
                    plan_artifact = event

                # Emit formatted Server-Sent Event
                yield f"data: {json.dumps(event)}\n\n"

            # Persist assistant turn to session store
            assistant_turn = {
                "id": assistant_turn_id,
                "role": "assistant",
                "timestamp": time.time(),
                "content": final_answer_text,
                "thoughts": "\n".join(full_thoughts),
                "tools": tool_records,
                "plan_artifact": plan_artifact,
            }
            session_store.append_turn(session_id, assistant_turn)

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'converged': False})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Mount Static UI Files
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")
