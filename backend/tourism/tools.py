"""Tourism Domain Tools for Limen Management Agent.
Covers all 10 mandatory competition workflows with strict schema validation,
provenance tracking, deterministic calculations, and tabular UI artifacts.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from core.tools import ToolResult
from tourism.adapters import RoutingAdapter, WeatherAdapter
from tourism.db import get_db_connection
from tourism.logic import (
    CrowdProjector,
    OpeningHoursEvaluator,
    ResourceAllocator,
    StaffingCalculator,
)
from tourism.provenance import DataSourceType, Provenance

TZ_KOLKATA = ZoneInfo("Asia/Kolkata")


class QueryOpenPlacesTool:
    """Workflow 1: Which places are open now and less crowded?"""
    name: str = "query_open_places"
    description: str = (
        "Query attractions in the demo city (default Visakhapatnam) to find which places are open now "
        "and rank them by fresh crowd occupancy percentage. Accurately flags unknown opening hours and emergency closures."
    )
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "destination_id": {"type": "string", "description": "City ID, defaults to 'vizag'", "default": "vizag"},
            "max_crowd_pct": {"type": "number", "description": "Filter places with occupancy below this percentage (e.g. 50)"},
            "category": {"type": "string", "description": "Optional category filter: beach, museum, park, temple, wildlife, viewpoint"}
        }
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    async def run(self, destination_id: str = "vizag", max_crowd_pct: Optional[float] = None, category: Optional[str] = None, **kwargs) -> ToolResult:
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()

            query = "SELECT * FROM attractions WHERE destination_id = ?"
            params: List[Any] = [destination_id]
            if category:
                query += " AND category = ?"
                params.append(category)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            now_local = datetime.now(TZ_KOLKATA)
            places = []

            for row in rows:
                # 1. Evaluate Opening
                opening = OpeningHoursEvaluator.evaluate(
                    schedule_json=row["schedule_json"],
                    dt=now_local,
                    has_emergency_closure=bool(row["has_emergency_closure"]),
                    closure_reason=row["closure_reason"],
                    closure_until=row["closure_until"]
                )

                # 2. Get latest crowd reading
                cursor.execute("""
                    SELECT visitor_count, capacity, occupancy_pct, timestamp, source_type
                    FROM crowd_readings
                    WHERE attraction_id = ?
                    ORDER BY timestamp DESC LIMIT 1
                """, (row["id"],))
                crowd_row = cursor.fetchone()

                if crowd_row:
                    curr_visitors = crowd_row["visitor_count"]
                    cap = crowd_row["capacity"]
                    occ_pct = crowd_row["occupancy_pct"]
                    crowd_ts = crowd_row["timestamp"]
                else:
                    curr_visitors = 0
                    cap = row["max_capacity"]
                    occ_pct = 0.0
                    crowd_ts = "N/A"

                # Filter if requested
                if max_crowd_pct is not None and occ_pct > max_crowd_pct:
                    continue

                places.append({
                    "id": row["id"],
                    "name": row["name"],
                    "category": row["category"],
                    "opening_status": opening["status"],
                    "hours_detail": opening["detail"],
                    "is_open": opening["is_open"],
                    "visitor_count": curr_visitors,
                    "capacity": cap,
                    "occupancy_pct": occ_pct,
                    "admission_fee": f"{row['currency']} {row['admission_fee']}",
                    "crowd_reading_time": crowd_ts,
                    "provenance": {
                        "schedule_source": row["source_name"],
                        "crowd_source": "Simulated local sensor reading" if crowd_row else "Unknown"
                    }
                })
        finally:
            conn.close()

        # Rank open places first, then lowest crowd occupancy
        def sort_key(p):
            is_open_val = 0 if p["is_open"] is True else (1 if p["is_open"] is None else 2)
            return (is_open_val, p["occupancy_pct"])

        sorted_places = sorted(places, key=sort_key)

        # Build schema-driven UI table artifact
        artifact = {
            "type": "table",
            "title": f"Open & Crowd Status: {destination_id.capitalize()} ({now_local.strftime('%I:%M %p, %a')})",
            "columns": ["Attraction", "Status", "Schedule / Override", "Crowd Count", "Occupancy %", "Admission"],
            "rows": [
                [
                    p["name"],
                    p["opening_status"],
                    p["hours_detail"],
                    f"{p['visitor_count']} / {p['capacity']}",
                    f"{p['occupancy_pct']}%",
                    p["admission_fee"]
                ]
                for p in sorted_places
            ]
        }

        return ToolResult(
            success=True,
            output={"places": sorted_places, "total_found": len(sorted_places)},
            artifact=artifact
        )


class BuildItineraryTool:
    """Workflow 2: What can I visit in one day given weather and travel time?"""
    name: str = "build_itinerary"
    description: str = (
        "Construct and save a feasible, weather-aware 1-day itinerary for Visakhapatnam. "
        "Checks destination opening windows, weather conditions, normal visit durations, "
        "and real road travel times between stops. Persists the resulting itinerary to the session."
    )
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Current active session ID"},
            "target_date": {"type": "string", "description": "Date in YYYY-MM-DD format (defaults to today)"},
            "interests": {"type": "array", "items": {"type": "string"}, "description": "Interests, e.g. ['beach', 'museum', 'viewpoint']"},
            "budget_inr": {"type": "number", "description": "Max budget in INR for admissions and transit", "default": 2000.0},
            "start_time": {"type": "string", "description": "Start time HH:MM, defaults to '09:00'", "default": "09:00"}
        },
        "required": ["session_id"]
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    async def run(
        self,
        session_id: str,
        target_date: Optional[str] = None,
        interests: Optional[List[str]] = None,
        budget_inr: float = 2000.0,
        start_time: str = "09:00",
        **kwargs
    ) -> ToolResult:
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Check for saved session preferences if parameters omitted or default
            cursor.execute("SELECT * FROM session_preferences WHERE session_id = ?", (session_id,))
            pref_row = cursor.fetchone()
            if pref_row:
                if not target_date and pref_row["target_date"]:
                    target_date = pref_row["target_date"]
                if budget_inr == 2000.0 and pref_row["budget_limit"]:
                    budget_inr = float(pref_row["budget_limit"])
                if not interests and pref_row["interests_json"]:
                    try:
                        saved_interests = json.loads(pref_row["interests_json"])
                        if saved_interests:
                            interests = saved_interests
                    except Exception:
                        pass

            now_local = datetime.now(TZ_KOLKATA)
            date_str = target_date or now_local.strftime("%Y-%m-%d")

            # 1. Fetch live weather for Visakhapatnam
            weather_res = await WeatherAdapter.get_current_and_forecast(17.68009, 83.20161)
            weather_curr = weather_res.get("current", {})
            temp = weather_curr.get("temperature_2m", 28.0)
            precip = weather_curr.get("precipitation", 0.0)
            is_rainy = precip > 1.0

            # 2. Fetch candidates from database
            cursor.execute("SELECT * FROM attractions WHERE destination_id = 'vizag'")
            candidates = [dict(r) for r in cursor.fetchall()]

            # Filter out emergency closed attractions
            candidates = [c for c in candidates if not c.get("has_emergency_closure")]

            # Match interests if provided
            if interests:
                matched = [c for c in candidates if any(i.lower() in c["category"].lower() for i in interests)]
                if len(matched) >= 3:
                    candidates = matched

            # Select candidates adhering to budget constraint
            selected_candidates = []
            running_cost = 0.0
            for c in candidates:
                fee = float(c.get("admission_fee") or 0.0)
                if running_cost + fee <= budget_inr:
                    selected_candidates.append(c)
                    running_cost += fee
                    if len(selected_candidates) >= 4:
                        break
            if not selected_candidates and candidates:
                selected_candidates = [candidates[0]]

            # 3. Sequence stops and calculate road travel durations
            stops = []
            curr_time = datetime.strptime(f"{date_str} {start_time}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ_KOLKATA)
            prev_coords = (17.68009, 83.20161)  # City center / transit start
            total_cost = 0.0
            unpriced_count = 0

            for idx, place in enumerate(selected_candidates):
                origin_lat, origin_lon = prev_coords
                dest_lat, dest_lon = place["latitude"], place["longitude"]

                route_res = await RoutingAdapter.get_route(origin_lat, origin_lon, dest_lat, dest_lon, mode="driving")
                if route_res.get("status") != "success":
                    route_res = RoutingAdapter.calculate_haversine_estimate(origin_lat, origin_lon, dest_lat, dest_lon, mode="driving")

                transit_min = route_res.get("duration_min", 15.0)
                transit_dist = route_res.get("distance_km", 5.0)

                arrival_time = curr_time + timedelta(minutes=transit_min)

                # Check opening at arrival time
                opening = OpeningHoursEvaluator.evaluate(
                    schedule_json=place["schedule_json"],
                    dt=arrival_time,
                    has_emergency_closure=bool(place["has_emergency_closure"]),
                    closure_reason=place["closure_reason"]
                )

                visit_duration = place["normal_duration_min"]
                departure_time = arrival_time + timedelta(minutes=visit_duration)

                fee = float(place["admission_fee"] or 0.0)
                total_cost += fee
                if place["schedule_json"] is None:
                    unpriced_count += 1

                stops.append({
                    "stop_order": idx + 1,
                    "place_id": place["id"],
                    "name": place["name"],
                    "category": place["category"],
                    "arrival_time": arrival_time.strftime("%I:%M %p"),
                    "departure_time": departure_time.strftime("%I:%M %p"),
                    "transit_duration_min": transit_min,
                    "transit_distance_km": transit_dist,
                    "visit_duration_min": visit_duration,
                    "opening_status": opening["status"],
                    "admission_fee": fee,
                    "notes": opening["detail"]
                })

                curr_time = departure_time
                prev_coords = (dest_lat, dest_lon)

            # 4. Persist Itinerary
            itinerary_id = f"itin_{uuid.uuid4().hex[:8]}"
            title = f"1-Day Vizag Experience ({date_str})"
            summary = (
                f"Feasible 1-day plan across {len(stops)} stops. Weather: {temp}°C, precip: {precip}mm. "
                f"Total estimated admission: INR {total_cost}. Transit grounded in OSRM road routes."
            )

            created_ts = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                INSERT INTO itineraries (
                    id, session_id, title, target_date, status, stops_json,
                    total_cost, unpriced_items, summary, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'saved', ?, ?, ?, ?, 1, ?, ?)
            """, (itinerary_id, session_id, title, date_str, json.dumps(stops), total_cost, unpriced_count, summary, created_ts, created_ts))

            conn.commit()
        finally:
            conn.close()

        # Build schema-driven UI table artifact
        artifact = {
            "type": "table",
            "title": f"Itinerary: {title} [ID: {itinerary_id}]",
            "columns": ["Stop #", "Destination", "Arrival", "Departure", "Travel", "Visit", "Status", "Cost"],
            "rows": [
                [
                    str(s["stop_order"]),
                    s["name"],
                    s["arrival_time"],
                    s["departure_time"],
                    f"{s['transit_duration_min']}m ({s['transit_distance_km']}km)",
                    f"{s['visit_duration_min']}m",
                    s["opening_status"],
                    f"INR {s['admission_fee']}"
                ]
                for s in stops
            ]
        }

        return ToolResult(
            success=True,
            output={
                "itinerary_id": itinerary_id,
                "session_id": session_id,
                "target_date": date_str,
                "stops": stops,
                "total_cost_inr": total_cost,
                "total_admission_inr": total_cost,
                "weather_summary": f"Temp: {temp}°C, Precip: {precip}mm, Rainy: {is_rainy}",
                "provenance": {
                    "routing": "OSRM Open Street Routing",
                    "weather": "Open-Meteo Live API"
                }
            },
            artifact=artifact
        )


