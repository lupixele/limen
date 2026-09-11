"""FastAPI Server for Autonomous Tourism Agent Harness with SSE Streaming and Monitoring."""
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.llm_client import OpenAICompatibleClient
from agent.loop import run_agent_loop
from core.sessions import SessionStore
from core.tools import CalculatorTool, MockLookupTool, ToolRegistry
from tourism.adapters import WeatherAdapter
from tourism.db import get_db_connection, init_db
from tourism.monitor import global_monitor
from tourism.seeds import seed_scenario_data
from tourism.tools import (
    AllocateAuthoritiesResourcesTool,
    BuildItineraryTool,
    CalculateRouteTool,
    CheckDisruptionsTool,
    ProjectCrowdSurgeTool,
    QueryAccommodationsTool,
    QueryEventsTool,
    QueryOpenPlacesTool,
    RankCrowdsTool,
    RecommendStaffingTool,
    UpdatePreferencesTool,
)

logger = logging.getLogger("app")
PROJECT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = PROJECT_DIR / "config.json"
STATIC_DIR = PROJECT_DIR / "static"
TZ_KOLKATA = ZoneInfo("Asia/Kolkata")

app = FastAPI(title="Limen Autonomous Tourism Agent", version="3.1.0")
session_store = SessionStore()

# Global tracking of active agent runs for explicit cancellation
_active_agent_runs: Dict[str, asyncio.Task] = {}

# Ensure tourism database is initialized and seeded on startup
init_db()
conn_check = get_db_connection()
c = conn_check.cursor()
c.execute("SELECT COUNT(*) as cnt FROM attractions")
if c.fetchone()["cnt"] == 0:
    seed_scenario_data()
conn_check.close()

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
        "custom_models": [
            "antigravity/gemini-3.8-flash-tiered",
            "auto/best-fast",
            "gpt-4o-mini",
        ],
        "max_steps": 8,
    }


