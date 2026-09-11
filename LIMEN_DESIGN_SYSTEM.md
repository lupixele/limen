# Limen Design System: Precision Monolith

**Authoritative Specification for Limen Autonomous Agent Workbench**  
*Document Version:* 3.1.0  
*Target Product:* `P:\Magnanimity\Projects\Limen`  
*Research & Specification Reference:* `P:\Magnanimity\Projects\Harness\FRONTEND_DESIGN_AUDIT.md`  

---

## 1. Executive Summary & Design Thesis

Limen is a domain-neutral autonomous agent harness and engineering workstation. Its design grammar—**"Precision Monolith"**—rejects consumer chatbot tropes (playful pastel gradients, electric-blue glow, giant marketing hero cards, floating rounded chat bubbles, and hidden mechanics) in favor of high-density, industrial developer-tool discipline.

### Core Principles
1. **Zero AI Slop**: Elimination of decorative gradients, neon glow, gratuitous glassmorphism, and oversized rounded corners.
2. **Dense & Predictable Geometry**: 4px base spacing grid, strict 24px/28px/36px control heights, 4px/6px border radii, and 13px base typography with 11px monospace telemetry.
3. **Split Workbench Architecture**: Replaces the single-column centered chat layout (which leaves 60% of wide desktop displays empty) with an invertible split workstation: 580px execution trace on the left, and a flex-1 inspector/artifact workbench on the right.
4. **Layered Dark Charcoal Surfaces**: Replaces harsh `#000000` AMOLED black with deep neutral graphite tiers (`#0E0F12` canvas $\rightarrow$ `#121418` titlebar/rail $\rightarrow$ `#16181E` sidebar/inspector $\rightarrow$ `#1C1F26` cards/composer surface).
5. **Sub-Pixel Alpha Demarcation**: 1px borders using subtle white alphas (`rgba(255, 255, 255, 0.06–0.16)`) providing crisp visual segmentation without heavy divider lines.
6. **Purposeful Semantic Accents**: Color is strictly reserved for meaning (Green = success/converged, Red = error/interrupted, Amber = warning/step limit, Cyan = tool telemetry, Violet = reasoning).

---

## 2. Shell & Workbench Architecture

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ TITLEBAR: Height 36px (h-9)                                                                            │
│ [Limen Glyph] [Project: Limen Core] │ [Session 1 ✕] [Session 2] [+] │ [⚡ Gemini 3.8 ▼] [Ping] [Inspector] [⚙]│
├────────┬─────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│ RAIL   │ SIDEBAR: 240px              │ STREAM PANE: 580px             │ INSPECTOR WORKBENCH: Flex-1    │
│ 44px   │                             ├────────────────────────────────┼────────────────────────────────┤
│        │ ┌─────────────────────────┐ │ SUB-HEADER: run / <title>      │ TABS: [Artifacts] [Tools] [SSE]│
│ 💬     │ │ Execution Runs          │ ├────────────────────────────────┼────────────────────────────────┤
│ Runs   │ │   Run #1 (4 turns)      │ │ TIMELINE VIEWPORT (Scroll)     │ [Structured Plan Artifacts]    │
│ ⚡     │ │   Run #2 (2 turns)      │ │   User Task Bubble             │   Metric │ Cost │ Status       │
│ Tools  │ │                         │ │   Turn Block                   │   ───────┼──────┼───────       │
│ 📈     │ └─────────────────────────┘ │     24px Tool Summary Rows     │   Unit   │ $150 │ Verified     │
│ Tele-  │                             │     Reasoning Drawer           │   Total  │ $5670│ Final        │
│ metry  │                             │     Markdown Synthesis Prose   │                                │
│ ⚙      │                             │     Terminal State Banner      │ [Tool Inspector: Args & Out]   │
│ Set    │                             ├────────────────────────────────┤                                │
│        │                             │ COMPOSER DOCK (Anchored)       │ [Live SSE Telemetry Stream]    │
│        │                             │ [Textarea] [⚡ Model] [↵ Run]   │                                │
└────────┴─────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