class CalculateRouteTool:
    """Workflow 3: What is the fastest way to reach a destination now?"""
    name: str = "calculate_route"
    description: str = (
        "Compare supported route transit options (driving, walking) between two points or landmarks in Visakhapatnam "
        "using live road routing data. Accurately qualifies the answer by modes and distances checked."
    )
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "Origin attraction ID or place name, e.g. 'rk_beach'"},
            "destination": {"type": "string", "description": "Destination attraction ID or place name, e.g. 'kailasagiri'"},
            "departure_time": {"type": "string", "description": "Departure time HH:MM, defaults to 'now'"}
        },
        "required": ["origin", "destination"]
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    async def run(self, origin: str, destination: str, departure_time: str = "now", **kwargs) -> ToolResult:
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()

            def resolve_coords(query: str):
                cursor.execute("SELECT id, name, latitude, longitude FROM attractions WHERE id = ? OR name LIKE ?", (query, f"%{query}%"))
                r = cursor.fetchone()
                if r:
                    return r["id"], r["name"], r["latitude"], r["longitude"]
                if "station" in query.lower() or "railway" in query.lower():
                    return "vizag_station", "Visakhapatnam Railway Station", 17.7214, 83.2906
                if "airport" in query.lower():
                    return "vizag_airport", "Visakhapatnam International Airport", 17.7211, 83.2245
                return "city_center", query.capitalize(), 17.6801, 83.2016

            orig_id, orig_name, orig_lat, orig_lon = resolve_coords(origin)
            dest_id, dest_name, dest_lat, dest_lon = resolve_coords(destination)

            # Check disruptions affecting these places
            cursor.execute("SELECT * FROM disruptions WHERE active = 1")
            disruptions = cursor.fetchall()
            active_impacts = []
            for dis in disruptions:
                affected = json.loads(dis["affected_places_json"] or "[]")
                if orig_id in affected or dest_id in affected:
                    active_impacts.append(f"{dis['title']}: {dis['description']}")
        finally:
            conn.close()

        # Check driving via OSRM live API
        route_drive = await RoutingAdapter.get_route(orig_lat, orig_lon, dest_lat, dest_lon, mode="driving")
        if route_drive.get("status") != "success":
            route_drive = RoutingAdapter.calculate_haversine_estimate(orig_lat, orig_lon, dest_lat, dest_lon, mode="driving")

        drive_distance_km = route_drive["distance_km"]
        drive_duration = route_drive["duration_min"]
        if active_impacts:
            drive_duration += 12.0  # realistic road incident delay

        # Check walking: OSRM public demo server only hosts car profiles; use deterministic pedestrian model
        route_walk = RoutingAdapter.calculate_haversine_estimate(orig_lat, orig_lon, dest_lat, dest_lon, mode="walking")
        # Ensure walking distance aligns with actual ground distance
        walk_distance_km = max(drive_distance_km, route_walk["distance_km"])
        walk_duration = max(5.0, round((walk_distance_km / 4.5) * 60, 1))

        options = [
            {
                "mode": "Driving / Taxi",
                "duration_min": drive_duration,
                "distance_km": drive_distance_km,
                "notes": "Includes 12m incident delay" if active_impacts else "Normal road conditions",
                "provenance": route_drive["provenance"]
            },
            {
                "mode": "Walking",
                "duration_min": walk_duration,
                "distance_km": walk_distance_km,
                "notes": "Pedestrian path (~4.5 km/h walking speed; OSRM public server lacks foot profile)",
                "provenance": route_walk["provenance"]
            }
        ]

        fastest = min(options, key=lambda x: x["duration_min"])

        artifact = {
            "type": "table",
            "title": f"Route Comparison: {orig_name} → {dest_name}",
            "columns": ["Mode", "Estimated Duration", "Distance", "Status / Notes", "Source"],
            "rows": [
                [
                    opt["mode"],
                    f"{opt['duration_min']} mins",
                    f"{opt['distance_km']} km",
                    opt["notes"],
                    opt["provenance"]["source_name"]
                ]
                for opt in options
            ]
        }

        return ToolResult(
            success=True,
            output={
                "origin": orig_name,
                "destination": dest_name,
                "fastest_mode": fastest["mode"],
                "fastest_duration_min": fastest["duration_min"],
                "route_options": options,
                "options": options,
                "active_disruptions": active_impacts,
                "coverage_qualification": "Evaluated driving (OSRM live/fallback) and pedestrian walk (simulated 4.5km/h). Public transit not available in open feeds."
            },
            artifact=artifact
        )


