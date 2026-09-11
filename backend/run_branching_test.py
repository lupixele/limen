"""Branching Verification Test: One task prompt, two different tool-return values.

Verifies that the agent loop's tool-call sequence dynamically diverges based purely
on runtime tool observations and the model's conditional reasoning.
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from agent.loop import run_agent_loop
from core.tools import CalculatorTool, MockLookupTool, ToolRegistry

TASK_PROMPT = (
    "Look up `stock_level`. If it's below `reorder_threshold`, also look up `reorder_threshold` "
    "and calculate how many units to order to reach it. If it's at or above `reorder_threshold`, "
    "just report the current stock level — no further tool calls needed."
)


async def execute_run(run_label: str, stock_val: int, threshold_val: int, cfg: Dict[str, Any]):
    print(f"\n{'=' * 80}")
    print(f"{run_label}")
    print(f"Configuration: stock_level = {stock_val}, reorder_threshold = {threshold_val}")
    print(f"Task Prompt: {TASK_PROMPT}")
    print(f"{'=' * 80}\n")

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    mock_lookup = MockLookupTool()
    mock_lookup.set_value("stock_level", stock_val)
    mock_lookup.set_value("reorder_threshold", threshold_val)
    registry.register(mock_lookup)

    provider_url = cfg.get("provider_url", "http://localhost:20128/v1")
    api_key = cfg.get("api_key", "")
    model = cfg.get("active_model", "antigravity/gemini-3.8-flash-tiered")

    tool_call_sequence: List[Dict[str, Any]] = []
    thoughts: List[str] = []
    final_content = ""

    async for event in run_agent_loop(
        instruction=TASK_PROMPT,
        registry=registry,
        provider_url=provider_url,
        api_key=api_key,
        model=model,
        max_steps=8,
    ):
        ev_type = event.get("type")
        step = event.get("step")

        if ev_type == "tool_call":
            tool_name = event.get("tool_name")
            status = event.get("status")
            args = event.get("args")
            summary = event.get("result_summary")
            if status == "running":
                print(f"[STEP {step}] -> Tool Call Requested: {tool_name}({json.dumps(args)})")
                tool_call_sequence.append({"tool": tool_name, "args": args, "step": step})
            else:
                print(f"[STEP {step}] <- Tool Result ({status}): {summary}")

        elif ev_type == "thought":
            thought_text = event.get("content", "").strip()
            thoughts.append(thought_text)
            print(f"[STEP {step}] [Model Reasoning]: {thought_text}")

        elif ev_type == "final_answer":
            final_content = event.get("content", "")
            print(f"\n[STEP {step}] [FINAL ANSWER (converged={event.get('converged')}]:\n{final_content}\n")

        elif ev_type == "done":
            print(f"[DONE] Session: {event.get('session_id')}, Converged: {event.get('converged')}")

        elif ev_type == "error":
            print(f"[ERROR]: {event.get('message')}")

    return {
        "label": run_label,
        "stock_val": stock_val,
        "tool_calls": tool_call_sequence,
        "final_content": final_content,
        "thoughts": thoughts,
    }


async def main():
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # RUN 1: stock_level = 30 (below threshold 50)
    result_1 = await execute_run("RUN 1: stock_level = 30 (below threshold 50)", stock_val=30, threshold_val=50, cfg=cfg)

    # RUN 2: stock_level = 70 (above threshold 50)
    result_2 = await execute_run("RUN 2: stock_level = 70 (at or above threshold 50)", stock_val=70, threshold_val=50, cfg=cfg)

    # Analysis & Verification
    print(f"\n{'=' * 80}")
    print("BRANCHING VERIFICATION SUMMARY & ASSERTIONS")
    print(f"{'=' * 80}")

    r1_calls = [f"{c['tool']}({c['args'].get('key') or c['args'].get('expression')})" for c in result_1["tool_calls"]]
    r2_calls = [f"{c['tool']}({c['args'].get('key') or c['args'].get('expression')})" for c in result_2["tool_calls"]]

    print(f"Run 1 Tool Calls Sequence ({len(r1_calls)}): {' -> '.join(r1_calls)}")
    print(f"Run 2 Tool Calls Sequence ({len(r2_calls)}): {' -> '.join(r2_calls) if r2_calls else 'None'}")

    # Check Run 1
    has_r1_stock = any(c['tool'] == 'mock_lookup' and c['args'].get('key') == 'stock_level' for c in result_1["tool_calls"])
    has_r1_reorder = any(c['tool'] == 'mock_lookup' and c['args'].get('key') == 'reorder_threshold' for c in result_1["tool_calls"])
    has_r1_calc = any(c['tool'] == 'calculator' for c in result_1["tool_calls"])

    # Check Run 2
    has_r2_stock = any(c['tool'] == 'mock_lookup' and c['args'].get('key') == 'stock_level' for c in result_2["tool_calls"])
    has_r2_reorder = any(c['tool'] == 'mock_lookup' and c['args'].get('key') == 'reorder_threshold' for c in result_2["tool_calls"])
    has_r2_calc = any(c['tool'] == 'calculator' for c in result_2["tool_calls"])

    structural_diff = len(r1_calls) > len(r2_calls)
    pass_condition = (
        has_r1_stock and has_r1_reorder and has_r1_calc and
        has_r2_stock and has_r2_reorder and not has_r2_calc and
        structural_diff
    )

    print("\nVerification Checks:")
    print(f"• Run 1 called mock_lookup(stock_level): {has_r1_stock}")
    print(f"• Run 1 called mock_lookup(reorder_threshold): {has_r1_reorder}")
    print(f"• Run 1 called calculator: {has_r1_calc}")
    print(f"• Run 2 called mock_lookup(stock_level): {has_r2_stock}")
    print(f"• Run 2 called mock_lookup(reorder_threshold): {has_r2_reorder}")
    print(f"• Run 2 skipped calculator (no reorder math needed): {not has_r2_calc}")
    print(f"• Tool-call paths structurally diverged purely on runtime data: {structural_diff}")

    if pass_condition:
        print("\n--> [BRANCHING TEST: PASSED]")
        return 0
    else:
        print("\n--> [BRANCHING TEST: FAILED]")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
