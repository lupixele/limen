# Limen Tourism Management Agent — Demo & Run Guide

## 1. Quickstart & Installation

### Prerequisites
- Python 3.11+
- Windows 11 (Git Bash or MSYS2 recommended for shell commands)
- Running local/remote OpenAI-compatible inference gateway (e.g., Hermes Agent / Antigravity Gateway) providing `antigravity/gemini-3.8-flash-tiered`.

### Dependency Installation
Run from repository root (`P:\Magnanimity\Projects\limen`):
```bash
pip install -r backend/requirements.txt
```
*(Dependencies: `fastapi`, `uvicorn`, `httpx`, `pydantic`, `tzdata`)*

### Launch Backend & Frontend Server
Launch the FastAPI server using the exact command:
```bash
python -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port 8000
```
Open browser to `http://127.0.0.1:8000/` (or port 8011 if configured for alternative local ports).

---

## 2. Configuration & Environment Setup

1. **LLM Gateway Configuration:**
   - Configure via `backend/config.json` or through the frontend **Settings** modal (gear icon).
   - `provider_url`: `http://localhost:20128/v1`
   - `active_model`: `antigravity/gemini-3.8-flash-tiered`
   - `api_key`: Optional depending on gateway authentication.
   - Template provided in `backend/.env.example` and `backend/config.example.json`.

2. **Data Sources & API Credentials:**
   - **Open-Meteo Weather API:** Live queries executed against `https://api.open-meteo.com/v1/forecast` (no API key required).
   - **OSRM Public Routing:** Live driving routes calculated via `https://router.project-osrm.org/` (no API key required).
   - **SQLite Database:** Local persistent database located at `backend/tourism.db` (auto-initialized on startup).

3. **Data Mode Selection:**
   - **Scenario Mode (`DATA_MODE=scenario`, Default):**
     Uses deterministic seeded database records for attractions, simulated crowd sensor feeds, fixture hotel inventories, and municipal service rules. Enables manual scenario disruption injection and state resets.
   - **Live Mode (`DATA_MODE=live`):**
     Connects live Open-Meteo weather and OSRM driving routes. Feeds without live real-world integrations (e.g. live hotel room inventory, real-time physical crowd sensors) are truthfully reported as `UNKNOWN` rather than fabricated. Disruption simulation triggers are disabled in this mode.
   - *Note:* The legacy `DATA_MODE=hybrid` is deprecated and unsupported.

---

## 3. Scenario Controls & Database Reset

- **Scenario Seed / Reset Status:**
  - **Standalone CLI:** *MISSING*. There is currently no standalone command-line script (e.g. `python -m tourism.seeds`) provided in the repository.
  - **Available Reset Mechanisms:**
    1. **Frontend UI:** Click the **"Reset Scenario Data"** button in the top scenario controls strip.
    2. **HTTP API:** Send a POST request to `/api/tourism/reset`:
       ```bash
       curl -X POST http://127.0.0.1:8000/api/tourism/reset
       ```
    3. **Python One-Liner:**
       ```bash
       python -c "import sys; sys.path.insert(0, 'backend'); from tourism.seeds import seed_scenario_data; seed_scenario_data()"
       ```
  - **Disruption Injection:**
    - Click **"Trigger Scenario Disruption"** in the top bar to simulate an emergency maintenance closure of the INS Kursura Submarine Museum (`ins_kursura`) and induce a crowd spike at the nearby TU 142 Aircraft Museum (`tu_142_museum`).
    - API endpoint: `POST /api/tourism/trigger-scenario`

---

## 4. Key Limitations & Assumptions

1. **Routing Adapter (OSRM):**
   - Public OSRM routing (`router.project-osrm.org`) only supports the **driving** car profile on the public demo server.
   - Walking transit uses an internal geometric Haversine calculation (average speed 4.5 km/h) marked with `fallback` provenance.
   - OSRM does **not** provide live real-time traffic congestion; traffic delays are calculated deterministically when road incident disruptions exist.
2. **Accommodations Inventory:**
   - Hotel listings and room inventories are synthetic fixture records in SQLite (`accommodation_inventory`). In `live` mode, real-time bookable availability is reported as unknown.
3. **Crowd Readings & Projections:**
   - Physical visitor counts and sensor readings are simulated. Surge projection requires at least two historical readings to establish trend; otherwise, low-confidence warning is returned.
4. **Events:**
   - Events are curated demo records for Visakhapatnam in `Asia/Kolkata` timezone. External ticketing/discovery APIs (e.g. Ticketmaster) are not currently connected.

---

## 5. Live Demonstration Script

Execute the following steps in sequence in the web interface:

### Step 1: Query Open Places & Crowds
- **Prompt:** `Which attractions in Visakhapatnam are open right now and have low crowds?`
- **Observed Behavior:** Agent executes `query_open_places` with `max_crowd_pct=50`. Returns tabular artifact ranking attractions by current occupancy percentage and schedules. Note that Ross Hill Viewpoint is flagged with schedule `UNKNOWN`.

### Step 2: Build & Save a Weather-Aware Itinerary
- **Prompt:** `Plan a 1-day itinerary for Visakhapatnam visiting Kursura Submarine Museum and Kailasagiri, accounting for weather and travel times.`
- **Observed Behavior:** Agent fetches live Open-Meteo weather via `build_itinerary`, verifies attraction opening windows, computes driving times via OSRM, and saves the itinerary to the active session. The itinerary table displays sequential stops and arrival windows.

### Step 3: Fast Route Comparison
- **Prompt:** `What is the fastest way to get from RK Beach to Kailasagiri right now?`
- **Observed Behavior:** Agent calls `calculate_route(origin="rk_beach", destination="kailasagiri")`. Outputs a comparison table showing Driving/Taxi (OSRM route) vs Walking, along with distance and active road status.

### Step 4: Revise User Preferences
- **Prompt:** `Update my preferences: budget 1500 INR, pace relaxed, prefer museums and coastal parks.`
- **Observed Behavior:** Agent calls `update_preferences`, persisting updated constraints into SQLite `user_preferences` for the active session.

### Step 5: Start Autonomous Monitoring & Inject Disruption
1. In the header status bar, click **"Start Monitor"** (connects to `/api/tourism/monitor/stream`).
2. Click **"Trigger Scenario Disruption"** (injects emergency electrical closure for INS Kursura).
3. **Observed Behavior:** Background monitor detects the emergency closure of `ins_kursura`, marks the itinerary as unhealthy, and executes an autonomous replan proposing an alternative stop (TU 142 Aircraft Museum or Kailasagiri) without manual user intervention.

### Step 6: Query Accommodations & Events
- **Prompt:** `What hotels are available near the beach for 2 guests under 4000 INR per night for tomorrow?`
- **Observed Behavior:** Agent calls `query_accommodations` checking per-night room inventory, calculating total stay cost, and clearly disclosing fixture source provenance.
- **Prompt:** `What cultural or festival events are scheduled for this weekend?`
- **Observed Behavior:** Agent calls `query_events`, returning scheduled events in `Asia/Kolkata` time with source links.

### Step 7: Operational Decisions (Staffing & Authority Allocation)
- **Prompt:** `Which attractions need increased business staffing due to crowd surges?`
- **Observed Behavior:** Agent calls `recommend_staffing`, combining projected visitor surges with configured service-capacity ratios (e.g. ticket counters, docents, lifeguards).
- **Prompt:** `Where should municipal authorities deploy emergency patrols and shuttle buses?`
- **Observed Behavior:** Agent calls `allocate_authorities_resources`, prioritizing hotspots under surge or closure, allocating available patrol and transit inventory without exceeding limits, and saving the allocation record.