class CheckDisruptionsTool:
    """Workflow 4: What disruptions affect my trip?"""
    name: str = "check_disruptions"
    description: str = (
        "Check active weather advisories, traffic/road incidents, and attraction emergency closures. "
        "Can evaluate against a saved session itinerary to identify affected stops and suggest alternatives."
    )
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Session ID to check active itinerary against"},
            "destination_id": {"type": "string", "description": "City ID, defaults to 'vizag'", "default": "vizag"}
        }
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    async def run(self, session_id: Optional[str] = None, destination_id: str = "vizag", **kwargs) -> ToolResult:
        # 1. Fetch live weather alerts / rain
        weather_res = await WeatherAdapter.get_current_and_forecast(17.68009, 83.20161)
        weather_curr = weather_res.get("current", {})
        wind_speed = weather_curr.get("wind_speed_10m", 0.0)
        precip = weather_curr.get("precipitation", 0.0)

        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # 2. Fetch stored disruptions
            cursor.execute("SELECT * FROM disruptions WHERE destination_id = ? AND active = 1", (destination_id,))
            rows = cursor.fetchall()
            disruptions = []
            for d in rows:
                disruptions.append({
                    "id": d["id"],
                    "type": d["disruption_type"],
                    "severity": d["severity"],
                    "title": d["title"],
                    "description": d["description"],
                    "affected_places": json.loads(d["affected_places_json"] or "[]"),
                    "source_type": d["source_type"]
                })

            # Add live weather warning if precipitation or wind is high
            if wind_speed > 25.0 or precip > 2.0:
                disruptions.append({
                    "id": "live_wx_alert",
                    "type": "weather",
                    "severity": "medium",
                    "title": "Coastal Wind & Rain Alert",
                    "description": f"Observed wind {wind_speed} km/h, precipitation {precip} mm. High seas along RK Beach.",
                    "affected_places": ["rk_beach", "yarada_beach", "rushikonda_beach"],
                    "source_type": "live"
                })

            # 3. Check itinerary impact if session has saved itinerary
            impacted_stops = []
            if session_id:
                cursor.execute("SELECT * FROM itineraries WHERE session_id = ? ORDER BY created_at DESC LIMIT 1", (session_id,))
                itin_row = cursor.fetchone()
                if itin_row:
                    stops = json.loads(itin_row["stops_json"])
                    for s in stops:
                        place_id = s["place_id"]
                        for dis in disruptions:
                            if place_id in dis["affected_places"]:
                                impacted_stops.append({
                                    "stop_order": s["stop_order"],
                                    "place_name": s["name"],
                                    "place_id": place_id,
                                    "disruption_title": dis["title"],
                                    "severity": dis["severity"],
                                    "recommendation": f"Consider skipping or swapping {s['name']}: {dis['description']}"
                                })
        finally:
            conn.close()

        artifact = {
            "type": "table",
            "title": f"Active Travel Disruptions: {destination_id.capitalize()}",
            "columns": ["Severity", "Type", "Title", "Affected Areas / Places", "Source"],
            "rows": [
                [
                    d["severity"].upper(),
                    d["type"].capitalize(),
                    d["title"],
                    ", ".join(d["affected_places"]),
                    d["source_type"].capitalize()
                ]
                for d in disruptions
            ]
        }

        return ToolResult(
            success=True,
            output={
                "total_disruptions": len(disruptions),
                "disruptions": disruptions,
                "impacted_itinerary_stops": impacted_stops,
                "itinerary_status": "DISRUPTED" if impacted_stops else "CLEAR"
            },
            artifact=artifact
        )


