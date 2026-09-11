# Limen — Autonomous AI Agent Platform

Autonomous, problem-agnostic AI agent harness built for competition and real-time execution. Features a genuine decide-act-observe loop with dynamic tool selection, strict grounding, multi-step branching, and live SSE event streaming.

## Tech Stack
- **Backend:** Python 3.11, FastAPI, Uvicorn, httpx, pydantic
- **AI Protocol:** OpenAI-compatible `/v1/chat/completions` with native tool/function calling (OmniRoute, Ollama, OpenRouter)
- **Streaming:** Server-Sent Events (`text/event-stream`) streaming reasoning, tool execution status, plan artifacts, and answers
- **Persistence:** File-based session store (`.sessions/*.json`) for multi-turn threads
- **Frontend:** Responsive dark web interface (HTML5 / CSS3 / Vanilla JS)

## Project Structure
```text
P:/Magnanimity/Projects/Limen/
├── backend/
│   ├── agent/
│   │   ├── loop.py          # Core decide-act-observe agent loop
│   │   ├── prompt.py        # Generic prompt & strict grounding rules
│   │   └── llm_client.py    # OpenAI client helper
│   ├── core/
│   │   ├── tools.py         # Tool Protocol, ToolRegistry, Calculator, MockLookup
│   │   └── sessions.py      # Conversation turn persistence
│   ├── tests/               # Full automated unit test suite (18 tests)
│   ├── static/              # Web harness UI
│   ├── app.py               # FastAPI server & SSE streaming route
│   ├── config.json          # Provider URL, active model, settings
│   ├── requirements.txt     # Python dependencies
│   ├── run_live_proof.py    # Live multi-tool chaining test
│   ├── run_branching_test.py# Adaptive high/low threshold branching test
│   └── run_failure_test.py  # Error recovery & anti-hallucination test
├── index.md                 # Project root index
└── PROGRESS.md              # Milestone tracking & architectural log
```
