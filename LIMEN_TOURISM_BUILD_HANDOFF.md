# Hermes build handoff — Limen Tourism Management Agent

Implement this now in `P:\Magnanimity\Projects\Limen`. You are the engineering agent responsible for delivering a working hackathon prototype. Approximately two hours remain. Work autonomously, make reasonable reversible decisions, and finish implementation and validation rather than stopping at a plan.

## Existing product and boundaries

The user has completed Limen's frontend and previously built a custom agent loop with FastAPI, SSE streaming, tool invocation, and session state. Inspect the current repository and applicable instructions to establish what actually exists. Preserve the finished visual design, working architecture, selected model/provider, event protocol, and unrelated user changes. Integrate tourism capabilities into the existing tool registry and UI. Do not rebuild the frontend, migrate frameworks, add another agent framework, or repeat the earlier design audit.

Use the actual repository files and supported tools. If the Windows path is unavailable, find an explicitly mapped checkout in the current workspace; otherwise report the access blocker. Do not pretend a scratch directory is the product repository. Do not publish, deploy externally, commit secrets, or make purchases as part of this task.

The competition requires a live demonstrable prototype, explainable API calls and retrieved context, and at least two autonomous capabilities. Implement dynamic tool selection, persistent memory, and a correction loop grounded in changed tool results. A fixed sequence hidden behind a chat interface is insufficient.

Acceptance of pre-event code and simulated data by organizers has not been established. This is a technical build instruction, not a claim of competition compliance. Continue implementing useful functionality without waiting for that clarification; report simulation-dependent coverage explicitly.

## Product scope

Build a tourism decision agent for ONE demo city, defaulting to Visakhapatnam, India, with timezone `Asia/Kolkata`. Make the city configurable; prioritize useful coverage in the demo city rather than global completeness. It serves tourists, tourism businesses, and authorities through the existing interface.

Cover every mandatory question with a real implemented workflow:

| # | Question | Required behavior |
|---|---|---|
| 1 | Which places are open now and less crowded? | Evaluate local opening schedules and closure overrides; rank by fresh crowd/capacity readings; expose unknowns |
| 2 | What can I visit in one day given weather and travel time? | Build and save a feasible itinerary using preferences, opening windows, weather, visit duration, and travel time |
| 3 | What is the fastest way to reach a destination now? | Compare supported route options using available routing data; qualify the answer by modes and routes actually checked |
| 4 | What disruptions affect my trip? | Check weather, traffic/road incidents, and attraction closures; identify affected itinerary stops and alternatives |
| 5 | What accommodation is available within my budget/location? | Query date-specific inventory, occupancy needs, location, and total price; distinguish fixture inventory from real availability |
| 6 | What events happen today or this weekend? | Filter dated, located event records with source links and provenance; interpret dates in the destination timezone |
| 7 | Which attractions have the highest crowds? | Rank both visitor counts and occupancy relative to capacity; explain the distinction |
| 8 | Which destinations may become overcrowded soon? | Compute a short-horizon projection from timestamped readings and flag likely capacity thresholds |
| 9 | When should businesses increase staff/services? | Convert projected demand and configured service-capacity rules into a staffing recommendation |
| 10 | Where should authorities add support? | Prioritize locations using occupancy, projected demand, disruptions, and available resources; save a proposed allocation |

Do not leave placeholder functions or canned answers for any row. When real inputs are unavailable, implement the workflow in an explicitly selected simulation scenario and mark live coverage unavailable. Never imply all ten use external live data.

## Data strategy: live where available, explicit scenarios elsewhere

Use a small adapter layer and the existing database, or SQLite if none exists. Check official API documentation before wiring requests; do not assume remembered response schemas or free quotas are correct.

Candidate sources:

- Open-Meteo geocoding: https://open-meteo.com/en/docs/geocoding-api
- Open-Meteo weather: https://open-meteo.com/en/docs
- Geoapify places: https://apidocs.geoapify.com/docs/places/
- Geoapify platform documentation for routing if using its existing key: https://apidocs.geoapify.com/
- TomTom traffic and routing documentation: https://docs.tomtom.com/
- Google Places, only if already configured: https://developers.google.com/maps/documentation/places/web-service/overview
- Ticketmaster events, only if useful local coverage is verified: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/

