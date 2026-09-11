# Limen — Frontend Design and Implementation Handoff

You are the lead product designer and frontend implementer for **Limen**, a domain-neutral autonomous agent harness. Create and implement one coherent, distinctive interface for its live AI Agent Challenge 2K26 demo on **11–12 September 2026**.

Work autonomously in one continuous workflow. Make the design decisions yourself; do not pause between sections for approval or ask me to choose from superficial themes. Inspect, design, implement, and validate. The primary deliverable is a working frontend, supported by a concise design-system document.

## Project boundaries and source of truth

- **Working product:** `P:\Magnanimity\Projects\Limen`
- **Completed design audit:** `P:\Magnanimity\Projects\Harness\FRONTEND_DESIGN_AUDIT.md`
- **Research workspace:** `P:\Magnanimity\Projects\Harness`

Read the full audit and inspect the actual Limen frontend, backend event producer, and stream consumer before changing the interface. Harness contains research; implement in Limen. If these paths are unavailable, report that exact access limitation rather than claiming to have inspected them.

Resolve conflicts using these rules:

1. This brief defines the intended product, scope, and deliverables.
2. The current Limen source defines the actual integration contract and available capabilities. Identify discrepancies with this brief explicitly.
3. The audit supplies reference evidence and suggestions; its proposed layout is not a product requirement.
4. Earlier mockups and assistant-written handoffs are historical context, not additional mandatory features.

The existing frontend is a functional/mock baseline, not an established visual identity. Preserve the **dark-theme direction** and working behavior; you may redesign its composition, palette, typography, spacing, and interactions substantially.

## Product objective

The problem statement is unknown. Limen must accept a task and represent arbitrary tools without assuming coding, file organization, research, or another domain.

The backend has been reported as a working FastAPI agent loop with SSE streaming, tool selection, decisions based on tool results, and honest failure handling. Preserve that behavior and verify the integration locally; do not treat historical test claims as current validation.

The competition excludes basic chatbots. Within roughly ten seconds, a judge should be able to identify:

- the user's task;
- the current action and its status;
- the results or errors already observed;
- whether the run is ongoing, complete, or incomplete.

Make the execution trace a primary part of the interface. Keep activity summaries visible; progressively disclose lengthy arguments and raw output. A conversation/composer is appropriate, but agent activity must remain legible without opening a debug panel.

## Design authorship and reference evidence

Create a visual language that belongs to Limen. Learn proportion, hierarchy, density, and interaction craft from the references without copying their layouts or assembling a collage of their components.

The name may inform a subtle relationship between intention, action, and outcome. This is optional inspiration, not a requirement for threshold graphics, portal imagery, or a predetermined motif.

Choose a clear design thesis and express it through a few consistent decisions: typography, alignment, surface boundaries, execution-state treatment, and composer integration. Distinctiveness should survive removal of the logo and accent color.

Avoid default dashboard composition, repeated oversized cards, empty hero space, ornamental AI symbols, decorative glow, and motion that does not explain state. These are quality criteria, not a blanket ban on particular colors, curves, or expressive design. Use restraint without making the product anonymous.

Use the audit's actual evidence. Reported examples include 28px controls, 24px compact controls, 4px/6px radii, and fast transitions around 85–100ms. These are **claims to trace to the audit/source**, not universal standards or mandatory Limen values. Do not assume the audit's summary proves every measurement.

For the important adopted values, document:

| Limen token or pattern | Chosen value | Evidence and source | Adaptation rationale |
|---|---|---|---|

Distinguish directly verified source values, audit-reported values, estimates, and original decisions. Use exact source paths and selectors/tokens when available; never invent citations. Verify high-impact claims selectively rather than repeating the entire audit. If evidence is unavailable, label the limitation and make a reasoned original choice.

Build a compact CSS token system for surfaces, text, accent and semantic states, typography, spacing, borders, radii, control geometry, icons, and motion. Define tokens for components you actually implement. Validate readability and browser rendering instead of copying tiny text, half-pixel borders, or native titlebar dimensions uncritically.

## Scope and implementation constraints

Deliver the frontend in **HTML, CSS, and JavaScript with no newly required build step**, preserving the existing zero-bundling approach. Inspect the repository first. If it already differs, document the discrepancy and integrate with its working architecture without introducing a framework migration or dismantling unrelated infrastructure.

Preserve existing SSE streaming, session behavior, and supported controls. Render incrementally without polling or full-page refreshes. Keep dependencies minimal and avoid new runtime network dependencies for cosmetic assets where practical.

Remove obsolete file-organizer UI and copy: folder-scope modal, directory tree/browser, OS folder presets, filesystem-specific placeholders, and “Revert Previous Run.” Check their wiring before removing frontend references; do not delete unrelated backend capabilities.

Use neutral task language such as “Describe the task.” Tool names and content must come from events, not tool-specific CSS, hardcoded branches, or domain-specific templates. Structured-data rendering may depend on data shape, not a tool's identity.

Implement the needed shell, session navigation, composer, execution stream, tool details, structured tables, final output, and run states. An artifact inspector is optional if it materially improves the real data flow.