def save_config(cfg: Dict[str, Any]):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_session_context(session_id: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Retrieves isolated, persistent session context (preferences, latest itinerary) for this session only."""
    context: Dict[str, Any] = {
        "session_id": session_id,
        "preferences": None,
        "active_itinerary": None,
    }
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()

        # 1. Fetch saved user preferences for this session
        cursor.execute("SELECT * FROM session_preferences WHERE session_id = ?", (session_id,))
        pref = cursor.fetchone()
        if pref:
            context["preferences"] = {
                "target_city": pref["target_city"],
                "target_date": pref["target_date"],
                "budget_limit": pref["budget_limit"],
                "budget_currency": pref["budget_currency"],
                "party_size": pref["party_size"],
                "interests": json.loads(pref["interests_json"] or "[]"),
                "updated_at": pref["updated_at"],
            }

        # 2. Fetch latest saved itinerary for this session ONLY
        cursor.execute(
            """
            SELECT id, title, target_date, status, total_cost, summary, version, stops_json, updated_at
            FROM itineraries
            WHERE session_id = ?
            ORDER BY version DESC, updated_at DESC LIMIT 1
        """,
            (session_id,),
        )
        itin = cursor.fetchone()
        if itin:
            context["active_itinerary"] = {
                "itinerary_id": itin["id"],
                "title": itin["title"],
                "target_date": itin["target_date"],
                "status": itin["status"],
                "total_cost": itin["total_cost"],
                "summary": itin["summary"],
                "version": itin["version"],
                "stops": json.loads(itin["stops_json"] or "[]"),
                "updated_at": itin["updated_at"],
            }
        conn.close()
    except Exception as e:
        logger.warning(f"Error loading session context for {session_id}: {e}")

    return context


def create_agent_registry(db_path: Optional[Path] = None) -> ToolRegistry:
    """Builds a ToolRegistry populated with both generic regression tools and all 10 tourism tools."""
    registry = ToolRegistry()
    # Generic regression tools
    registry.register(CalculatorTool())
    registry.register(MockLookupTool())
    # Tourism domain tools
    registry.register(QueryOpenPlacesTool(db_path))
    registry.register(BuildItineraryTool(db_path))
    registry.register(CalculateRouteTool(db_path))
    registry.register(CheckDisruptionsTool(db_path))
    registry.register(QueryAccommodationsTool(db_path))
    registry.register(QueryEventsTool(db_path))
    registry.register(RankCrowdsTool(db_path))
    registry.register(ProjectCrowdSurgeTool(db_path))
    registry.register(RecommendStaffingTool(db_path))
    registry.register(AllocateAuthoritiesResourcesTool(db_path))
    registry.register(UpdatePreferencesTool(db_path))
    return registry


# Connect monitor runner to actual model loop
async def _monitor_agent_runner(
    session_id: str, instruction: str, health: Dict[str, Any]
) -> Dict[str, Any]:
    cfg = load_config()
    registry = create_agent_registry()
    provider_url = cfg.get("provider_url", "http://localhost:20128/v1")
    api_key = cfg.get("api_key", "")
    model = cfg.get("active_model", "antigravity/gemini-3.8-flash-tiered")
    session_ctx = get_session_context(session_id)
    replan_run_id = f"replan_{uuid.uuid4().hex[:8]}"

    artifact = None
    itinerary_id = None

    async for event in run_agent_loop(
        instruction=instruction,
        registry=registry,
        provider_url=provider_url,
        api_key=api_key,
        model=model,
        session_id=session_id,
        run_id=replan_run_id,
        max_steps=6,
        context=session_ctx,
    ):
        await global_monitor.emit_event(session_id, event)
        if event.get("type") == "plan_artifact":
            artifact = event
        elif event.get("type") == "tool_call" and event.get("artifact"):
            artifact = event.get("artifact")

    conn = get_db_connection()
    c_sub = conn.cursor()
    c_sub.execute(
        "SELECT id FROM itineraries WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    )
    row = c_sub.fetchone()
    if row:
        itinerary_id = row["id"]
    conn.close()

    return {"itinerary_id": itinerary_id, "artifact": artifact}


global_monitor.set_agent_runner(_monitor_agent_runner)


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


class TriggerScenarioRequest(BaseModel):
    attraction_id: Optional[str] = "ins_kursura"
    reason: Optional[str] = "Emergency electrical maintenance on submarine dehumidification system"


class MonitorStartRequest(BaseModel):
    session_id: str
    interval_seconds: Optional[float] = 4.0
    max_ticks: Optional[int] = 15


class CancelRequest(BaseModel):
    session_id: Optional[str] = None
    run_id: Optional[str] = None


# System & Config Endpoints
@app.get("/api/config")
def get_config():
    cfg = load_config()
    api_key = cfg.get("api_key", "")
    return {
        "provider_url": cfg.get("provider_url", "http://localhost:20128/v1"),
        "active_model": cfg.get("active_model", ""),
        "custom_models": cfg.get("custom_models", []),
        "max_steps": cfg.get("max_steps", 8),
        "default_target_folder": cfg.get("default_target_folder", ""),
        "has_api_key": bool(api_key.strip()),
        "api_key_masked": (
            (api_key[:3] + "..." + api_key[-4:])
            if len(api_key) > 7
            else ("••••••••" if api_key else "")
        ),
    }


@app.post("/api/config")
def update_config(req: ConfigUpdateRequest):
    cfg = load_config()
    if req.provider_url is not None:
        cfg["provider_url"] = req.provider_url.strip()
    if req.api_key is not None:
        key_candidate = req.api_key.strip()
        # Safe masking guard: never overwrite real key with masked placeholder
        if key_candidate and not key_candidate.startswith("••") and "..." not in key_candidate:
            cfg["api_key"] = key_candidate
        elif key_candidate == "":
            cfg["api_key"] = ""
    if req.active_model is not None:
        cfg["active_model"] = req.active_model.strip()
    if req.max_steps is not None:
        cfg["max_steps"] = max(1, min(int(req.max_steps), 50))
    if req.custom_models is not None:
        deduped = []
        for m in req.custom_models:
            m_clean = str(m).strip()
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
    if isinstance(result, dict):
        result.pop("api_key", None)
    return result


# Session Management Endpoints
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
    if not updated:
        raise HTTPException(status_code=404, detail="Artifact or session not found")
    return {"status": "ok", "message": "Artifact status updated"}


# Agent Run Cancellation Endpoint
@app.post("/api/agent/cancel")
def cancel_agent_run(req: CancelRequest):
    cancelled = False
    if req.run_id and req.run_id in _active_agent_runs:
        task = _active_agent_runs.pop(req.run_id)
        if not task.done():
            task.cancel()
            cancelled = True
    elif req.session_id and req.session_id in _active_agent_runs:
        task = _active_agent_runs.pop(req.session_id)
        if not task.done():
            task.cancel()
            cancelled = True
    return {
        "status": "cancelled" if cancelled else "not_found",
        "run_id": req.run_id,
        "session_id": req.session_id,
    }


# Tourism Domain & Scenario Endpoints
@app.post("/api/tourism/reset")
def reset_tourism_data():
    """Idempotent seed/reset of demo scenario data."""
    seed_scenario_data()
    return {"status": "ok", "message": "Tourism scenario data reset to deterministic baseline."}


@app.post("/api/tourism/trigger-scenario")
def trigger_scenario(req: TriggerScenarioRequest):
    """Triggers scenario change (emergency closure and crowd surge) in underlying data ONLY."""
    attraction_id = req.attraction_id or "ins_kursura"
    reason = req.reason or "Emergency electrical maintenance on submarine dehumidification system"

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        now_kolkata = datetime.now(TZ_KOLKATA)
        closure_until = (now_kolkata + timedelta(hours=6)).isoformat()
        cursor.execute(
            """
            UPDATE attractions
            SET has_emergency_closure = 1, closure_reason = ?, closure_until = ?
            WHERE id = ?
        """,
            (reason, closure_until, attraction_id),
        )
        dis_id = f"dis_emergency_{attraction_id}_{int(datetime.now().timestamp())}"
        cursor.execute(
            """
            INSERT INTO disruptions (
                id, destination_id, disruption_type, severity, title, description,
                affected_places_json, start_time, end_time, active, source_type
            ) VALUES (?, 'vizag', 'closure', 'critical', ?, ?, ?, ?, ?, 1, 'simulated')
        """,
            (
                dis_id,
                f"Emergency Closure: {attraction_id.upper()}",
                reason,
                json.dumps([attraction_id]),
                now_kolkata.isoformat(),
                closure_until,
            ),
        )
        cursor.execute(
            """
            INSERT INTO crowd_readings (attraction_id, timestamp, visitor_count, capacity, occupancy_pct, source_type)
            VALUES (?, ?, 235, 250, 94.0, 'simulated')
        """,
            ("tu142_museum", datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        res = {
            "attraction_closed": attraction_id,
            "reason": reason,
            "disruption_id": dis_id,
            "crowd_surge_at": "tu142_museum",
            "surge_occupancy_pct": 94.0,
        }
    finally:
        conn.close()

    return {"status": "ok", "data": res}


@app.get("/api/tourism/context")
async def get_tourism_context(
    session_id: Optional[str] = Query(None), data_mode: Optional[str] = Query(None)
):
    """Returns real-time destination context, local time, weather, active alerts, and isolated session context."""
    now_kolkata = datetime.now(TZ_KOLKATA)
    conn = get_db_connection()
    c_ctx = conn.cursor()
    c_ctx.execute("SELECT * FROM disruptions WHERE active = 1")
    disruptions = [dict(r) for r in c_ctx.fetchall()]
    c_ctx.execute("SELECT COUNT(*) as cnt FROM attractions WHERE has_emergency_closure = 1")
    emergency_closed_count = c_ctx.fetchone()["cnt"]
    conn.close()

    # Fetch live weather
    wx = await WeatherAdapter.get_current_and_forecast(17.68009, 83.20161)
    current_wx = wx.get("current", {})

    resp: Dict[str, Any] = {
        "city": "Visakhapatnam",
        "state": "Andhra Pradesh",
        "country": "India",
        "timezone": "Asia/Kolkata",
        "local_datetime": now_kolkata.strftime("%Y-%m-%d %I:%M %p"),
        "date": now_kolkata.strftime("%Y-%m-%d"),
        "weather": {
            "temperature_c": current_wx.get("temperature_2m", 27.0),
            "precipitation_mm": current_wx.get("precipitation", 0.0),
            "apparent_temp_c": current_wx.get("apparent_temperature", 30.0),
            "wind_speed_kmh": current_wx.get("wind_speed_10m", 12.0),
            "source": "Open-Meteo Live API",
            "provenance": {
                "source_name": "Open-Meteo Weather API",
                "source_type": "live",
                "confidence": 0.98,
            },
        },
        "active_disruptions": len(disruptions),
        "emergency_closed_places": emergency_closed_count,
        "data_mode": data_mode
        or "Hybrid (Live Weather & Routing + Sourced Attractions + Simulated Sensor Feeds)",
    }

    if session_id:
        resp["session_id"] = session_id
        resp["session_context"] = get_session_context(session_id)

    return resp


# Monitoring & Autonomous Replanning Endpoints
@app.post("/api/tourism/monitor/start")
async def start_itinerary_monitoring(req: MonitorStartRequest):
    """Spawns background bounded monitoring loop for active session itinerary with strict no-overlap guard."""
    started = global_monitor.start_monitoring(
        session_id=req.session_id,
        interval_seconds=req.interval_seconds or 4.0,
        max_ticks=req.max_ticks or 15,
    )
    return {
        "status": "started" if started else "already_running",
        "session_id": req.session_id,
    }


@app.post("/api/tourism/monitor/stop")
def stop_itinerary_monitoring(session_id: str = Query(...)):
    stopped = global_monitor.stop_monitoring(session_id)
    return {"status": "stopped" if stopped else "not_running", "session_id": session_id}


@app.get("/api/tourism/monitor/status")
def get_monitoring_status(session_id: str = Query(...)):
    return global_monitor.get_status(session_id)


@app.post("/api/tourism/itinerary/recheck")
async def manual_itinerary_recheck(session_id: str = Query(...)):
    """Manual recheck now action: checks health and triggers autonomous replan if disrupted."""
    health = await global_monitor.check_itinerary_health(session_id)
    if not health.get("healthy"):
        replan = await global_monitor.autonomous_replan(session_id, health)
        return {"status": "replan_triggered", "health": health, "replan": replan}
    return {"status": "healthy", "health": health}


@app.get("/api/tourism/monitor/stream")
async def stream_monitoring(session_id: str = Query(...)):
    """SSE Stream for background monitoring events and autonomous replans."""
    queue = await global_monitor.register_listener(session_id)

    async def mon_generator():
        try:
            while True:
                ev = await queue.get()
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get("type") in ("monitoring_stopped", "autonomous_replan"):
                    break
        except asyncio.CancelledError:
            pass

    return StreamingResponse(mon_generator(), media_type="text/event-stream")


# Autonomous Agent Streaming Endpoint (Server-Sent Events)
@app.post("/api/agent/stream")
async def stream_agent(req: StreamRequest):
    """
    Executes the autonomous decide-act-observe agent loop, streaming events via SSE.
    Enforces session isolation, trusted session tool binding, failure persistence,
    and cancellation semantics.
    """
    cfg = load_config()
    model_to_use = (req.model or cfg.get("active_model", "")).strip()
    if not model_to_use:
        raise HTTPException(
            status_code=400, detail="No model ID selected. Configure in Settings."
        )

    session_id = req.session_id or f"session_{uuid.uuid4().hex[:12]}"
    active_session = session_store.get_session(session_id)
    if not active_session:
        active_session = {
            "id": session_id,
            "title": req.instruction[:36] + ("..." if len(req.instruction) > 36 else ""),
            "folder_path": req.folder_path or "",
            "created_at": time.time(),
            "updated_at": time.time(),
            "turns": [],
        }
        session_store.save_session(active_session)

    # Record user turn
    user_turn = {
        "id": f"turn_u_{uuid.uuid4().hex[:8]}",
        "role": "user",
        "timestamp": time.time(),
        "content": req.instruction,
        "folder_path": req.folder_path or "",
    }
    session_store.append_turn(session_id, user_turn)

    # Initialize Tool Registry with both generic and tourism tools
    registry = create_agent_registry()

    provider_url = cfg.get("provider_url", "http://localhost:20128/v1")
    api_key = cfg.get("api_key", "")
    max_steps = int(cfg.get("max_steps", 8))
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    session_ctx = get_session_context(session_id)

    async def event_generator():
        assistant_turn_id = f"turn_a_{uuid.uuid4().hex[:8]}"
        tool_records: List[Dict[str, Any]] = []
        full_thoughts: List[str] = []
        final_answer_text = ""
        plan_artifact: Optional[Dict[str, Any]] = None
        converged = False

        # Register active task for cancellation
        current_task = asyncio.current_task()
        if current_task:
            _active_agent_runs[run_id] = current_task
            _active_agent_runs[session_id] = current_task

        try:
            async for event in run_agent_loop(
                instruction=req.instruction,
                registry=registry,
                provider_url=provider_url,
                api_key=api_key,
                model=model_to_use,
                session_id=session_id,
                run_id=run_id,
                prior_turns=active_session.get("turns", []),
                max_steps=max_steps,
                context=session_ctx,
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
                elif ev_type == "done":
                    converged = bool(event.get("converged", False))

                # Emit formatted Server-Sent Event
                yield f"data: {json.dumps(event)}\n\n"

            # Normal completion persistence
            assistant_turn = {
                "id": assistant_turn_id,
                "role": "assistant",
                "timestamp": time.time(),
                "content": final_answer_text,
                "status": "completed" if converged else "incomplete",
                "thoughts": "\n".join(full_thoughts),
                "tools": tool_records,
                "plan_artifact": plan_artifact,
            }
            session_store.append_turn(session_id, assistant_turn)

        except asyncio.CancelledError:
            # Failure/Cancellation Persistence: preserve partial evidence collected before abort
            assistant_turn = {
                "id": assistant_turn_id,
                "role": "assistant",
                "timestamp": time.time(),
                "content": final_answer_text or "Execution cancelled by client/user.",
                "status": "cancelled",
                "thoughts": "\n".join(full_thoughts),
                "tools": tool_records,
                "plan_artifact": plan_artifact,
            }
            session_store.append_turn(session_id, assistant_turn)
            raise

        except Exception as e:
            # Failure Persistence: preserve partial evidence collected before error
            assistant_turn = {
                "id": assistant_turn_id,
                "role": "assistant",
                "timestamp": time.time(),
                "content": final_answer_text or f"Execution failed: {str(e)}",
                "status": "failed",
                "thoughts": "\n".join(full_thoughts),
                "tools": tool_records,
                "plan_artifact": plan_artifact,
            }
            session_store.append_turn(session_id, assistant_turn)

            yield f"data: {json.dumps({'type': 'error', 'session_id': session_id, 'run_id': run_id, 'message': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'run_id': run_id, 'converged': False})}\n\n"

        finally:
            _active_agent_runs.pop(run_id, None)
            _active_agent_runs.pop(session_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Mount Static UI Files
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")