Prefer credentials already configured. Never print secret values. Add placeholder environment-variable names to `.env.example` as needed. Keep API keys server-side. Use bounded HTTP timeouts, limited retries, caching, and clear error propagation. Spend at most 10 minutes checking integration access and coverage before committing to the available sources; do not lose the sprint on registration or partner onboarding.

Important limitations:

- A hotel listing is not bookable room availability. Without a connected inventory source, live availability is unknown.
- Road congestion, review counts, and place popularity are not measured attraction crowds.
- Published opening hours indicate scheduled opening, not verified absence of an emergency closure.
- Ordinary routing estimates do not establish current traffic or the fastest route across every transport mode.
- Event search returning no records means no events were found in that source, not that no events exist.
- Out-of-range weather dates must not receive fabricated forecasts.

Create a small deterministic scenario dataset: approximately 8–12 attractions, 4–6 accommodations, several dated events, visitor readings over time, service-capacity rules, resource inventory, and disruption records. Real place names/coordinates should come from available sources. Mark synthetic counts, prices, schedules, events, capacities, inventory, and incidents as simulated individually. Use fictional demo accommodation/event names when inventing inventory to avoid attributing false offers to real businesses.

Implement explicit live and scenario modes. A live API error must produce unavailable/stale data, not silently switch to simulated success. Scenario mode may combine live weather with simulated operational feeds only when each input is visibly labelled. Keep scenarios repeatable and separate from genuine observations.

Every relevant tool result and stored observation must expose source/provider or fixture ID, source URL where available, observed/effective time, retrieval time, provenance (`live`, `operator_entered`, `simulated`, `cached`), and uncertainty/staleness. Cached data must retain its original provenance and observation timestamp. Derived predictions must inherit whether their inputs are simulated. Never relabel cached or generated information as live by refreshing a timestamp.

## Agent tools and persistent actions

Adapt these responsibilities into the existing registry; combine tools if that keeps the implementation clearer:

- Resolve destination and query places/opening status.
- Fetch weather and disruptions.
- Query route alternatives and durations.
- Query date-specific accommodation inventory and events.
- Read visitor counts/history and compute crowd projections.
- Validate and save an itinerary; retrieve and revise it.
- Compute and save staffing/resource recommendations.

The model chooses tools according to the user request and available evidence. Python/backend code performs arithmetic, filtering, date checks, capacity checks, and persistence. Keep prompts concise and schema-driven. Validate model-supplied IDs and arguments. Do not allow arbitrary model-generated SQL or unrestricted URL fetching.

Persist session preferences, dates, budget and currency, interests, itinerary revisions, observations, and proposed resource plans. Queries from different sessions must not leak into each other. Saving a recommendation is a real local action; distinguish it from dispatching staff, booking rooms, or contacting authorities. No external reservations or dispatches are required.

## Deterministic decision logic

Keep the algorithms simple, inspectable, and honest:

- Opening status uses destination timezone, weekly/overnight schedules, and dated closure overrides. Missing schedule means unknown.
- Itinerary construction filters candidates by preferences and constraints, then uses a simple scoring/greedy heuristic with travel and visit durations. Check arrival/departure against opening windows and total available time. Do not call this globally optimal. If costs are missing, show a partial budget and unpriced items instead of claiming compliance with the full budget.
- Crowd occupancy is visitors divided by configured capacity. Estimate recent net arrivals from readings with actual elapsed time. Project a short horizon, clamp counts at zero, and identify threshold crossings. Require enough fresh readings; otherwise return insufficient data. Clearly label this a simple trend projection, not a trained prediction model.
- Staffing uses explicit configurable visitors-per-staff or workload capacity assumptions. Distinguish total staff needed from additional staff beyond the existing roster.
- Resource recommendations allocate from a finite available pool and never over-assign it. Show assumptions and unserved demand. Treat security/support thresholds as demo policy inputs, not validated safety standards.

## Monitoring and correction loop

