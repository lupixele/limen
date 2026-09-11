"""SQLite Database Management and Schema for Limen Tourism Management Agent."""
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).parent.parent / "tourism.db"


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    path = db_path or DB_PATH
    conn = get_db_connection(path)
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS destinations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        country TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        timezone TEXT NOT NULL,
        is_demo_city INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS attractions (
        id TEXT PRIMARY KEY,
        destination_id TEXT NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        address TEXT,
        schedule_json TEXT, -- JSON mapping day of week to open/close e.g. {"mon": {"open": "09:00", "close": "17:00"}, ...}
        normal_duration_min INTEGER DEFAULT 60,
        admission_fee REAL DEFAULT 0.0,
        currency TEXT DEFAULT 'INR',
        max_capacity INTEGER DEFAULT 500,
        has_emergency_closure INTEGER DEFAULT 0,
        closure_reason TEXT,
        closure_until TEXT,
        source_type TEXT DEFAULT 'live',
        source_name TEXT DEFAULT 'OpenStreetMap',
        FOREIGN KEY (destination_id) REFERENCES destinations (id)
    );

    CREATE TABLE IF NOT EXISTS crowd_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attraction_id TEXT NOT NULL,
        timestamp TEXT NOT NULL, -- ISO8601
        visitor_count INTEGER NOT NULL,
        capacity INTEGER NOT NULL,
        occupancy_pct REAL NOT NULL,
        source_type TEXT DEFAULT 'simulated',
        FOREIGN KEY (attraction_id) REFERENCES attractions (id)
    );

    CREATE TABLE IF NOT EXISTS accommodations (
        id TEXT PRIMARY KEY,
        destination_id TEXT NOT NULL,
        name TEXT NOT NULL,
        property_type TEXT NOT NULL,
        address TEXT,
        latitude REAL,
        longitude REAL,
        total_rooms INTEGER DEFAULT 50,
        price_per_night_inr REAL NOT NULL,
        rating REAL DEFAULT 4.0,
        amenities_json TEXT, -- JSON list
        is_synthetic INTEGER DEFAULT 1,
        source_name TEXT DEFAULT 'Demo Scenario Fixture',
        FOREIGN KEY (destination_id) REFERENCES destinations (id)
    );

    CREATE TABLE IF NOT EXISTS accommodation_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        accommodation_id TEXT NOT NULL,
        date TEXT NOT NULL, -- YYYY-MM-DD
        available_rooms INTEGER NOT NULL,
        is_real_inventory INTEGER DEFAULT 0,
        FOREIGN KEY (accommodation_id) REFERENCES accommodations (id),
        UNIQUE(accommodation_id, date)
    );

    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        destination_id TEXT NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        venue_name TEXT NOT NULL,
        latitude REAL,
        longitude REAL,
        start_datetime TEXT NOT NULL, -- ISO8601 with tz
        end_datetime TEXT NOT NULL,
        expected_attendance INTEGER DEFAULT 100,
        ticket_price_inr REAL DEFAULT 0.0,
        source_url TEXT,
        source_type TEXT DEFAULT 'simulated',
        FOREIGN KEY (destination_id) REFERENCES destinations (id)
    );

    CREATE TABLE IF NOT EXISTS disruptions (
        id TEXT PRIMARY KEY,
        destination_id TEXT NOT NULL,
        disruption_type TEXT NOT NULL, -- weather, traffic, closure, event
        severity TEXT NOT NULL, -- low, medium, high, critical
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        affected_places_json TEXT, -- JSON list of attraction_ids or routes
        start_time TEXT NOT NULL,
        end_time TEXT,
        active INTEGER DEFAULT 1,
        source_type TEXT DEFAULT 'simulated',
        FOREIGN KEY (destination_id) REFERENCES destinations (id)
    );

    CREATE TABLE IF NOT EXISTS itineraries (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        title TEXT NOT NULL,
        target_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'saved', -- saved, active, disrupted, revised, archived
        stops_json TEXT NOT NULL, -- JSON array of stops with travel/visit times and fees
        total_cost REAL DEFAULT 0.0,
        unpriced_items INTEGER DEFAULT 0,
        summary TEXT,
        version INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS service_rules (
        id TEXT PRIMARY KEY,
        attraction_id TEXT,
        business_type TEXT NOT NULL, -- ticket_counter, security, cafe, transit_hub
        visitors_per_staff INTEGER NOT NULL,
        current_roster INTEGER NOT NULL,
        notes TEXT,
        FOREIGN KEY (attraction_id) REFERENCES attractions (id)
    );

    CREATE TABLE IF NOT EXISTS resources (
        id TEXT PRIMARY KEY,
        destination_id TEXT NOT NULL,
        resource_type TEXT NOT NULL, -- police_patrol, ambulance_medic, shuttle_bus, traffic_officer
        total_available INTEGER NOT NULL,
        unit_cost REAL DEFAULT 0.0,
        notes TEXT,
        FOREIGN KEY (destination_id) REFERENCES destinations (id)
    );

    CREATE TABLE IF NOT EXISTS resource_allocations (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        target_date TEXT NOT NULL,
        allocations_json TEXT NOT NULL,
        unserved_demand_json TEXT,
        rationale TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS session_preferences (
        session_id TEXT PRIMARY KEY,
        target_city TEXT DEFAULT 'Visakhapatnam',
        target_date TEXT,
        budget_limit REAL,
        budget_currency TEXT DEFAULT 'INR',
        party_size INTEGER DEFAULT 1,
        interests_json TEXT,
        mobility_notes TEXT,
        preferred_pace TEXT,
        budget_category TEXT,
        dietary_restrictions TEXT,
        preferences_json TEXT,
        updated_at TEXT NOT NULL
    );
    """)

    conn.commit()
    conn.close()
