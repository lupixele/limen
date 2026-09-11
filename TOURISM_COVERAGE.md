# Limen Tourism Management Agent — Coverage & Verification Report

## 1. 10-Row Coverage & Tool Mapping

The following 10 mandatory competition workflows are implemented in `backend/tourism/tools.py` and registered in `create_agent_registry()` (`backend/app.py`):

| # | Question / User Workflow | Implemented Tool & Class | Data Mode & Real-World Source Status | Implementation & Verification Status |
|---|--------------------------|--------------------------|---------------------------------------|--------------------------------------|
| 1 | Which places are open now and less crowded? | `query_open_places`<br>`(QueryOpenPlacesTool)` | **Scenario / Sourced**: Sourced attractions coordinates/hours in SQLite; simulated crowd readings. Flags `UNKNOWN` schedules (Ross Hill) and emergency closures truthfully. | Implemented.<br>**Acceptance: NOT YET VERIFIED** (domain test suite under active repair). |
| 2 | What can I visit in one day given weather and travel time? | `build_itinerary`<br>`(BuildItineraryTool)` | **Hybrid (Live + Scenario)**: Live weather via Open-Meteo API; live driving transit via public OSRM API; sourced attraction opening hours and durations. Saves itinerary to SQLite. | Implemented.<br>**Acceptance: NOT YET VERIFIED** (domain test suite under active repair). |
| 3 | What is the fastest way to reach a destination now? | `calculate_route`<br>`(CalculateRouteTool)` | **Live with Fallback**: Live driving via public OSRM API (`router.project-osrm.org`). Walking uses geometric Haversine speed fallback (OSRM demo lacks walking profile). Traffic incidents simulated from disruptions table. | Implemented.<br>**Acceptance: NOT YET VERIFIED** (domain test suite under active repair). |
| 4 | What disruptions affect my trip? | `check_disruptions`<br>`(CheckDisruptionsTool)` | **Hybrid (Live + Scenario)**: Live weather alerts via Open-Meteo; road incidents and attraction closures from SQLite scenario disruptions table. Correlates against saved session itinerary. | Implemented.<br>**Acceptance: NOT YET VERIFIED** (domain test suite under active repair). |
| 5 | What accommodation is available within my budget/location? | `query_accommodations`<br>`(QueryAccommodationsTool)` | **Scenario**: Synthetic hotel inventory in SQLite (`accommodation_inventory`). In `live` mode, real-time booking availability is marked `UNKNOWN` (no live GDS/OTA booking integration). | Implemented.<br>**Acceptance: NOT YET VERIFIED** (domain test suite under active repair). |
| 6 | What events happen today or this weekend? | `query_events`<br>`(QueryEventsTool)` | **Scenario / Curated**: Curated municipal and festival records in `Asia/Kolkata` timezone with source URLs. Live external ticketing API (e.g. Ticketmaster) is not connected. | Implemented.<br>**Acceptance: NOT YET VERIFIED** (domain test suite under active repair). |
| 7 | Which attractions have the highest crowds? | `rank_crowds`<br>`(RankCrowdsTool)` | **Scenario**: Synthetic crowd sensor readings. Accurately distinguishes absolute headcount from percentage occupancy relative to site capacity. | Implemented.<br>**Acceptance: NOT YET VERIFIED** (domain test suite under active repair). |
| 8 | Which destinations may become overcrowded soon? | `project_crowd_surge`<br>`(ProjectCrowdSurgeTool)` | **Scenario**: Deterministic linear projection using timestamped readings (+2h horizon). Refuses high-confidence projections when reading history is insufficient (<2 readings). | Implemented.<br>**Acceptance: NOT YET VERIFIED** (domain test suite under active repair). |
| 9 | When should businesses increase staff/services? | `recommend_staffing`<br>`(RecommendStaffingTool)` | **Scenario**: Business rules logic (`service_rules`) mapping projected visitor surges to specific staffing ratios (counters, docents, lifeguards, security). | Implemented.<br>**Acceptance: NOT YET VERIFIED** (domain test suite under active repair). |
| 10 | Where should authorities add support? | `allocate_authorities_resources`<br>`(AllocateAuthoritiesResourcesTool)` | **Scenario**: Multi-criteria priority ranking based on occupancy, surge warnings, and closures. Allocates finite resources (police, ambulances, buses) within inventory limits and persists plan. | Implemented.<br>**Acceptance: NOT YET VERIFIED** (domain test suite under active repair). |

*Auxiliary Tool:* `update_preferences` (`UpdatePreferencesTool`) persists user budget, speed, and category constraints across turns into `user_preferences`.

---

## 2. Test Suite & Verification Status

### Baseline Regression Test Suite
- **Location:** `backend/tests/` (`test_tools.py`, `test_prompt.py`, `test_loop.py`, `test_api.py`)
- **Status:** **PASS (18/18 tests green)**
- **Coverage:** Core agent tool protocol, AST calculator, mock lookup, prompt construction, decide-act-observe loop, SSE format, and session store.