1. **Titlebar (36px, h-9)**: Houses brand identity, active project pill, draggable/closable session tabs strip, global model picker, gateway connection indicator, inspector toggle, and settings dialog trigger.
2. **Activity Icon Rail (44px)**: Minimalist vertical rail switching between Execution Runs (`💬`), Tool Registry (`⚡`), Live Telemetry (`📈`), and Engine Settings (`⚙`).
3. **Session Sidebar (240px)**: Collapsible list of past runs with turn counts and single-click run deletion.
4. **Execution Stream Pane (580px)**: Fixed-width readability column featuring step counters, user bubbles, progressive tool disclosures, reasoning streams, and terminal outcome banners.
5. **Anchored Composer Surface**: Border-top docked control surface with auto-growing textarea, model selector pill, max-step indicator, keybinding cues (`↵ to send, Shift+↵ for newline`), and execution button.
6. **Inspector & Artifact Workbench (Flex-1, Min 400px)**: Full-height pane with 3 integrated views:
   - **Structured Artifacts Tab**: Renders arbitrary multi-column, multi-row `plan_artifact` tables.
   - **Tool Inspector Tab**: Displays formatted JSON arguments and raw execution outputs with clipboard copy triggers.
   - **SSE Telemetry Tab**: Real-time monospace event log recording streaming server-sent events.

---

## 3. Implemented CSS Custom Property Tokens (Obsidian & Neutral Charcoal)

Replaced all electric-blue or cyan tints with Kimi-calibrated warm obsidian carbon:

```css
:root {
  /* Surfaces & Backgrounds (Exact Kimi Neutral Obsidian Stepping) */
  --bg-canvas: #121212;           /* Pure Kimi foundation background */
  --bg-subtle: #171717;           /* Titlebar, icon rail, sub-headers */
  --bg-surface: #1c1c1c;          /* Sidebars & inspector panels */
  --bg-surface-raised: #222222;   /* Composer card, inputs, elevation */
  --bg-surface-hover: #2a2a2a;    /* Interactive hover states */
  --bg-surface-active: #323232;   /* Pressed / active rows */
  --bg-surface-selected: #2d2d2d; /* Selected tabs / active tree items */
  --bg-overlay: rgba(12, 12, 12, 0.85); /* Dialog backdrop with blur */

  /* Borders & Separators (Clean Sub-Pixel White Alphas) */
  --border-subtle: rgba(255, 255, 255, 0.06);   /* Structural hairline splits */
  --border-default: rgba(255, 255, 255, 0.10);  /* Card outlines, input borders */
  --border-strong: rgba(255, 255, 255, 0.18);   /* Active tabs, hovered cards */
  --border-focus: rgba(255, 255, 255, 0.35);    /* Keyboard focus ring */
  --border-focus-glow: rgba(255, 255, 255, 0.08);

  /* Typography & Foregrounds (Bone White & Neutral Greys) */
  --text-primary: #ededed;        /* Headings, user input, primary labels */
  --text-secondary: #a0a0a5;      /* Assistant prose, tool titles, meta */
  --text-muted: #66666c;          /* Timestamps, shortcuts, inactive icons */
  --text-disabled: #424248;       /* Disabled controls, placeholders */
  --text-link: #e2e2e5;           /* Clickable paths, inspect links */

  /* Monolith Action Buttons (Kimi High-Contrast Bone White) */
  --action-btn-bg: #e8e8ea;
  --action-btn-bg-hover: #ffffff;
  --action-btn-text: #121212;

  /* Functional Semantic Accents (Strictly Meaningful, Never Flooded) */
  --accent-success: #10b981;      /* Goal reached, test passed, tool ok */
  --accent-success-subtle: rgba(16, 185, 129, 0.12);
  --accent-success-text: #34d399;
  --accent-warning: #f59e0b;      /* Running spinner, step limits, caution */
  --accent-warning-subtle: rgba(245, 158, 11, 0.12);
  --accent-warning-text: #fbbf24;
  --accent-danger: #ef4444;       /* Execution error, transport drop */
  --accent-danger-subtle: rgba(239, 68, 68, 0.12);
  --accent-danger-text: #f87171;
  --accent-reasoning: #9d9da8;    /* Muted graphite reasoning process */
  --accent-reasoning-subtle: rgba(255, 255, 255, 0.04);

  /* Dimensions */
  --titlebar-height: 36px;
  --rail-width: 44px;
  --sidebar-width: 240px;
  --stream-pane-width: 580px;
}
```