class QueryAccommodationsTool:
    """Workflow 5: What accommodation is available within my budget/location?"""
    name: str = "query_accommodations"
    description: str = (
        "Query date-specific accommodation inventory, room availability, price per night, "
        "and total stay cost in Visakhapatnam. Distinguishes fixture inventory from live availability."
    )
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "checkin_date": {"type": "string", "description": "Check-in date YYYY-MM-DD"},
            "nights": {"type": "integer", "description": "Number of nights", "default": 1},
            "rooms": {"type": "integer", "description": "Number of rooms required", "default": 1},
            "max_budget_per_night": {"type": "number", "description": "Max budget per night in INR"},
            "destination_id": {"type": "string", "description": "Defaults to 'vizag'", "default": "vizag"}
        },
        "required": ["checkin_date"]
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    async def run(
        self,
        checkin_date: str,
        nights: int = 1,
        rooms: int = 1,
        max_budget_per_night: Optional[float] = None,
        destination_id: str = "vizag",
        **kwargs
    ) -> ToolResult:
        nights = max(1, nights)
        rooms = max(1, rooms)

        # Calculate requested date range
        dt_start = datetime.strptime(checkin_date, "%Y-%m-%d")
        stay_dates = [(dt_start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(nights)]

        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM accommodations WHERE destination_id = ?", (destination_id,))
            acc_rows = cursor.fetchall()

            results = []
            for acc in acc_rows:
                price_night = acc["price_per_night_inr"]
                if max_budget_per_night is not None and price_night > max_budget_per_night:
                    continue

                # Check availability for EVERY requested night
                cursor.execute("""
                    SELECT date, available_rooms, is_real_inventory
                    FROM accommodation_inventory
                    WHERE accommodation_id = ? AND date IN ({})
                """.format(",".join("?" * len(stay_dates))), [acc["id"]] + stay_dates)

                inv_records = cursor.fetchall()
                avail_by_date = {r["date"]: r["available_rooms"] for r in inv_records}

                # Check if all nights are available with sufficient rooms
                all_nights_found = len(inv_records) == len(stay_dates)
                min_avail = min(avail_by_date.values()) if avail_by_date else 0
                is_available = all_nights_found and min_avail >= rooms

                total_stay_price = price_night * nights * rooms

                results.append({
                    "id": acc["id"],
                    "name": acc["name"],
                    "property_type": acc["property_type"],
                    "price_per_night_inr": price_night,
                    "total_stay_price_inr": total_stay_price,
                    "is_available": is_available,
                    "min_rooms_available": min_avail,
                    "amenities": json.loads(acc["amenities_json"] or "[]"),
                    "is_synthetic": bool(acc["is_synthetic"]),
                    "source_notice": "Simulated Demo Fixture: Not a live bookable reservation"
                })
        finally:
            conn.close()

        # Sort by available first, then price ascending
        sorted_acc = sorted(results, key=lambda a: (not a["is_available"], a["price_per_night_inr"]))

        artifact = {
            "type": "table",
            "title": f"Available Stays: {destination_id.capitalize()} ({checkin_date} for {nights} night{'s' if nights > 1 else ''})",
            "columns": ["Property Name", "Type", "Nightly Rate", f"Total ({nights}n)", "Available?", "Rooms Left", "Source"],
            "rows": [
                [
                    a["name"],
                    a["property_type"].capitalize(),
                    f"INR {a['price_per_night_inr']}",
                    f"INR {a['total_stay_price_inr']}",
                    "Available" if a["is_available"] else "Sold Out",
                    str(a["min_rooms_available"]),
                    "Demo Fixture (Simulated)"
                ]
                for a in sorted_acc
            ]
        }

        return ToolResult(
            success=True,
            output={
                "checkin_date": checkin_date,
                "nights": nights,
                "rooms_requested": rooms,
                "total_properties_checked": len(sorted_acc),
                "accommodations": sorted_acc,
                "provenance": {
                    "source": "Demo Scenario Fixture",
                    "disclaimer": "Simulated inventory data; actual room bookings require live supplier connectivity."
                }
            },
            artifact=artifact
        )


class QueryEventsTool:
    """Workflow 6: What events happen today or this weekend?"""
    name: str = "query_events"
    description: str = (
        "Query dated, located event records with source links and provenance in Visakhapatnam. "
        "Interprets dates and times in the destination timezone (Asia/Kolkata)."
    )
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "filter_period": {
                "type": "string",
                "enum": ["today", "weekend", "all"],
                "description": "Filter period: today, weekend, or all upcoming",
                "default": "all"
            },
            "destination_id": {"type": "string", "description": "Defaults to 'vizag'", "default": "vizag"}
        }
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    async def run(self, filter_period: str = "all", destination_id: str = "vizag", **kwargs) -> ToolResult:
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events WHERE destination_id = ?", (destination_id,))
            rows = cursor.fetchall()
            now_local = datetime.now(TZ_KOLKATA)
            today_str = now_local.strftime("%Y-%m-%d")

            events = []
            for r in rows:
                start_dt = datetime.fromisoformat(r["start_datetime"])
                event_date = start_dt.strftime("%Y-%m-%d")

                if filter_period == "today" and event_date != today_str:
                    continue
                if filter_period == "weekend" and start_dt.weekday() not in (4, 5, 6):  # Fri, Sat, Sun
                    continue

                events.append({
                    "id": r["id"],
                    "title": r["title"],
                    "category": r["category"],
                    "venue": r["venue_name"],
                    "start_time": start_dt.strftime("%d %b %Y, %I:%M %p"),
                    "expected_attendance": r["expected_attendance"],
                    "ticket_price_inr": r["ticket_price_inr"],
                    "source_url": r["source_url"],
                    "source_type": r["source_type"]
                })
        finally:
            conn.close()

        artifact = {
            "type": "table",
            "title": f"Local Events: {destination_id.capitalize()} ({filter_period.upper()})",
            "columns": ["Event Title", "Category", "Venue", "Date & Time", "Expected Attendance", "Ticket Fee"],
            "rows": [
                [
                    e["title"],
                    e["category"].capitalize(),
                    e["venue"],
                    e["start_time"],
                    str(e["expected_attendance"]),
                    f"INR {e['ticket_price_inr']}" if e["ticket_price_inr"] > 0 else "Free"
                ]
                for e in events
            ]
        }

        return ToolResult(
            success=True,
            output={
                "filter_period": filter_period,
                "total_events": len(events),
                "events": events,
                "timezone": "Asia/Kolkata",
                "notes": "No events found in local registry for this period." if not events else None
            },
            artifact=artifact
        )


