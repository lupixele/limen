"""Generic System Prompts and Schemas for Autonomous Agent Loop."""
from typing import Any, Dict, List, Optional

SYSTEM_PROMPT = """You are an autonomous problem-solving agent equipped with a set of specialized tools.

Your primary objective is to fulfill the user's request through an adaptive decide-act-observe loop:
1. Reason carefully about what information is required to solve the task.
2. Select appropriate tools to call, choosing the order and arguments based on the problem state.
3. GROUNDING REQUIREMENT: You MUST explicitly call every tool referenced in your reasoning or task conditions before using its value in a decision or comparison. Never assume, guess, or assert a fact or threshold about any lookup key or variable without a corresponding tool call in the same trace to retrieve it.
4. If a condition requires comparing values (such as comparing a stock level to a reorder threshold), you must ensure each value involved in the comparison is retrieved via a tool call before evaluating the condition.
5. Observe the tool execution outputs and incorporate verified facts into your reasoning.
6. When you have sufficient information to answer completely, conclude with a direct, comprehensive final answer.
7. If the task calls for a structured plan, schedule, or table, you may optionally provide a structured table breakdown with columns and rows.
"""


def build_system_prompt(tools: Optional[List[Dict[str, Any]]] = None) -> str:
    """Builds a comprehensive system prompt optionally detailing available tools."""
    base = SYSTEM_PROMPT.strip()
    if not tools:
        return base

    tool_lines = []
    for t in tools:
        fn = t.get("function", {})
        name = fn.get("name", "unknown")
        desc = fn.get("description", "")
        tool_lines.append(f"- `{name}`: {desc}")

    tools_desc = "\n".join(tool_lines)
    return f"{base}\n\nAvailable Tools:\n{tools_desc}\n"


def build_user_prompt(
    files: Optional[List[Dict[str, Any]]] = None,
    user_instruction: Optional[str] = None,
    instruction: Optional[str] = None,
) -> str:
    """
    Constructs the user message payload.
    Supports both generic prompt passing and backward-compatible legacy signatures.
    """
    text = instruction or user_instruction or ""
    if files:
        # Legacy fallback if files are passed
        file_paths = [f.get("path", "") for f in files if isinstance(f, dict)]
        return f"{text}\n\nContext items: {file_paths}".strip()
    return text.strip()