---

## 4. 4-Tier Progressive Tool Disclosure & Micro-Interactions

Following Section 14 of `FRONTEND_DESIGN_AUDIT.md`:
1. **Tier 1 (24px Inline Summary Row)**:
   - Always visible in stream.
   - **Micro-Interaction 14.2 (Hover Icon-to-Chevron Morph)**: Leading 14px box displays semantic tool glyph by default; on row hover, the icon smoothly crossfades (`100ms ease`) to an expand chevron (`›`).
   - Contains: `[Step N]` `[tool_name]` `[args preview]` `[Status Badge]` `[Inspect ↗ Button]`.
2. **Tier 2 (Visible Result Summary Bar)**:
   - Directly underneath Tier 1 row (`↳ 150` or `↳ 6300`).
   - Surfaces verified execution result without requiring user clicks.
3. **Tier 3 (Inline Quick Payload)**:
   - Clicking the Tier 1 row expands formatted JSON payload inline.
4. **Tier 4 (Crimson Error Alert)**:
   - Injected immediately upon `status === "error"` with exact error message (`DatabaseConnectionTimeout: Gateway failed to respond...`).
5. **Inspector Integration (`Inspect ↗`)**:
   - Clicking `Inspect ↗` shifts focus to the right-hand Inspector Workbench pane, populating full arguments, return payloads, and copy utilities.

---

## 5. Event Contract & State Handling

Limen SSE stream (`POST /api/agent/stream`) mapping:

| Event Type | Attributes | UI Mapping |
| :--- | :--- | :--- |
| `thought` | `content` | DeepSeek-style reasoning drawer (`<details>`) with purple dot indicator |
| `tool_call` (running) | `step`, `tool_name`, `args` | 24px row with cyan running badge and animated spinner |
| `tool_call` (success) | `step`, `tool_name`, `result_summary` | Green `✓ done` badge and visible inline `↳ <summary>` bar |
| `tool_call` (error) | `step`, `tool_name`, `result_summary` | Red `✕ error` badge and crimson error alert block |
| `plan_artifact` | `columns`, `rows` | Tabular artifact container in right inspector workbench |
| `final_answer` (converged) | `content`, `converged: true` | Markdown prose report + green `✓ Goal Reached & Converged` banner |
| `final_answer` (incomplete) | `content`, `converged: false` | Markdown report + amber `⚠ Incomplete — Max Execution Steps Reached` |
| `error` | `message` | Red runtime error banner |
| `done` | `session_id`, `converged` | LocalStorage session persistence + sidebar reload |
| *Stream Drop* | Abrupt EOF / Abort | Red `✕ Transport Drop` terminal banner |

---

## 6. Deterministic Evaluation Fixtures

Available via `window.limenFixtures` or query parameters:
- `?fixture=idle`: Clean industrial workbench idle card with prompt templates.
- `?fixture=running`: In-flight multi-step execution with running spinner and step counter.
- `?fixture=success`: Converged execution with multi-step tool rows, markdown summary, and structured plan artifact in right inspector.
- `?fixture=failure`: Simulated `DatabaseConnectionTimeout` error recovery handled honestly.
- `?fixture=step_limit`: Step guardrail termination state (Max Steps: 8).