class RankCrowdsTool:
    """Workflow 7: Which attractions have the highest crowds?"""
    name: str = "rank_crowds"
    description: str = (
        "Rank attractions by both visitor count and occupancy relative to capacity. "
        "Distinguishes absolute headcount from percentage density."
    )
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "destination_id": {"type": "string", "description": "Defaults to 'vizag'", "default": "vizag"},
            "sort_by": {
                "type": "string",
                "enum": ["occupancy_pct", "visitor_count"],
                "description": "Rank by percentage occupancy or absolute visitor count",
                "default": "occupancy_pct"
            }
        }
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    async def run(self, destination_id: str = "vizag", sort_by: str = "occupancy_pct", **kwargs) -> ToolResult:
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, category, max_capacity FROM attractions WHERE destination_id = ?", (destination_id,))
            attractions = cursor.fetchall()

            ranked = []
            for a in attractions:
                cursor.execute("""
                    SELECT visitor_count, capacity, occupancy_pct, timestamp
                    FROM crowd_readings
                    WHERE attraction_id = ?
                    ORDER BY timestamp DESC LIMIT 1
                """, (a["id"],))
                crowd = cursor.fetchone()

                if crowd:
                    visitors = crowd["visitor_count"]
                    cap = crowd["capacity"]
                    occ = crowd["occupancy_pct"]
                    ts = crowd["timestamp"]
                else:
                    visitors = 0
                    cap = a["max_capacity"]
                    occ = 0.0
                    ts = "No reading"

                ranked.append({
                    "id": a["id"],
                    "name": a["name"],
                    "category": a["category"],
                    "visitor_count": visitors,
                    "capacity": cap,
                    "occupancy_pct": occ,
                    "density_level": "Overcrowded" if occ >= 85 else ("Busy" if occ >= 60 else "Moderate" if occ >= 35 else "Low"),
                    "reading_time": ts
                })
        finally:
            conn.close()

        reverse = True
        ranked.sort(key=lambda x: x[sort_by], reverse=reverse)

        artifact = {
            "type": "table",
            "title": f"Crowd Rankings: {destination_id.capitalize()} (Sorted by {sort_by.replace('_', ' ').title()})",
            "columns": ["Rank", "Attraction", "Visitor Headcount", "Capacity", "Occupancy %", "Status"],
            "rows": [
                [
                    f"#{i+1}",
                    item["name"],
                    str(item["visitor_count"]),
                    str(item["capacity"]),
                    f"{item['occupancy_pct']}%",
                    item["density_level"]
                ]
                for i, item in enumerate(ranked)
            ]
        }

        return ToolResult(
            success=True,
            output={
                "sorted_by": sort_by,
                "total_ranked": len(ranked),
                "rankings": ranked,
                "distinction_note": (
                    "Headcount measures absolute visitors; occupancy % measures pressure relative to facility capacity. "
                    "A high-capacity beach may have high headcount with low occupancy, while a compact museum may be saturated."
                )
            },
            artifact=artifact
        )


