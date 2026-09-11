"""Generic and Domain-Enhanced System Prompts and Schemas for Autonomous Agent Loop."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

TZ_KOLKATA = ZoneInfo("Asia/Kolkata")

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

TOURISM_DOMAIN_INSTRUCTIONS = """
You are the Limen Tourism Decision and Management Agent for Visakhapatnam, India (Timezone: Asia/Kolkata).
You serve tourists, local tourism businesses, and municipal authorities with grounded, real-time decision intelligence.

CRITICAL OPERATIONAL RULES:
1. Ground every statement in tool output. Never fabricate place hours, weather forecasts, crowd headcounts, or room rates.
2. Opening status: If schedule is missing, explicitly report it as UNKNOWN rather than assuming open or closed. Respect emergency closures immediately.
3. Crowd metrics: Always distinguish absolute headcount (e.g. 2,100 visitors) from percentage capacity occupancy (e.g. 85% density). Projections require historical sensor readings; if only 1 reading exists, report insufficient history.
4. Accommodations: Accommodation inventory is date-specific. Distinguish demo scenario inventory from live bookable supplier feeds.
5. Finite Resources: When recommending municipal resource allocations, strictly honor the finite resource pool (never over-allocate). Report unserved demand.
6. Infeasible plans: If weather, closures, or budget conflict with a request, clearly explain the constraints and suggest viable alternatives.
7. SESSION BOUNDARY & ISOLATION: Operate strictly within the active session. Never request, access, or modify data from other sessions.
"""


def build_system_prompt(
    tools: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
    include_tourism_context: bool = True,
) -> str:
    """Builds a comprehensive system prompt optionally detailing available tools and domain context."""
    base = SYSTEM_PROMPT.strip()

    sections = [base]

    if include_tourism_context:
        now_kolkata = datetime.now(TZ_KOLKATA)
        now_str = now_kolkata.strftime("%Y-%m-%d %I:%M %p (%A)")
        tourism_ctx = (
            f"{TOURISM_DOMAIN_INSTRUCTIONS.strip()}\n\n"
            f"CURRENT ENVIRONMENT CONTEXT:\n"
            f"- Default Destination: Visakhapatnam, Andhra Pradesh, India (ID: 'vizag')\n"
            f"- Destination Timezone: Asia/Kolkata (IST)\n"
            f"- Local Datetime: {now_str}\n"
        )
        if context:
            if isinstance(context, dict):
                ctx_lines = []
                sess_id = context.get("session_id")
                if sess_id:
                    ctx_lines.append(f"- Active Session ID: {sess_id}")
                pref = context.get("preferences")
                if isinstance(pref, dict) and pref:
                    items = []
                    if pref.get("target_city"):
                        items.append(f"City: {pref['target_city']}")
                    if pref.get("target_date"):
                        items.append(f"Date: {pref['target_date']}")
                    if pref.get("budget_limit"):
                        items.append(f"Budget: {pref['budget_limit']} {pref.get('budget_currency', 'INR')}")
                    if pref.get("party_size"):
                        items.append(f"Party Size: {pref['party_size']}")
                    if pref.get("interests"):
                        items.append(f"Interests: {pref['interests']}")
                    if items:
                        ctx_lines.append(f"- Saved Tourist Preferences: {', '.join(items)}")
                itin = context.get("active_itinerary")
                if isinstance(itin, dict) and itin:
                    ctx_lines.append(
                        f"- Current Active Itinerary: [ID: {itin.get('itinerary_id')}, Version: {itin.get('version')}, "
                        f"Status: {itin.get('status')}, Cost: INR {itin.get('total_cost')}] Summary: {itin.get('summary')}"
                    )
                if ctx_lines:
                    tourism_ctx += "\n".join(ctx_lines) + "\n"
                else:
                    tourism_ctx += f"- Active Session Context: {context}\n"
            else:
                tourism_ctx += f"- Active Session Context: {context}\n"
        sections.append(tourism_ctx)

    if tools:
        tool_lines = []
        for t in tools:
            fn = t.get("function", {})
            name = fn.get("name", "unknown")
            desc = fn.get("description", "")
            tool_lines.append(f"- `{name}`: {desc}")
        tools_desc = "\n".join(tool_lines)
        sections.append(f"Available Tools:\n{tools_desc}")

    return "\n\n".join(sections) + "\n"


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
