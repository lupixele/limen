"""Deterministic business and tourism decision logic for Limen."""
import json
import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("tourism.logic")


def parse_schedule_time(t_str: str) -> time:
    parts = t_str.strip().split(":")
    return time(int(parts[0]), int(parts[1]))


class OpeningHoursEvaluator:
    """Evaluates opening schedules, overnight windows, and emergency closures."""

    @staticmethod
    def evaluate(
        schedule_json: Optional[str],
        dt: datetime,
        has_emergency_closure: bool = False,
        closure_reason: Optional[str] = None,
        closure_until: Optional[str] = None
    ) -> Dict[str, Any]:
        if has_emergency_closure:
            # Check if closure window has elapsed
            closure_active = True
            if closure_until:
                try:
                    c_dt = datetime.fromisoformat(closure_until)
                    if c_dt.tzinfo is None and dt.tzinfo is not None:
                        c_dt = c_dt.replace(tzinfo=dt.tzinfo)
                    if dt > c_dt:
                        closure_active = False
                except Exception:
                    pass
            if closure_active:
                return {
                    "status": "EMERGENCY_CLOSED",
                    "is_open": False,
                    "reason": closure_reason or "Emergency closure in effect",
                    "closure_until": closure_until,
                    "detail": f"Temporarily closed: {closure_reason}"
                }

        if not schedule_json:
            return {
                "status": "UNKNOWN",
                "is_open": None,
                "reason": "Missing published schedule",
                "detail": "No verified opening hours published. Schedule unknown."
            }

        try:
            sched = json.loads(schedule_json)
        except Exception:
            return {
                "status": "UNKNOWN",
                "is_open": None,
                "reason": "Invalid schedule format",
                "detail": "Failed to parse schedule."
            }

        day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        day_key = day_names[dt.weekday()]
        day_sched = sched.get(day_key)

        if not day_sched:
            return {
                "status": "CLOSED",
                "is_open": False,
                "reason": f"Closed on {day_key.capitalize()}",
                "detail": f"Regular weekly closure on {day_key.capitalize()}."
            }

        open_str = day_sched.get("open")
        close_str = day_sched.get("close")
        if not open_str or not close_str:
            return {
                "status": "CLOSED",
                "is_open": False,
                "reason": "No operating hours listed for today",
                "detail": "Closed today."
            }

        t_now = dt.time()
        t_open = parse_schedule_time(open_str)
        t_close = parse_schedule_time(close_str)

        # Handle standard daytime vs overnight schedules
        if t_open <= t_close:
            # Daytime (e.g. 09:00 to 17:00)
            is_open = t_open <= t_now <= t_close
        else:
            # Overnight (e.g. 20:00 to 04:00)
            is_open = t_now >= t_open or t_now <= t_close

        return {
            "status": "OPEN" if is_open else "CLOSED",
            "is_open": is_open,
            "hours": f"{open_str} - {close_str}",
            "reason": "Within normal operating hours" if is_open else "Outside operating hours",
            "detail": f"{'Open now' if is_open else 'Closed now'} ({open_str} to {close_str})"
        }


class CrowdProjector:
    """Computes crowd occupancy and short-horizon trend projections from timestamped readings."""

    @staticmethod
    def project(
        readings: List[Dict[str, Any]],
        capacity: int,
        target_horizon_hours: float = 1.0,
        staleness_minutes: float = 180.0
    ) -> Dict[str, Any]:
        """
        readings: list of dicts with 'timestamp' (ISO8601) and 'visitor_count'
        Requires at least 2 fresh readings to compute a trend.
        """
        if not readings:
            return {
                "status": "INSUFFICIENT_DATA",
                "reason": "No crowd readings available",
                "current_visitors": None,
                "occupancy_pct": None,
                "projected_visitors": None,
                "trend": "unknown"
            }

        # Sort chronologically
        def parse_ts(r):
            ts = r["timestamp"]
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)

        sorted_readings = sorted(readings, key=parse_ts)
        latest = sorted_readings[-1]
        latest_dt = parse_ts(latest)
        now_utc = datetime.now(timezone.utc)

        # Check staleness
        if latest_dt.tzinfo is None:
            latest_dt = latest_dt.replace(tzinfo=timezone.utc)

        age_minutes = (now_utc - latest_dt).total_seconds() / 60.0
        is_stale = age_minutes > staleness_minutes

        current_count = latest["visitor_count"]
        occupancy_pct = round((current_count / max(1, capacity)) * 100, 1)

        if len(sorted_readings) < 2:
            return {
                "status": "INSUFFICIENT_HISTORY",
                "reason": "Insufficient historical readings (minimum 2 required for trend projection)",
                "current_visitors": current_count,
                "capacity": capacity,
                "occupancy_pct": occupancy_pct,
                "is_stale": is_stale,
                "projected_visitors": None,
                "projected_occupancy_pct": None,
                "trend": "insufficient_history",
                "explanation": "Only one historical observation is recorded; cannot compute confident rate of change."
            }

        # Calculate rate of change between earliest and latest available reading in window
        earliest = sorted_readings[0]
        earliest_dt = parse_ts(earliest)
        if earliest_dt.tzinfo is None:
            earliest_dt = earliest_dt.replace(tzinfo=timezone.utc)

        elapsed_hours = (latest_dt - earliest_dt).total_seconds() / 3600.0
        if elapsed_hours <= 0.01:
            hourly_rate = 0.0
        else:
            hourly_rate = (latest["visitor_count"] - earliest["visitor_count"]) / elapsed_hours

        # Project 1 hour forward clamped at zero
        projected_count = max(0, int(round(current_count + (hourly_rate * target_horizon_hours))))
        projected_occ_pct = round((projected_count / max(1, capacity)) * 100, 1)

        trend = "stable"
        if hourly_rate > 15:
            trend = "surging"
        elif hourly_rate > 5:
            trend = "increasing"
        elif hourly_rate < -5:
            trend = "decreasing"

        threshold_crossed = projected_occ_pct >= 80.0

        return {
            "status": "VALID_PROJECTION",
            "current_visitors": current_count,
            "capacity": capacity,
            "occupancy_pct": occupancy_pct,
            "is_stale": is_stale,
            "hourly_rate": round(hourly_rate, 1),
            "projected_visitors": projected_count,
            "projected_occupancy_pct": projected_occ_pct,
            "trend": trend,
            "threshold_warning": threshold_crossed,
            "explanation": (
                f"Simple trend projection (not ML): based on {len(sorted_readings)} readings over "
                f"{round(elapsed_hours, 1)}h (net change {round(hourly_rate, 1)}/hr). "
                f"Projected at {projected_occ_pct}% capacity."
            )
        }