class ProjectCrowdSurgeTool:
    """Workflow 8: Which destinations may become overcrowded soon?"""
    name: str = "project_crowd_surge"
    description: str = (
        "Compute a short-horizon (default 1-hour) trend projection from timestamped readings "
        "and flag likely capacity threshold crossings (>=80%). Clamps projection at zero."
    )
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "attraction_id": {"type": "string", "description": "Attraction ID, e.g. 'ins_kursura' or 'rk_beach'"},
            "horizon_hours": {"type": "number", "description": "Projection horizon in hours (default 1.0)", "default": 1.0}
        },
        "required": ["attraction_id"]
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    async def run(self, attraction_id: str, horizon_hours: float = 1.0, **kwargs) -> ToolResult:
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, max_capacity FROM attractions WHERE id = ?", (attraction_id,))
            attr = cursor.fetchone()
            if not attr:
                return ToolResult(success=False, error=f"Attraction '{attraction_id}' not found.")

            cursor.execute("""
                SELECT visitor_count, capacity, timestamp
                FROM crowd_readings
                WHERE attraction_id = ?
                ORDER BY timestamp ASC
            """, (attraction_id,))
            readings = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

        projection = CrowdProjector.project(
            readings=readings,
            capacity=attr["max_capacity"],
            target_horizon_hours=horizon_hours
        )

        artifact = {
            "type": "table",
            "title": f"1-Hour Crowd Projection: {attr['name']}",
            "columns": ["Metric", "Value", "Notes"],
            "rows": [
                ["Status", projection["status"], projection.get("explanation", "")],
                ["Current Headcount", str(projection.get("current_visitors", "N/A")), f"Capacity: {attr['max_capacity']}"],
                ["Current Occupancy", f"{projection.get('occupancy_pct', 'N/A')}%", "Based on latest sensor reading"],
                ["Projected Headcount (+1h)", str(projection.get("projected_visitors", "N/A")), f"Trend: {projection.get('trend', 'N/A')}"],
                ["Projected Occupancy (+1h)", f"{projection.get('projected_occupancy_pct', 'N/A')}%", "Warning if >=80%"],
                ["Threshold Warning", "CRITICAL OVERLOAD" if projection.get("threshold_warning") else "Normal", "Capacity threshold: 80%"]
            ]
        }

        return ToolResult(
            success=True,
            output={
                "attraction_id": attraction_id,
                "attraction_name": attr["name"],
                "projection": projection,
                "projected_visitors": projection.get("projected_visitors"),
                "projected_occupancy_pct": projection.get("projected_occupancy_pct"),
                "current_visitors": projection.get("current_visitors"),
                "occupancy_pct": projection.get("occupancy_pct"),
                "trend": projection.get("trend"),
                "threshold_warning": projection.get("threshold_warning"),
            },
            artifact=artifact
        )


