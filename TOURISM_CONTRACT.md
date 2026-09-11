# Limen Tourism Management Agent — Architecture & API Contract Specification

## 1. System Overview & Architecture

Limen is an autonomous tourism decision and management agent built on a high-density "Precision Monolith" developer workbench. It pairs a Python/FastAPI backend with a vanilla HTML/CSS/JavaScript interface communicating over Server-Sent Events (SSE) and REST endpoints.

```
┌─────────────────────────────────────────────────────────────┐
│                       Browser Frontend                      │
│   (Split Workbench: 580px Trace Stream + Flex-1 Inspector)   │
└──────────────┬──────────────────────────────▲───────────────┘
               │ HTTP POST                    │ SSE Streams
               │ (/api/agent/stream,          │ (/api/agent/stream,
               │  /api/tourism/*)             │  /api/tourism/monitor/stream)
┌──────────────▼──────────────────────────────┴───────────────┐
│                      FastAPI Backend                        │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Agent Loop Engine (Decide - Act - Observe)              │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │ Tool Registry (10 Tourism Tools + Generic Regression)   │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │ Bounded Data Adapters (Open-Meteo, OSRM Public Routing) │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │ Session Store & SQLite DB (tourism.db)                  │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Server-Sent Events (SSE) Event Contracts

### A. Primary Agent Execution Stream (`POST /api/agent/stream`)
The request body contains:
```json
{
  "instruction": "string",
  "session_id": "string | null",
  "model": "string | null",
  "data_mode": "scenario | live"
}
```

Stream emits line-delimited SSE chunks in the format `data: <json>\n\n`:

#### 1. `thought` (Internal reasoning trace)
```json
{
  "type": "thought",
  "content": "Analyzing user destination and opening windows...",
  "step": 1,
  "session_id": "session_abc123",
  "run_id": "run_xyz789"
}
```

#### 2. `tool_call` (Tool invocation lifecycle)
Emitted at the start of execution (`status: "running"`) and upon completion (`status: "success"` or `status: "error"`).
```json
{
  "type": "tool_call",
  "status": "running | success | error",
  "step": 1,
  "tool_name": "query_open_places",
  "args": {
    "destination_id": "vizag",
    "max_crowd_pct": 60
  },
  "result_summary": "Found 6 open attractions in Visakhapatnam",
  "result": {
    "places": [...],
    "total_found": 6
  },
  "provenance": {
    "source_name": "OpenStreetMap / Municipal Ground Truth",
    "source_type": "simulated",
    "confidence": 1.0
  },
  "invocation_id": "inv_12345678",
  "session_id": "session_abc123",
  "run_id": "run_xyz789"
}
```

#### 3. `plan_artifact` (Structured tabular output)
Emitted when a tool produces rich tabular data for the inspector panel.
```json
{
  "type": "plan_artifact",
  "artifact_type": "table",
  "title": "Open Attractions: Visakhapatnam",
  "columns": ["Attraction", "Category", "Hours Today", "Status", "Crowd / Occupancy", "Fee (INR)"],
  "rows": [
    ["INS Kursura Submarine Museum", "museum", "14:00 - 20:30", "OPEN", "72% (Surge Warning)", "₹70"],
    ["Ross Hill Viewpoint", "viewpoint", "UNKNOWN", "UNKNOWN SCHEDULE", "12%", "₹0"]
  ],
  "session_id": "session_abc123",
  "run_id": "run_xyz789"
}
```

#### 4. `final_answer` (Synthesized markdown response)
```json
{
  "type": "final_answer",
  "content": "Based on current schedules and crowd readings...",
  "session_id": "session_abc123",
  "run_id": "run_xyz789"
}
```

#### 5. `error` (Execution error)
```json
{
  "type": "error",
  "message": "Detailed error message",
  "step": 2,
  "session_id": "session_abc123",
  "run_id": "run_xyz789"
}
```

#### 6. `done` (Run terminal signal)
```json
{
  "type": "done",
  "converged": true,
  "session_id": "session_abc123",
  "run_id": "run_xyz789"
}
```

---

### B. Autonomous Monitoring Stream (`GET /api/tourism/monitor/stream?session_id=...`)
Provides continuous real-time state updates for an active itinerary:

| Event Type | Trigger & Content |
|------------|-------------------|
| `monitoring_started` | Monitoring daemon starts polling for the given `session_id`. |
| `monitoring_tick` | Polling heartbeat containing `iteration`, `timestamp`, and `itinerary_id`. |
| `itinerary_healthy` | All stops operating normally without active closures or disruptions. |
| `disruption_detected` | Closure or incident impacts one or more stops in the saved itinerary. |
| `autonomous_replan` | Agent executes automated replanning loop, proposing replacement stops. |
| `monitoring_stopped` | Monitoring loop completes its max ticks or is explicitly stopped. |

---

## 3. REST API Specifications

### Configuration & System Endpoints
- `GET /api/config`: Returns active model, provider URL, max steps, and masked API key.
- `POST /api/config`: Updates model provider parameters (`provider_url`, `active_model`, `api_key`, `max_steps`).

### Session Endpoints
- `GET /api/sessions`: Lists all persistent sessions.
- `POST /api/sessions`: Creates a new session `{ "title": "...", "folder_path": "..." }`.
- `GET /api/sessions/{session_id}`: Retrieves complete session transcript and artifacts.
- `DELETE /api/sessions/{session_id}`: Deletes a session and its saved state.

### Tourism Domain & Scenario Endpoints
- `GET /api/tourism/context?session_id=...&data_mode=...`:
  Returns destination context (local time in `Asia/Kolkata`, live weather from Open-Meteo, active disruptions count, emergency closures count, and current data mode).
- `POST /api/tourism/reset`:
  Resets SQLite scenario tables to deterministic baseline records.
- `POST /api/tourism/trigger-scenario`:
  Injects emergency closure (default: `ins_kursura`) and triggers crowd surge at nearby alternative (`tu_142_museum`).
- `POST /api/tourism/monitor/start`:
  Spawns background monitor loop for session `{ "session_id": "...", "interval_seconds": 3.0, "max_ticks": 60 }`.
- `POST /api/tourism/monitor/stop?session_id=...`:
  Stops active monitoring daemon.
- `POST /api/tourism/itinerary/recheck?session_id=...`:
  Manually triggers immediate health check and autonomous replanning if disrupted.

---

## 4. Provenance & Truthful Data Models

Every tool result and adapter response attaches a structured `provenance` dictionary:

```json
{
  "source_name": "string",
  "source_type": "live | simulated | stale | unknown | fallback",
  "source_url": "string | null",
  "fetched_at": "ISO-8601 UTC timestamp",
  "confidence": 0.0 to 1.0,
  "notes": "string | null"
}
```

### Truthfulness Contract
1. **Never Fabricate Unknowns:** Missing opening hours (e.g. Ross Hill) must return `status: "UNKNOWN"` rather than guessed hours.
2. **Never Fabricate Live Inventories:** Hotel room counts and live crowd sensors are synthetic fixture data; in `live` mode, lack of live booking API returns `status: "UNKNOWN"`.
3. **Explicit Fallbacks:** When OSRM live routing fails or calculates pedestrian transit, the source type is tagged as `fallback` with Haversine speed notes.

---

## 5. UI & Design System Component Contract

The frontend strictly implements the **"Precision Monolith"** design system:
- **Surfaces:** `#0E0F12` (canvas), `#121418` (rails/bars), `#16181E` (inspector/panels), `#1C1F26` (cards/inputs).
- **Typography:** 13px base UI font (`Inter` / system sans), 11px monospace for tool args and telemetry (`JetBrains Mono`, `Consolas`).
- **Semantic Accents:**
  - **Success / Converged:** Emerald Green `#34D399`
  - **Error / Interrupted:** Coral Red `#F87171`
  - **Warning / Non-converged:** Amber `#FBBF24`
  - **Telemetry / Tool Activity:** Ice Cyan `#38BDF8`
  - **Artifacts / Tables:** Light Violet `#A78BFA`
- **Actions:** High-contrast bone-white `#E1E4EA` on dark background for primary submission; subtle ghost buttons for scenario triggers.
