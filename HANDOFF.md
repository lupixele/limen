# Session Handoff: Limen Autonomous Agent Platform

**Date:** 2026-09-10  
**Status:** Backend Harness Verified & Competition-Ready  
**Active Working Directory:** `P:\Magnanimity\Projects\Limen\backend`

---

## 1. Current State & What Was Accomplished Tonight
We successfully dismantled the old, hardcoded procedural file organizer backend and extracted it into a **genuine, domain-agnostic decide → act → observe AI agent harness**.

The platform lives in `P:\Magnanimity\Projects\Limen\backend` and has been verified with live, real-model execution over OmniRoute:
1. **Model-Controlled Loop (`backend/agent/loop.py`):**
   - Native OpenAI function-calling (`tool_choice="auto"`).
   - Zero hardcoded tool sequences; the model decides what to call, with what parameters, or when to stop.
   - Max-step guardrail (default: 8) with clean non-converged termination states.
   - Live SSE event streaming (`tool_call`, `thought`, `plan_artifact`, `final_answer`, `done`, `error`).
2. **Tool Protocol & Registry (`backend/core/tools.py`):**
   - Clean `Tool` protocol (`name`, `description`, `json_schema`, `async run(**kwargs) -> ToolResult`).
   - `ToolRegistry` for auto-exporting function schemas and safe dispatch.
   - Ships with AST-safe `CalculatorTool` (zero `eval()`) and deterministic `MockLookupTool`.
3. **Strict Grounding Rule (`backend/agent/prompt.py`):**
   - System prompt explicitly enforces that every value used in a decision or condition must have a corresponding tool call in the trace.
   - Proved live: when tested on a branching threshold task, the agent fetched data, branched its tool execution dynamically, and refused to fabricate numbers when simulated timeouts occurred.
4. **Clean Decoupling:**
   - Legacy file-organizer domain modules (`sandbox.py`, `scanner.py`, `executor.py`, `undo.py`, and `/api/scan`, `/api/fs/browse`, `/api/execute`) are archived in `Projects/file organaiser/archive/`.
   - `app.py` has **zero** file-organizer dependencies.
   - All 18 automated unit tests in `tests/` are passing (`python -m unittest discover tests`).

---

## 2. Verified Live Proof Scripts (Run to Verify Anytime)
From `P:\Magnanimity\Projects\Limen\backend`:
- `python run_live_proof.py`: Multi-step adaptive tool chaining (lookup -> observe -> calculate -> final answer).
- `python run_branching_test.py`: Dynamic conditional branching (proves Run 1 calls 3 tools, Run 2 stops after 2 tools).
- `python run_failure_test.py`: Error resilience & anti-hallucination when an external tool returns `success=False`.

---

## 3. Tomorrow's Immediate Plan & Roadmap

### Step 1: Plug in the Real Competition Tools
Do not touch `loop.py`, `app.py`, or SSE routing. Simply implement the `Tool` protocol for tomorrow's competition problem domain in `backend/core/tools.py` (or a dedicated `domain_tools.py`):
```python
class CompetitionTool:
    name: str = "your_tool_name"
    description: str = "Detailed description telling the model when and how to use this tool."
    json_schema: dict = { ... }
    async def run(self, **kwargs) -> ToolResult:
        try:
            ...
            return ToolResult(success=True, output=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```
Register it in `backend/app.py` or registry initialization:
```python
registry.register(CompetitionTool())
```

### Step 2: Error & Partial Data Watchpoint
As noted tonight: real-world tools return messy data (nulls, partial schemas, timeouts). Keep tool return shapes consistent via `ToolResult(success=..., output=..., error=...)`. The model is already instructed to halt or report blockers rather than guessing ungrounded values.

### Step 3: Frontend Theming / Polish (If Required)
The UI in `backend/static/` communicates over SSE via `/api/agent/stream`. The streaming contract is stable:
- `event.type == "tool_call"`: `{step, tool_name, status ("running"|"success"|"error"), args, result_summary}`
- `event.type == "thought"`: `{step, content}`
- `event.type == "plan_artifact"`: `{columns: [...], rows: [...]}`
- `event.type == "final_answer"`: `{content, converged}`
- `event.type == "done"`: `{session_id, converged}`
Frontend updates only need to render these events cleanly.

---

## 4. Environment & Launch
- **Launch server:** `cd P:\Magnanimity\Projects\Limen\backend && uvicorn app:app --host 127.0.0.1 --port 8000 --reload` (or run `start.bat`)
- **Active Model/Provider:** Configured in `backend/config.json` (OmniRoute `http://localhost:20128/v1`, default model `antigravity/gemini-3.8-flash-tiered`).
