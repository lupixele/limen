# Limen — Autonomous AI Agent Platform

Limen is a lightweight, competition-ready, problem-agnostic autonomous AI agent harness built on FastAPI and modern agent loop principles.

## Features

- **Decide-Act-Observe Loop**: Native function-calling agent loop where the model autonomously plans, chooses tools, observes runtime outputs, and decides next actions.
- **Strict Grounding**: System prompt guardrails requiring full tool-retrieval verification before making evaluations or decisions.
- **SSE Real-Time Streaming**: Server-Sent Events delivering live reasoning thoughts, tool execution states (`running`, `success`, `error`), generalized plan artifacts, and final conclusions.
- **Pluggable Tool Registry**: Clean `Tool` protocol for registering any external API, database, or domain executor without modifying routing or core agent logic.
- **Zero Hardcoded Secrets**: Configuration loads securely with support for external providers (e.g. OmniRoute, Ollama, OpenRouter).

## Architecture

```text
Limen/
├── backend/
│   ├── agent/
│   │   ├── loop.py          # Core decide-act-observe agent loop
│   │   ├── prompt.py        # Generic system prompt & grounding rules
│   │   └── llm_client.py    # OpenAI-compatible client adapter
│   ├── core/
│   │   ├── tools.py         # Tool Protocol, Registry, Calculator, MockLookup
│   │   └── sessions.py      # Conversation turn persistence
│   ├── static/              # Web application harness
│   ├── tests/               # Automated unit test suite
│   ├── app.py               # FastAPI application & SSE streaming
│   ├── config.example.json  # Configuration template
│   ├── requirements.txt     # Dependencies
│   └── run_*.py             # Automated proof scripts
├── Design/                  # OpenDesign specifications and UI plans
├── index.md                 # Vault index & manifest
├── PROGRESS.md              # Milestone tracking
└── HANDOFF.md               # Session context & architecture handoff
```

## Getting Started

### 1. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Endpoint
Copy `config.example.json` to `config.json` and adjust your provider settings:
```bash
cp config.example.json config.json
```

### 3. Run the Server
```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
# Or execute start.bat on Windows
```

### 4. Run Tests & Live Proofs
```bash
python -m unittest discover tests
python run_live_proof.py
python run_branching_test.py
python run_failure_test.py
```