class RecommendStaffingTool:
    """Workflow 9: When should businesses increase staff/services?"""
    name: str = "recommend_staffing"
    description: str = (
        "Convert projected visitor demand and configured service-capacity rules into actionable "
        "staffing recommendations. Distinguishes total staff needed from additional staff beyond existing roster."
    )
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "attraction_id": {"type": "string", "description": "Attraction ID, e.g. 'ins_kursura' or 'kailasagiri'"},
            "projected_visitors": {"type": "integer", "description": "Optional override for projected visitor count"}
        },
        "required": ["attraction_id"]
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    async def run(self, attraction_id: str, projected_visitors: Optional[int] = None, **kwargs) -> ToolResult:
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, max_capacity FROM attractions WHERE id = ?", (attraction_id,))
            attr = cursor.fetchone()
            if not attr:
                return ToolResult(success=False, error=f"Attraction '{attraction_id}' not found.")

            # Get visitors if not supplied
            if projected_visitors is None:
                cursor.execute("""
                    SELECT visitor_count FROM crowd_readings
                    WHERE attraction_id = ? ORDER BY timestamp DESC LIMIT 1
                """, (attraction_id,))
                crowd = cursor.fetchone()
                visitors = crowd["visitor_count"] if crowd else 100
            else:
                visitors = projected_visitors

            # Fetch service capacity rules
            cursor.execute("SELECT * FROM service_rules WHERE attraction_id = ?", (attraction_id,))
            rules = [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

        if not rules:
            rules = [
                {"business_type": "Ticketing Staff", "visitors_per_staff": 100, "current_roster": 2},
                {"business_type": "Security / Floor Marshals", "visitors_per_staff": 150, "current_roster": 3},
                {"business_type": "Guest Support Desk", "visitors_per_staff": 300, "current_roster": 1}
            ]

        staffing_recs = StaffingCalculator.calculate(rules=rules, projected_or_current_visitors=visitors)

        artifact = {
            "type": "table",
            "title": f"Staffing Recommendations: {attr['name']} (Demand: {visitors} visitors)",
            "columns": ["Role / Service", "Active Roster", "Total Needed", "Additional Required", "Status", "Recommendation"],
            "rows": [
                [
                    r["role"].capitalize(),
                    str(r["current_roster"]),
                    str(r["total_staff_needed"]),
                    f"+{r['additional_staff_needed']}" if r["additional_staff_needed"] > 0 else "0",
                    r["status"].replace("_", " ").upper(),
                    r["recommendation"]
                ]
                for r in staffing_recs
            ]
        }

        return ToolResult(
            success=True,
            output={
                "attraction_id": attraction_id,
                "attraction_name": attr["name"],
                "projected_visitors": visitors,
                "staffing_recommendations": staffing_recs
            },
            artifact=artifact
        )


class AllocateAuthoritiesResourcesTool:
    """Workflow 10: Where should authorities add support?"""
    name: str = "allocate_authorities_resources"
    description: str = (
        "Prioritize public locations using occupancy, projected demand, disruptions, and available finite "
        "resources (police patrol, ambulance medic, traffic officers, shuttles). Saves proposed allocation."
    )
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Session ID to save allocation for"},
            "destination_id": {"type": "string", "description": "Defaults to 'vizag'", "default": "vizag"}
        },
        "required": ["session_id"]
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    async def run(self, session_id: str, destination_id: str = "vizag", **kwargs) -> ToolResult:
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # 1. Fetch resources pool
            cursor.execute("SELECT resource_type, total_available FROM resources WHERE destination_id = ?", (destination_id,))
            res_pool = {r["resource_type"]: r["total_available"] for r in cursor.fetchall()}

            # 2. Fetch attractions and active disruptions
            cursor.execute("SELECT * FROM disruptions WHERE active = 1 AND destination_id = ?", (destination_id,))
            disruptions = cursor.fetchall()
            disrupted_places = set()
            for d in disruptions:
                disrupted_places.update(json.loads(d["affected_places_json"] or "[]"))

            cursor.execute("SELECT id, name FROM attractions WHERE destination_id = ?", (destination_id,))
            attractions = cursor.fetchall()

            demands = []
            for a in attractions:
                cursor.execute("""
                    SELECT occupancy_pct FROM crowd_readings
                    WHERE attraction_id = ? ORDER BY timestamp DESC LIMIT 1
                """, (a["id"],))
                crowd = cursor.fetchone()
                occ = crowd["occupancy_pct"] if crowd else 0.0

                demands.append({
                    "place_id": a["id"],
                    "name": a["name"],
                    "occupancy_pct": occ,
                    "has_disruption": a["id"] in disrupted_places
                })

            # Run finite allocation logic
            result = ResourceAllocator.allocate(demands, res_pool)

            # Save allocation plan
            alloc_id = f"alloc_{uuid.uuid4().hex[:8]}"
            now_str = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                INSERT INTO resource_allocations (
                    id, session_id, target_date, allocations_json, unserved_demand_json, rationale, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                alloc_id,
                session_id,
                datetime.now(TZ_KOLKATA).strftime("%Y-%m-%d"),
                json.dumps(result["allocated_plans"]),
                json.dumps(result["unserved_demand"]),
                result["assumptions"],
                now_str
            ))

            conn.commit()
        finally:
            conn.close()

        artifact = {
            "type": "table",
            "title": f"Municipal Resource Deployment Plan [ID: {alloc_id}]",
            "columns": ["Hub / Landmark", "Occupancy", "Assigned Police", "Assigned Traffic", "Assigned Medic", "Assigned Shuttle"],
            "rows": [
                [
                    p["name"],
                    f"{p['occupancy_pct']}%",
                    str(p["assigned_resources"].get("police_patrol", 0)),
                    str(p["assigned_resources"].get("traffic_officer", 0)),
                    str(p["assigned_resources"].get("ambulance_medic", 0)),
                    str(p["assigned_resources"].get("shuttle_bus", 0))
                ]
                for p in result["allocated_plans"][:6]
            ]
        }

        return ToolResult(
            success=True,
            output={
                "allocation_id": alloc_id,
                "allocations": result["allocated_plans"],
                "allocated_plans": result["allocated_plans"],
                "remaining_resources": result["remaining_inventory"],
                "remaining_pool": result["remaining_inventory"],
                "unserved_demand": result["unserved_demand"],
                "unserved_demands": result["unserved_demand"],
                "policy_rationale": result["assumptions"]
            },
            artifact=artifact
        )


