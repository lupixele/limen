"""Live Proof Script: Demonstrates adaptive multi-step agent loop against real endpoint."""
import asyncio
import json
import sys
from pathlib import Path

from agent.loop import run_agent_loop
from core.tools import CalculatorTool, MockLookupTool, ToolRegistry


async def main():
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        print("config.json not found!")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    provider_url = cfg.get("provider_url", "http://localhost:20128/v1")
    api_key = cfg.get("api_key", "")
    model = cfg.get("active_model", "antigravity/gemini-3.8-flash-tiered")

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(MockLookupTool())

    task = (
        "Look up the 'unit_cost' and 'item_count' in the database, and then calculate "
        "the total inventory valuation by multiplying them together. Also apply a 10% discount to that total."
    )

    print("================================================================================")
    print("RUNNING LIVE AGENT LOOP PROOF")
    print(f"Endpoint: {provider_url}")
    print(f"Model: {model}")
    print(f"Task: {task}")
    print("================================================================================\n")

    events = []
    async for event in run_agent_loop(
        instruction=task,
        registry=registry,
        provider_url=provider_url,
        api_key=api_key,
        model=model,
        max_steps=8,
    ):
        events.append(event)
        ev_type = event.get("type")

        if ev_type == "tool_call":
            step = event.get("step")
            tool_name = event.get("tool_name")
            status = event.get("status")
            args = event.get("args")
            summary = event.get("result_summary")
            if status == "running":
                print(f"[STEP {step}] -> Tool Call Requested: {tool_name}({json.dumps(args)})")
            else:
                print(f"[STEP {step}] <- Tool Result ({status}): {summary}")

        elif ev_type == "thought":
            step = event.get("step")
            thought = event.get("content", "").strip()
            print(f"[STEP {step}] [Reasoning]: {thought[:160]}..." if len(thought) > 160 else f"[STEP {step}] [Reasoning]: {thought}")

        elif ev_type == "plan_artifact":
            print(f"[Plan Artifact Table Emitted]: Columns={event.get('columns')}, Rows={len(event.get('rows', []))}")

        elif ev_type == "final_answer":
            step = event.get("step")
            converged = event.get("converged")
            content = event.get("content", "")
            print(f"\n[STEP {step}] [FINAL ANSWER (converged={converged})]:\n{content}\n")

        elif ev_type == "done":
            print(f"[DONE] Session: {event.get('session_id')}, Converged: {event.get('converged')}")

        elif ev_type == "error":
            print(f"[ERROR] {event.get('message')}")

    print("\n================================================================================")
    print("EXECUTION COMPLETED")
    print("================================================================================")


if __name__ == "__main__":
    asyncio.run(main())