### Domain Integration Test Suite
- **Location:** `backend/tests/test_tourism.py` (17 tests covering all 10 tools, provenance, and monitor)
- **Status:** **UNDER REPAIR** by domain worker (35 total tests across repository; domain tests encountered runtime exceptions such as missing `timezone` import and schema edge-cases).
- **Current Policy:** In accordance with sprint guidelines, acceptance criteria are marked **NOT YET VERIFIED** until verified by passing test runs.

### Frontend Initial Load
- **Status:** **VERIFIED** — initial UI load on browser (port 8011) executed cleanly with zero JavaScript console errors.

---

## 3. Detailed Acceptance Checks Status

| Check # | Handoff Acceptance Criteria | Current Status | Technical Evidence & Limitations |
|---------|-----------------------------|----------------|-----------------------------------|
| 1 | Live weather and at least one available place/route source return usable results, or specific access failures are reported. | **NOT YET VERIFIED** | `WeatherAdapter` queries live Open-Meteo API. `RoutingAdapter` queries live OSRM public API for driving; returns structured error and fallback provenance on network timeout. |
| 2 | Each of the ten mandatory questions invokes appropriate tools and returns evidence-backed output or explicit limitation. | **NOT YET VERIFIED** | Tools implemented in `backend/tourism/tools.py`. End-to-end multi-step agent test with model loop undergoing peer domain stabilization. |
| 3 | An itinerary is saved and recalled in a later turn; preference changes produce a persisted revision. | **NOT YET VERIFIED** | `BuildItineraryTool` writes to `saved_itineraries` table; `UpdatePreferencesTool` updates `user_preferences` table. Integration test undergoing fix. |
| 4 | Monitoring observes scenario closure & crowd change, triggers tool-based reconsideration, and saves valid alternative. | **NOT YET VERIFIED** | `ItineraryMonitor` (`backend/tourism/monitor.py`) checks attraction health against active disruptions, calling `autonomous_replan()`. Stream wiring under review. |
| 5 | Unknown opening schedule, stale crowd reading, and unavailable hotel feed remain unknown rather than fabricated. | **NOT YET VERIFIED** | `OpeningHoursEvaluator` returns `status: "UNKNOWN"` for Ross Hill (unrecorded schedule). Live hotel check returns unknown availability without live GDS. |
| 6 | Crowd calculations use correct timestamps; insufficient history cannot produce a confident projection. | **NOT YET VERIFIED** | `CrowdProjector.project()` strictly checks reading count: if `< 2`, returns `confidence: 0.20` and `status: "INSUFFICIENT_HISTORY"`. |
| 7 | Hotel inventory checks every requested night and accounts for guests/rooms and total cost as represented by source. | **NOT YET VERIFIED** | `QueryAccommodationsTool` loops across each night between check-in and check-out, summing total cost and validating room capacity against guest count. |
| 8 | Resource allocation does not exceed inventory, and infeasible itineraries explain conflicting constraints. | **NOT YET VERIFIED** | `ResourceAllocator.allocate()` enforces `units_available` ceiling from SQLite `resources` table; does not allocate over available quota. |
| 9 | API timeout/failure terminates cleanly, preserves the trace, and does not silently enable simulation. | **NOT YET VERIFIED** | Adapters use bounded 4.0s timeout with `DataSourceType.FALLBACK` / `UNKNOWN` tags; live mode does not silently fall back to scenario data. |
| 10 | Frontend renders tool activity, tables, errors, and final states without session mixing or runtime errors. | **NOT YET VERIFIED** | Browser UI renders split workbench with collapsible tool cards, table inspector, and telemetry. Zero JS errors on initial load. |

---

## 4. Known Technical Limitations & Gaps

1. **Routing Adapter Limitations:**
   - **Driving Only on Public Server:** Project OSRM demo server (`router.project-osrm.org`) only serves the car profile. Pedestrian/walking calculations fall back to Haversine geometric approximations.
   - **No Real-Time Traffic Sensor:** OSRM does not provide live real-time congestion data. Congestion delays (+12m) are deterministically triggered when incident records exist in SQLite `disruptions`.
2. **Synthetic Data Feeds:**
   - Hotel room counts, attraction crowd sensors, and emergency disruption events are synthetic fixture records in SQLite. They must not be presented as physical IoT or commercial live APIs.
3. **Seed/Reset Tooling Gap:**
   - **Missing CLI:** No standalone CLI script (`python -m tourism.seeds`) exists. Seeding relies on the `/api/tourism/reset` endpoint or manual Python invocation.
4. **Environment Variable Handling:**
   - Backend configuration is primarily managed through `backend/config.json` rather than automatic `.env` ingestion via `python-dotenv`.