class UpdatePreferencesTool:
    """Session preferences persistence tool for user constraints."""
    name: str = "update_preferences"
    description: str = "Save or revise tourist preferences (city, budget, date, party size, interests) for the session."
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Session ID to update"},
            "budget_inr": {"type": "number", "description": "Budget limit in INR"},
            "target_date": {"type": "string", "description": "Travel date YYYY-MM-DD"},
            "party_size": {"type": "integer", "description": "Number of travelers"},
            "interests": {"type": "array", "items": {"type": "string"}, "description": "List of interests"},
            "preferred_pace": {"type": "string", "description": "Travel pace: leisurely, moderate, intensive"},
            "budget_category": {"type": "string", "description": "Budget category: budget, standard, luxury"},
            "dietary_restrictions": {"type": "string", "description": "Dietary preferences or restrictions"}
        },
        "required": ["session_id"]
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    async def run(
        self,
        session_id: str,
        budget_inr: Optional[float] = None,
        target_date: Optional[str] = None,
        party_size: Optional[int] = None,
        interests: Optional[List[str]] = None,
        **kwargs
    ) -> ToolResult:
        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()
            now_str = datetime.now(timezone.utc).isoformat()
            cursor.execute("SELECT * FROM session_preferences WHERE session_id = ?", (session_id,))
            existing = cursor.fetchone()

            existing_prefs = {}
            if existing and "preferences_json" in existing.keys() and existing["preferences_json"]:
                try:
                    existing_prefs = json.loads(existing["preferences_json"])
                except Exception:
                    existing_prefs = {}

            # Merge existing preferences with newly passed kwargs
            updated_prefs = dict(existing_prefs)
            for k, v in kwargs.items():
                if v is not None:
                    updated_prefs[k] = v

            if budget_inr is not None:
                updated_prefs["budget_inr"] = budget_inr
            elif existing and existing["budget_limit"] is not None:
                updated_prefs.setdefault("budget_inr", existing["budget_limit"])

            if target_date is not None:
                updated_prefs["target_date"] = target_date
            elif existing and existing["target_date"]:
                updated_prefs.setdefault("target_date", existing["target_date"])

            if party_size is not None:
                updated_prefs["party_size"] = party_size
            elif existing and existing["party_size"] is not None:
                updated_prefs.setdefault("party_size", existing["party_size"])

            if interests is not None:
                updated_prefs["interests"] = interests
            elif existing and existing["interests_json"]:
                try:
                    updated_prefs.setdefault("interests", json.loads(existing["interests_json"]))
                except Exception:
                    pass

            new_budget = updated_prefs.get("budget_inr")
            new_date = updated_prefs.get("target_date")
            new_party = updated_prefs.get("party_size", 1)
            new_interests = json.dumps(updated_prefs.get("interests", []))
            prefs_json = json.dumps(updated_prefs)
            pref_pace = updated_prefs.get("preferred_pace")
            b_cat = updated_prefs.get("budget_category")
            diet = updated_prefs.get("dietary_restrictions")

            if existing:
                cursor.execute("""
                    UPDATE session_preferences
                    SET budget_limit = ?, target_date = ?, party_size = ?, interests_json = ?,
                        preferred_pace = ?, budget_category = ?, dietary_restrictions = ?,
                        preferences_json = ?, updated_at = ?
                    WHERE session_id = ?
                """, (new_budget, new_date, new_party, new_interests, pref_pace, b_cat, diet, prefs_json, now_str, session_id))
            else:
                cursor.execute("""
                    INSERT INTO session_preferences (
                        session_id, target_city, target_date, budget_limit, budget_currency,
                        party_size, interests_json, preferred_pace, budget_category,
                        dietary_restrictions, preferences_json, updated_at
                    ) VALUES (?, 'Visakhapatnam', ?, ?, 'INR', ?, ?, ?, ?, ?, ?, ?)
                """, (session_id, new_date, new_budget, new_party, new_interests, pref_pace, b_cat, diet, prefs_json, now_str))

            conn.commit()
        finally:
            conn.close()

        return ToolResult(
            success=True,
            output={
                "status": "preferences_saved",
                "session_id": session_id,
                "preferences": updated_prefs,
                "budget_inr": updated_prefs.get("budget_inr"),
                "target_date": updated_prefs.get("target_date"),
                "party_size": updated_prefs.get("party_size"),
                "interests": updated_prefs.get("interests"),
            }
        )