Do not add an IDE, file tree, diff engine, PTY terminal, docking system, approval workflow, model selector, attachments, or workspace tabs merely because a reference has them. Retain supported product controls where useful; only add capabilities grounded in the current contract and task. Future possibilities belong in a short deferred note, not inactive controls or simulated functionality.

## Event contract and truthful rendering

The earlier brief supplied these representative event shapes:

```json
{"type":"tool_call","step":3,"tool_name":"string","status":"running","args":{},"result_summary":"string"}
{"type":"thought","step":3,"content":"string"}
{"type":"plan_artifact","columns":["string"],"rows":[{}]}
{"type":"final_answer","step":4,"content":"string","converged":true}
{"type":"done","session_id":"string","converged":true}
```

`tool_call.status` can be `running`, `success`, or `error`. The audit summary also mentions `tool_start`, `tool_result`, `content`, and `status`. Those names are not automatically interchangeable.

Inspect the current producer and consumer. Record the actual event-to-UI mapping, including whether text is appended or replaced and how calls are correlated. Use a small frontend adapter if necessary; do not silently change the backend protocol to fit a mockup.

Required behavior:

- **Tool running:** show the tool name, running state, and meaningful available arguments. Long details may expand.
- **Tool success:** update the corresponding invocation and keep its result summary visible without a click.
- **Tool error:** show a distinct failure state and the reported error. Keep any following `thought` or final output nearby so the agent's response is understandable. Do not claim recovery, retry, or graceful termination until events establish it.
- **Repeated tools:** key by session/run and invocation identity, using step when the contract guarantees uniqueness. A repeated tool name must create a separate invocation; a status update must update its own invocation. Do not collapse unrelated calls together.
- **Thought:** display backend-provided user-facing activity text compactly, with access to longer content. Do not invent reasoning, infer hidden decisions, or manufacture summaries the backend did not provide.
- **Plan artifact:** render the supplied columns and rows generically. Handle empty data, long values, and large/wide tables without breaking the workspace. Keep an understandable artifact summary in the trace if details open elsewhere.
- **Final answer:** present the actual output with clear visual hierarchy. Preserve the meaning of `converged`; an answer's presence alone does not establish successful task completion.
- **Done:** finish the run according to the verified contract, preserve its session identity, and clear active indicators appropriately. Distinguish loop termination, convergence, and task outcome.
- **Non-convergence:** preserve the partial trace and show a clear incomplete state. Say “Step limit reached” only when the backend contract or explicit data establishes that cause; otherwise use neutral wording such as “Run ended without convergence.”
- **Transport failure:** distinguish an interrupted/disconnected stream from a tool error and from confirmed completion. Never infer success from EOF or a stopped spinner.

Do not invent durations, progress percentages, diff counts, citations, or success summaries. If local elapsed time is useful, label it as elapsed time rather than reported tool duration. Render streamed content safely as data; preserve any existing safe Markdown handling.

## Interaction and layout quality

Optimize for a laptop browser and projected live demo. Balance compact controls with readable execution text. Use developer-tool discipline without assuming an IDE or native desktop shell.

The idle interface should be ready for work. During a run, the current action should be easy to locate. Completed evidence should remain scannable, with failures and incomplete outcomes unmistakable.

Define and implement:

- composer submission, multiline entry, focus, and in-progress behavior;
- session switching that prevents events from one run appearing in another;
- disclosure controls accessible by keyboard and pointer;
- stream scrolling that follows new activity when appropriate, respects manual scrolling, and offers a return to the latest event;
- overflow rules for long tool names, arguments, results, and tables;
- narrow-window behavior that collapses optional regions before squeezing the trace;
- readable contrast, visible focus, text/icon status cues, adequate hit areas, and reduced-motion behavior.

Expose Stop, Retry, or other action controls only when their actual semantics are supported. Closing a stream is not proof that server execution was cancelled.

## Deliverables and validation

Complete all of the following in the same workflow:

1. **Working frontend changes in Limen**, integrated with the actual backend and covering the required event states.
2. **`P:\Magnanimity\Projects\Limen\LIMEN_DESIGN_SYSTEM.md`**, documenting the design thesis, important evidence and adaptations, implemented CSS tokens, component/state rules, actual event mapping, responsive behavior, and any deferred scope. Keep it useful to the next implementer; do not produce an encyclopedia of unused components.
3. **Visual evidence of the implemented UI**, including idle, active execution, success, tool failure with subsequent reported output, non-convergence, and a structured table. Capture at a representative laptop size and a narrower viewport. Clearly label fixture-driven states.
4. **A concise completion report** listing changed files, how to run the frontend, what was verified against the real backend, and any remaining limitations.

Exercise the real SSE integration where available. Use isolated deterministic fixtures for hard-to-trigger states, repeated invocations, and large data; never present them as live agent execution. Confirm that unfamiliar tool names and table columns render without special-case changes. Check streaming updates, session isolation, terminal states, overflow, keyboard use, and console/runtime errors.

If a required service or tool is unavailable, finish the parts you can and report exactly what remains unverified. Do not substitute a static mockup or design document for the implemented frontend, and do not claim tests or screenshots you did not produce.

The outcome should be a distinctive, coherent Limen interface whose visual polish makes the agent's real work easier to understand. Make the creative decisions confidently while keeping the scope, integration, and execution evidence honest.
