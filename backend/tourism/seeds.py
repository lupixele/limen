"""Seed and reset deterministic scenario data for Limen Tourism Management Agent.
Focuses on demo city: Visakhapatnam (Asia/Kolkata).
Real place coordinates and names; clearly marked synthetic operational counts and inventory.
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from tourism.db import get_db_connection, init_db

TZ_KOLKATA = ZoneInfo("Asia/Kolkata")


def seed_scenario_data(db_path: Optional[Path] = None) -> None:
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    now_kolkata = datetime.now(TZ_KOLKATA)
    today_str = now_kolkata.strftime("%Y-%m-%d")
    tomorrow_str = (now_kolkata + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after_str = (now_kolkata + timedelta(days=2)).strftime("%Y-%m-%d")

    # 1. Destinations
    cursor.execute("""
    INSERT OR REPLACE INTO destinations (id, name, country, latitude, longitude, timezone, is_demo_city)
    VALUES ('vizag', 'Visakhapatnam', 'India', 17.68009, 83.20161, 'Asia/Kolkata', 1)
    """)

    # 2. Attractions (10 real landmarks in Visakhapatnam)
    attractions = [
        (
            "ins_kursura",
            "vizag",
            "INS Kursura Submarine Museum",
            "museum",
            "Historic decommissioned submarine museum parked directly on RK Beach.",
            17.7169,
            83.3328,
            "Beach Road, RK Beach, Visakhapatnam",
            json.dumps({
                "mon": None, # closed on Mondays
                "tue": {"open": "14:00", "close": "20:30"},
                "wed": {"open": "14:00", "close": "20:30"},
                "thu": {"open": "14:00", "close": "20:30"},
                "fri": {"open": "14:00", "close": "20:30"},
                "sat": {"open": "14:00", "close": "20:30"},
                "sun": {"open": "10:00", "close": "20:30"}
            }),
            60,
            70.0,
            "INR",
            300,
            0,
            None,
            None,
            "verified",
            "AP Tourism & OpenStreetMap"
        ),
        (
            "tu142_museum",
            "vizag",
            "TU 142 Aircraft Museum",
            "museum",
            "Decommissioned maritime patrol aircraft converted into an interactive museum opposite Kursura.",
            17.7175,
            83.3332,
            "Beach Road, RK Beach, Visakhapatnam",
            json.dumps({
                "mon": {"open": "14:00", "close": "20:30"},
                "tue": {"open": "14:00", "close": "20:30"},
                "wed": {"open": "14:00", "close": "20:30"},
                "thu": {"open": "14:00", "close": "20:30"},
                "fri": {"open": "14:00", "close": "20:30"},
                "sat": {"open": "14:00", "close": "20:30"},
                "sun": {"open": "10:00", "close": "20:30"}
            }),
            45,
            70.0,
            "INR",
            250,
            0,
            None,
            None,
            "verified",
            "AP Tourism & OpenStreetMap"
        ),
        (
            "kailasagiri",
            "vizag",
            "Kailasagiri Hilltop Park",
            "park",
            "Panoramic hilltop park overlooking the Bay of Bengal with ropeway, toy train, and giant Shiva-Parvati statue.",
            17.7492,
            83.3422,
            "Hill Top Rd, Kailasagiri, Visakhapatnam",
            json.dumps({
                "mon": {"open": "06:00", "close": "19:30"},
                "tue": {"open": "06:00", "close": "19:30"},
                "wed": {"open": "06:00", "close": "19:30"},
                "thu": {"open": "06:00", "close": "19:30"},
                "fri": {"open": "06:00", "close": "19:30"},
                "sat": {"open": "06:00", "close": "19:30"},
                "sun": {"open": "06:00", "close": "19:30"}
            }),
            90,
            20.0,
            "INR",
            1200,
            0,
            None,
            None,
            "verified",
            "VMRDA"
        ),
        (
            "rk_beach",
            "vizag",
            "Ramakrishna (RK) Beach Promenade",
            "beach",
            "Urban beachfront promenade famous for evening walks, street food, and sea breeze.",
            17.7136,
            83.3242,
            "Beach Road, Visakhapatnam",
            json.dumps({
                "mon": {"open": "00:00", "close": "23:59"},
                "tue": {"open": "00:00", "close": "23:59"},
                "wed": {"open": "00:00", "close": "23:59"},
                "thu": {"open": "00:00", "close": "23:59"},
                "fri": {"open": "00:00", "close": "23:59"},
                "sat": {"open": "00:00", "close": "23:59"},
                "sun": {"open": "00:00", "close": "23:59"}
            }),
            60,
            0.0,
            "INR",
            3000,
            0,
            None,
            None,
            "verified",
            "Public Beach"
        ),
        (
            "rushikonda_beach",
            "vizag",
            "Rushikonda Beach",
            "beach",
            "Blue Flag certified pristine beach with golden sand, water sports, and sea sports facilities.",
            17.7825,
            83.3853,
            "Rushikonda, Bheemili Road, Visakhapatnam",
            json.dumps({
                "mon": {"open": "06:00", "close": "18:30"},
                "tue": {"open": "06:00", "close": "18:30"},
                "wed": {"open": "06:00", "close": "18:30"},
                "thu": {"open": "06:00", "close": "18:30"},
                "fri": {"open": "06:00", "close": "18:30"},
                "sat": {"open": "06:00", "close": "18:30"},
                "sun": {"open": "06:00", "close": "18:30"}
            }),
            90,
            20.0,
            "INR",
            1500,
            0,
            None,
            None,
            "verified",
            "Blue Flag & AP Tourism"
        ),
        (
            "simhachalam",
            "vizag",
            "Varaha Lakshmi Narasimha Temple (Simhachalam)",
            "temple",
            "Medieval 11th-century hill shrine dedicated to Lord Narasimha with Kalinga architecture.",
            17.7667,
            83.2505,
            "Simhachalam Hill, Visakhapatnam",
            json.dumps({
                "mon": {"open": "07:00", "close": "21:00"},
                "tue": {"open": "07:00", "close": "21:00"},
                "wed": {"open": "07:00", "close": "21:00"},
                "thu": {"open": "07:00", "close": "21:00"},
                "fri": {"open": "07:00", "close": "21:00"},
                "sat": {"open": "07:00", "close": "21:00"},
                "sun": {"open": "07:00", "close": "21:00"}
            }),
            90,
            100.0,
            "INR",
            2000,
            0,
            None,
            None,
            "verified",
            "Temple Devasthanam"
        ),
        (
            "zoo_park",
            "vizag",
            "Indira Gandhi Zoological Park",
            "wildlife",
            "Sprawling 625-acre natural reserve zoo nestled between Kambalakonda reserve forest and sea.",
            17.7689,
            83.3468,
            "Near Yendada, NH16, Visakhapatnam",
            json.dumps({
                "mon": None, # closed Mondays
                "tue": {"open": "09:00", "close": "17:00"},
                "wed": {"open": "09:00", "close": "17:00"},
                "thu": {"open": "09:00", "close": "17:00"},
                "fri": {"open": "09:00", "close": "17:00"},
                "sat": {"open": "09:00", "close": "17:00"},
                "sun": {"open": "09:00", "close": "17:00"}
            }),
            120,
            50.0,
            "INR",
            2500,
            0,
            None,
            None,
            "verified",
            "AP Forest Department"
        ),
        (
            "dolphin_nose",
            "vizag",
            "Dolphin's Nose Lighthouse & Viewpoint",
            "viewpoint",
            "Giant rocky promontory resembling a dolphin's nose, rising 358m above sea level with powerful lighthouse.",
            17.6833,
            83.2917,
            "Dolphin Hill, Visakhapatnam",
            json.dumps({
                "mon": {"open": "15:00", "close": "17:30"},
                "tue": {"open": "15:00", "close": "17:30"},
                "wed": {"open": "15:00", "close": "17:30"},
                "thu": {"open": "15:00", "close": "17:30"},
                "fri": {"open": "15:00", "close": "17:30"},
                "sat": {"open": "15:00", "close": "17:30"},
                "sun": {"open": "15:00", "close": "17:30"}
            }),
            45,
            20.0,
            "INR",
            400,
            0,
            None,
            None,
            "verified",
            "Directorate of Lighthouses"
        ),
        (
            "yarada_beach",
            "vizag",
            "Yarada Beach",
            "beach",
            "Scenic secluded beach surrounded by lush hills on three sides and pristine surf.",
            17.6539,
            83.2694,
            "Yarada, Visakhapatnam",
            json.dumps({
                "mon": {"open": "06:00", "close": "18:00"},
                "tue": {"open": "06:00", "close": "18:00"},
                "wed": {"open": "06:00", "close": "18:00"},
                "thu": {"open": "06:00", "close": "18:00"},
                "fri": {"open": "06:00", "close": "18:00"},
                "sat": {"open": "06:00", "close": "18:00"},
                "sun": {"open": "06:00", "close": "18:00"}
            }),
            75,
            30.0,
            "INR",
            800,
            0,
            None,
            None,
            "verified",
            "Local Panchayat"
        ),
        (
            "ross_hill",
            "vizag",
            "Ross Hill & Port Viewpoint",
            "viewpoint",
            "Historic tripartite religious hill featuring Ross Hill Church, Dargah, and Venkateswara Temple overlooking the port entrance.",
            17.6931,
            83.2986,
            "Port Area, Visakhapatnam",
            None, # Note: missing schedule intentionally to test UNKNOWN opening schedule edge case
            45,
            0.0,
            "INR",
            350,
            0,
            None,
            None,
            "verified",
            "Visakhapatnam Port Authority"
        )
    ]

    for a in attractions:
        cursor.execute("""
        INSERT OR REPLACE INTO attractions (
            id, destination_id, name, category, description, latitude, longitude, address,
            schedule_json, normal_duration_min, admission_fee, currency, max_capacity,
            has_emergency_closure, closure_reason, closure_until, source_type, source_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, a)

    # 3. Crowd Readings over time (Simulated provenance)
    # Generate timestamped crowd history at -120m, -90m, -60m, -30m, -10m
    now_utc = datetime.now(timezone.utc)
    crowd_specs = [
        ("ins_kursura", 300, [110, 140, 175, 210, 245]), # Trending up rapidly: 81.6% occupancy
        ("tu142_museum", 250, [60, 75, 90, 105, 120]),    # Moderate: 48%
        ("kailasagiri", 1200, [300, 450, 620, 800, 1020]), # High crowd & trending to overload: 85%
        ("rk_beach", 3000, [500, 800, 1200, 1600, 2100]), # 70%
        ("rushikonda_beach", 1500, [200, 300, 420, 510, 600]), # 40%
        ("simhachalam", 2000, [800, 950, 1100, 1250, 1400]), # 70%
        ("zoo_park", 2500, [300, 320, 350, 370, 400]), # 16% (low crowd)
        ("dolphin_nose", 400, [50, 70, 80, 95, 110]), # 27.5%
        ("yarada_beach", 800, [80, 100, 110, 120, 130]), # 16.2%
        ("ross_hill", 350, [40]), # Intentionally only 1 reading -> tests INSUFFICIENT HISTORY edge case!
    ]

    cursor.execute("DELETE FROM crowd_readings")
    intervals = [120, 90, 60, 30, 10]
    for place_id, cap, counts in crowd_specs:
        for idx, count in enumerate(counts):
            mins_ago = intervals[idx] if idx < len(intervals) else 10
            ts = (now_utc - timedelta(minutes=mins_ago)).isoformat()
            occ = round((count / cap) * 100, 1)
            cursor.execute("""
            INSERT INTO crowd_readings (attraction_id, timestamp, visitor_count, capacity, occupancy_pct, source_type)
            VALUES (?, ?, ?, ?, ?, 'simulated')
            """, (place_id, ts, count, cap, occ))

    # 4. Accommodations (5 Fictional demo properties with explicit synthetic labels)
    accommodations = [
        (
            "hotel_bayview_demo",
            "vizag",
            "Bayview Residency (Demo Fixture)",
            "hotel",
            "Beach Road near RK Beach, Visakhapatnam",
            17.7145,
            83.3260,
            40,
            2400.0,
            4.2,
            json.dumps(["Free Wi-Fi", "Ocean View", "Complimentary Breakfast", "AC"]),
            1,
            "Demo Scenario Fixture (Fictional Inventory)"
        ),
        (
            "resort_rushikonda_demo",
            "vizag",
            "Rushikonda Palm Retreat (Demo Fixture)",
            "resort",
            "Rushikonda Beachfront, Visakhapatnam",
            17.7840,
            83.3870,
            30,
            5500.0,
            4.6,
            json.dumps(["Beach Access", "Pool", "Spa", "Water Sports Desk", "Restaurant"]),
            1,
            "Demo Scenario Fixture (Fictional Inventory)"
        ),
        (
            "lodge_coral_sands_demo",
            "vizag",
            "Coral Sands Lodge (Demo Fixture)",
            "guesthouse",
            "Waltair Uplands, Visakhapatnam",
            17.7280,
            83.3150,
            25,
            1200.0,
            3.8,
            json.dumps(["AC Rooms", "Free Wi-Fi", "24hr Reception"]),
            1,
            "Demo Scenario Fixture (Fictional Inventory)"
        ),
        (
            "hotel_harbor_heritage_demo",
            "vizag",
            "Harbor Heritage Inn (Demo Fixture)",
            "boutique",
            "Port View Area, Visakhapatnam",
            17.6950,
            83.2970,
            20,
            3100.0,
            4.1,
            json.dumps(["Heritage Architecture", "Port View Cafe", "Free Parking"]),
            1,
            "Demo Scenario Fixture (Fictional Inventory)"
        ),
        (
            "dolphin_cove_boutique_demo",
            "vizag",
            "Dolphin Cove Suites (Demo Fixture)",
            "luxury_hotel",
            "Maharanipeta, Visakhapatnam",
            17.7080,
            83.3120,
            15,
            4200.0,
            4.5,
            json.dumps(["Sea View Balcony", "Fine Dining", "Airport Shuttle"]),
            1,
            "Demo Scenario Fixture (Fictional Inventory)"
        )
    ]

    cursor.execute("DELETE FROM accommodations")
    cursor.execute("DELETE FROM accommodation_inventory")

    for acc in accommodations:
        cursor.execute("""
        INSERT INTO accommodations (
            id, destination_id, name, property_type, address, latitude, longitude,
            total_rooms, price_per_night_inr, rating, amenities_json, is_synthetic, source_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, acc)

    # Add 30-day inventory records for each hotel
    for acc in accommodations:
        acc_id = acc[0]
        total_rooms = acc[7]
        for offset in range(30):
            date_str = (now_kolkata + timedelta(days=offset)).strftime("%Y-%m-%d")
            # Create realistic availability variation per night
            avail = max(1, int(total_rooms * (0.35 + (offset * 0.08) % 0.5)))
            cursor.execute("""
            INSERT INTO accommodation_inventory (accommodation_id, date, available_rooms, is_real_inventory)
            VALUES (?, ?, ?, 0)
            """, (acc_id, date_str, avail))

    # 5. Events (Dated local events with timezone ISO strings)
    events = [
        (
            "evt_beach_fest",
            "vizag",
            "Vizag Coastal Arts & Cultural Festival",
            "culture",
            "RK Beach Open Air Theatre",
            17.7140,
            83.3250,
            f"{today_str}T17:30:00+05:30",
            f"{today_str}T22:00:00+05:30",
            1200,
            0.0,
            "https://tourism.ap.gov.in/events/vizag-cultural-fest",
            "simulated"
        ),
        (
            "evt_sunset_carnival",
            "vizag",
            "Kailasagiri Sunset Music & Food Carnival",
            "entertainment",
            "Kailasagiri Hilltop Amphitheatre",
            17.7495,
            83.3425,
            f"{tomorrow_str}T16:00:00+05:30",
            f"{tomorrow_str}T21:30:00+05:30",
            800,
            150.0,
            "https://vmrda.gov.in/events/kailasagiri-carnival",
            "simulated"
        ),
        (
            "evt_tech_conclave",
            "vizag",
            "Bay Innovation & Tourism Tech Meet",
            "conference",
            "Rushikonda IT SEZ Auditorium",
            17.7870,
            83.3810,
            f"{day_after_str}T09:30:00+05:30",
            f"{day_after_str}T17:00:00+05:30",
            450,
            500.0,
            "https://vizaginnovation.org/meet",
            "simulated"
        )
    ]

    cursor.execute("DELETE FROM events")
    for evt in events:
        cursor.execute("""
        INSERT INTO events (
            id, destination_id, title, category, venue_name, latitude, longitude,
            start_datetime, end_datetime, expected_attendance, ticket_price_inr, source_url, source_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, evt)

    # 6. Service Rules (for question 9: When should businesses increase staff/services)
    service_rules = [
        ("sr_kursura_ticket", "ins_kursura", "ticket_counter", 60, 2, "1 ticket staff per 60 visitors/hr"),
        ("sr_kursura_guide", "ins_kursura", "docent_guide", 40, 3, "1 docent per 40 visitors inside submarine"),
        ("sr_kailasagiri_ropeway", "kailasagiri", "ropeway_operator", 100, 4, "1 operator per 100 ropeway visitors/hr"),
        ("sr_kailasagiri_security", "kailasagiri", "security", 150, 4, "1 security officer per 150 visitors in park"),
        ("sr_rk_beach_lifeguard", "rk_beach", "lifeguard", 300, 4, "1 coastal lifeguard per 300 promenade visitors"),
        ("sr_rushikonda_watersport", "rushikonda_beach", "safety_instructor", 50, 4, "1 safety instructor per 50 water sport users"),
        ("sr_simhachalam_queue", "simhachalam", "queue_manager", 120, 6, "1 queue marshal per 120 devotees/hr")
    ]

    cursor.execute("DELETE FROM service_rules")
    for sr in service_rules:
        cursor.execute("""
        INSERT INTO service_rules (id, attraction_id, business_type, visitors_per_staff, current_roster, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """, sr)

    # 7. Finite Resources (for question 10: Where should authorities add support)
    resources = [
        ("res_police_patrol", "vizag", "police_patrol", 10, 1500.0, "Mobile police patrol units for crowd control"),
        ("res_ambulance_medic", "vizag", "ambulance_medic", 6, 2500.0, "Emergency medical technician & quick-response ambulance"),
        ("res_traffic_officer", "vizag", "traffic_officer", 12, 1000.0, "Traffic management marshals at major junctions"),
        ("res_shuttle_bus", "vizag", "shuttle_bus", 8, 4000.0, "Electric park-and-ride municipal shuttles")
    ]

    cursor.execute("DELETE FROM resources")
    for res in resources:
        cursor.execute("""
        INSERT INTO resources (id, destination_id, resource_type, total_available, unit_cost, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """, res)

    # 8. Disruptions (Weather, road, or closure incidents)
    disruptions = [
        (
            "dis_ghat_road_work",
            "vizag",
            "traffic",
            "medium",
            "Simhachalam Ghat Road Drainage Maintenance",
            "Single-lane restriction on Simhachalam Ghat Road. Expect 10-15m transit delays for temple visitors.",
            json.dumps(["simhachalam_temple"]),
            f"{today_str}T08:00:00+05:30",
            f"{tomorrow_str}T20:00:00+05:30",
            1,
            "simulated"
        ),
        (
            "dis_high_wave_alert",
            "vizag",
            "weather",
            "high",
            "IMD Coastal Rough Sea & High Wave Advisory",
            "Swimming prohibited at Yarada and Bheemili Beach due to sudden swell surges. Lifeguards actively patrolling.",
            json.dumps(["yarada_beach", "bheemili_beach"]),
            f"{today_str}T06:00:00+05:30",
            f"{today_str}T23:59:00+05:30",
            1,
            "simulated"
        )
    ]

    cursor.execute("DELETE FROM disruptions")
    for dis in disruptions:
        cursor.execute("""
        INSERT INTO disruptions (
            id, destination_id, disruption_type, severity, title, description,
            affected_places_json, start_time, end_time, active, source_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, dis)

    conn.commit()
    conn.close()


def trigger_scenario_disruption(attraction_id: str = "ins_kursura", reason: str = "Emergency electrical maintenance on submarine dehumidification system", db_path: Optional[Path] = None) -> dict:
    """Modifies underlying database state for an emergency closure and spikes crowd at nearby attraction."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    now_kolkata = datetime.now(TZ_KOLKATA)
    closure_until = (now_kolkata + timedelta(hours=6)).isoformat()

    # 1. Close the attraction
    cursor.execute("""
    UPDATE attractions
    SET has_emergency_closure = 1, closure_reason = ?, closure_until = ?
    WHERE id = ?
    """, (reason, closure_until, attraction_id))

    # 2. Add an active disruption
    dis_id = f"dis_emergency_{attraction_id}_{int(datetime.now().timestamp())}"
    cursor.execute("""
    INSERT INTO disruptions (
        id, destination_id, disruption_type, severity, title, description,
        affected_places_json, start_time, end_time, active, source_type
    ) VALUES (?, 'vizag', 'closure', 'critical', ?, ?, ?, ?, ?, 1, 'simulated')
    """, (
        dis_id,
        f"Emergency Closure: {attraction_id.upper()}",
        reason,
        json.dumps([attraction_id]),
        now_kolkata.isoformat(),
        closure_until
    ))

    # 3. Crowd surge at alternative (e.g. tu142_museum)
    alt_id = "tu142_museum"
    now_utc = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
    INSERT INTO crowd_readings (attraction_id, timestamp, visitor_count, capacity, occupancy_pct, source_type)
    VALUES (?, ?, 235, 250, 94.0, 'simulated')
    """, (alt_id, now_utc))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "status": "triggered",
        "affected_attraction": attraction_id,
        "reason": reason,
        "closure_until": closure_until,
        "alt_affected": alt_id,
        "alt_occupancy_pct": 94.0
    }