Implement monitoring for an active saved itinerary, not only one-shot answers. Reuse a supported background/task mechanism; otherwise add a bounded session-scoped refresh loop with a stop condition. Use a configurable interval, avoid overlapping checks, and limit API/model calls. Fetch observations on schedule; invoke the agent to reconsider the plan only when relevant changes occur.

Backend polling of external sources is compatible with SSE updates to the frontend. Preserve incremental frontend streaming rather than adding full-page refreshes.

Provide a clearly labelled scenario trigger that updates a closure/crowd feed or advances deterministic scenario time. The trigger changes underlying data; it must not directly print a scripted agent response. Monitoring detects the change, the agent invokes appropriate tools, validates an alternative, and saves an updated itinerary. Show what changed and why. A manual “Recheck now” can supplement monitoring but is not a substitute for it.

## Frontend integration

Preserve Limen's completed frontend. Reuse existing execution rows, source disclosures, and schema-driven artifact tables. Add only essential controls/indicators: selected city, data mode, source timestamps, active monitoring status, itinerary revisions, and operational recommendations. Keep scenario controls visibly labelled and separate from ordinary user actions.

Inspect actual SSE names and invocation identity; do not assume an older handoff schema is current. Repeated tool calls must remain separate, status updates must correlate correctly, and tool errors must not appear as successful completion. Display retrieved evidence and concise decision summaries, never fabricated hidden reasoning.

## Time allocation

Use the approximate remaining 120 minutes as a deadline, not a reason to skip verification:

- 0–10: inspect existing integration points, credentials, and city coverage.
- 10–40: implement data adapters, database schema, deterministic scenarios, and basic tools.
- 40–75: implement itinerary validation, projections, operational decisions, and persistent actions.
- 75–95: connect monitoring/replanning and minimal UI additions.
- 95–115: exercise all ten questions and fix core failures.
- 115–120: write concise run instructions and demo script; stop optional work.

Use a small checklist and brief progress updates. Keep one coherent implementation; defer map polish, authentication, payment, booking transactions, broad city coverage, and framework changes. Do not silently drop a mandatory workflow: record any unfinished item explicitly.

## Acceptance checks and demonstration

Run these against actual code. Use isolated fixtures for deterministic edge cases; never present fixture execution as live API validation.

1. Live weather and at least one available place/route source return usable results, or their specific access failures are reported.
2. Each of the ten mandatory questions invokes appropriate tools and returns evidence-backed output or an explicit data limitation.
3. An itinerary is saved and recalled in a later turn; preference changes produce a persisted revision.
4. Monitoring observes a scenario closure and crowd change, triggers tool-based reconsideration, and saves a valid alternative.
5. An unknown opening schedule, stale crowd reading, and unavailable hotel feed remain unknown rather than fabricated.
6. Crowd calculations use the correct timestamps; insufficient history cannot produce a confident projection.
7. Hotel inventory checks every requested night and accounts for guests/rooms and total cost as represented by the source.
8. Resource allocation does not exceed inventory, and infeasible itineraries explain the conflicting constraints.
9. API timeout/failure terminates cleanly, preserves the trace, and does not silently enable simulation.
10. The existing frontend renders tool activity, tables, errors, and final states without session mixing or runtime errors.

Suggested live demo narrative: ask for a weather-aware day plan, save it, revise preferences in a later turn, start monitoring, inject a clearly labelled scenario disruption, watch autonomous replanning, then ask where staffing and transport should increase. Also exercise accommodations and dated events using the declared data mode.

## Deliverables

Write working code in Limen and provide:

- `.env.example` updates with no secret values.
- An idempotent scenario seed/reset command that only resets demo-owned data.
- `TOURISM_DEMO.md`: exact startup commands, data-source setup, scenario controls, and a short demo script.
- `TOURISM_COVERAGE.md`: all ten requirements mapped to implemented tools, verification performed, live/scenario status, and gaps.

Finish with changed files, run commands, tested behavior, required credentials, and any unverified or incomplete requirement. Do not claim full real-world/live-data compliance merely because all ten workflows run on scenarios.

Start by inspecting Limen, then implement. The goal is a working, explainable tourism agent with persistent actions and actual replanning, integrated into the frontend that already exists.