class StaffingCalculator:
    """Calculates operational staffing requirements from service capacity rules and projected demand."""

    @staticmethod
    def calculate(
        rules: List[Dict[str, Any]],
        projected_or_current_visitors: int
    ) -> List[Dict[str, Any]]:
        results = []
        for r in rules:
            visitors_per_staff = max(1, r.get("visitors_per_staff", 50))
            current_roster = r.get("current_roster", 1)
            role = r.get("business_type", "staff")

            # Total needed
            total_needed = max(1, -(-projected_or_current_visitors // visitors_per_staff)) # ceiling div
            additional_needed = max(0, total_needed - current_roster)
            status = "sufficient" if additional_needed == 0 else "increase_required"

            results.append({
                "role": role,
                "visitors_per_staff": visitors_per_staff,
                "current_roster": current_roster,
                "total_staff_needed": total_needed,
                "additional_staff_needed": additional_needed,
                "status": status,
                "recommendation": (
                    f"Deploy +{additional_needed} {role} (total {total_needed})"
                    if additional_needed > 0
                    else f"Current roster of {current_roster} {role} is sufficient"
                )
            })
        return results


class ResourceAllocator:
    """Prioritizes locations and allocates finite public safety / transit resources without over-allocating."""

    @staticmethod
    def allocate(
        demands: List[Dict[str, Any]], # place_id, name, score/occupancy, disruptions
        inventory: Dict[str, int] # e.g. {"police_patrol": 10, "ambulance_medic": 6, "traffic_officer": 12, "shuttle_bus": 8}
    ) -> Dict[str, Any]:
        remaining_pool = dict(inventory)
        allocations = []
        unserved = []

        # Sort demands descending by severity/occupancy
        sorted_demands = sorted(demands, key=lambda d: (d.get("has_disruption", 0), d.get("occupancy_pct", 0)), reverse=True)

        for place in sorted_demands:
            place_id = place.get("place_id")
            name = place.get("name")
            occ = place.get("occupancy_pct", 0)
            has_dis = place.get("has_disruption", False)

            req = {}
            if occ >= 80 or has_dis:
                req["traffic_officer"] = 3
                req["police_patrol"] = 2
                req["ambulance_medic"] = 1
                if occ >= 85:
                    req["shuttle_bus"] = 2
            elif occ >= 50:
                req["traffic_officer"] = 1
                req["police_patrol"] = 1
            else:
                req["traffic_officer"] = 1

            place_allocated = {}
            place_shortfall = {}

            for res_type, needed in req.items():
                avail = remaining_pool.get(res_type, 0)
                assigned = min(avail, needed)
                remaining_pool[res_type] = avail - assigned
                place_allocated[res_type] = assigned
                if assigned < needed:
                    place_shortfall[res_type] = needed - assigned

            allocations.append({
                "place_id": place_id,
                "name": name,
                "occupancy_pct": occ,
                "assigned_resources": place_allocated,
                "shortfall": place_shortfall
            })

            if place_shortfall:
                unserved.append({
                    "place_id": place_id,
                    "name": name,
                    "unserved_demand": place_shortfall
                })

        return {
            "status": "ALLOCATION_COMPLETED",
            "allocated_plans": allocations,
            "remaining_inventory": remaining_pool,
            "unserved_demand": unserved,
            "unserved_demands": unserved,
            "assumptions": (
                "Demo policy rules: High-occupancy (>=80%) or disrupted hubs receive priority police/traffic/medic units. "
                "Total assignments strictly constrained by finite pool; no over-allocation permitted."
            )
        }
