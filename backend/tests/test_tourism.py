"""Comprehensive Unit and Integration Tests for Limen Tourism Decision and Management Suite."""
import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tourism.adapters import RoutingAdapter, WeatherAdapter
from tourism.db import get_db_connection, init_db
from tourism.logic import (
    CrowdProjector,
    OpeningHoursEvaluator,
    ResourceAllocator,
    StaffingCalculator,
)
from tourism.monitor import ItineraryMonitor
from tourism.provenance import DataSourceType, Provenance
from tourism.seeds import seed_scenario_data, trigger_scenario_disruption
from tourism.tools import (
    AllocateAuthoritiesResourcesTool,
    BuildItineraryTool,
    CalculateRouteTool,
    CheckDisruptionsTool,
    ProjectCrowdSurgeTool,
    QueryAccommodationsTool,
    QueryEventsTool,
    QueryOpenPlacesTool,
    RankCrowdsTool,
    RecommendStaffingTool,
    UpdatePreferencesTool,
)

TZ_KOLKATA = ZoneInfo("Asia/Kolkata")


class TestTourismSuite(unittest.TestCase):
    def setUp(self):
        # Create an isolated temporary SQLite database for each test run
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_tourism.db"
        init_db(self.db_path)
        seed_scenario_data(self.db_path)

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    # 1. Provenance Tests
    def test_provenance_schema_and_types(self):
        p_live = Provenance(source_name="Open-Meteo", source_type=DataSourceType.LIVE)
        self.assertEqual(p_live.source_type, "live")
        self.assertEqual(p_live.confidence, 1.0)

        p_sim = Provenance(
            source_name="Vizag Municipal Sensors",
            source_type=DataSourceType.SIMULATED,
            notes="Simulated IoT feed",
        )
        self.assertEqual(p_sim.source_type, "simulated")
        self.assertIn("Simulated", p_sim.notes)

    # 2. Opening Hours Evaluator Tests
    def test_opening_hours_evaluation(self):
        evaluator = OpeningHoursEvaluator()

        # Regular schedule JSON string
        schedule = json.dumps({
            "fri": {"open": "09:00", "close": "18:00"},
            "sat": {"open": "09:00", "close": "18:00"},
            "sun": None,
        })

        # Friday 11:30 AM IST (open)
        dt_open = datetime(2026, 9, 11, 11, 30, tzinfo=TZ_KOLKATA)
        res_open = evaluator.evaluate(schedule, dt_open)
        self.assertTrue(res_open["is_open"])
        self.assertEqual(res_open["status"], "OPEN")

        # Friday 20:00 IST (closed)
        dt_closed = datetime(2026, 9, 11, 20, 0, tzinfo=TZ_KOLKATA)
        res_closed = evaluator.evaluate(schedule, dt_closed)
        self.assertFalse(res_closed["is_open"])
        self.assertEqual(res_closed["status"], "CLOSED")

        # Sunday (closed day)
        dt_sunday = datetime(2026, 9, 13, 12, 0, tzinfo=TZ_KOLKATA)
        res_sun = evaluator.evaluate(schedule, dt_sunday)
        self.assertFalse(res_sun["is_open"])
        self.assertEqual(res_sun["status"], "CLOSED")

        # Missing / None schedule -> MUST be explicitly UNKNOWN, never assumed
        res_unk = evaluator.evaluate(None, dt_open)
        self.assertIsNone(res_unk["is_open"])
        self.assertEqual(res_unk["status"], "UNKNOWN")
        self.assertIn("unknown", res_unk["detail"].lower())

        # Emergency closure override
        res_emerg = evaluator.evaluate(
            schedule, dt_open, has_emergency_closure=True, closure_reason="Structural test"
        )
        self.assertFalse(res_emerg["is_open"])
        self.assertEqual(res_emerg["status"], "EMERGENCY_CLOSED")
        self.assertIn("Structural test", res_emerg["detail"])

    # 3. Crowd Projector Tests
    def test_crowd_projector_deterministic(self):
        projector = CrowdProjector()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Insufficient history: single reading
        single_reading = [
            {"visitor_count": 120, "timestamp": now_iso}
        ]
        res_insufficient = projector.project(single_reading, capacity=300)
        self.assertEqual(res_insufficient["status"], "INSUFFICIENT_HISTORY")
        self.assertIsNone(res_insufficient["projected_visitors"])

        # Valid 2 readings with upward surge
        from datetime import timedelta
        t1 = datetime.now(timezone.utc) - timedelta(minutes=30)
        t2 = datetime.now(timezone.utc)
        two_readings = [
            {"visitor_count": 100, "timestamp": t1.isoformat()},
            {"visitor_count": 160, "timestamp": t2.isoformat()},
        ]
        # Rate: +60 people in 30 min = +120 people/hr. Over 1 hour horizon -> 160 + 120 = 280 (spec: clamp at zero, not capacity)
        res_projected = projector.project(two_readings, capacity=200, target_horizon_hours=1.0)
        self.assertEqual(res_projected["status"], "VALID_PROJECTION")
        self.assertEqual(res_projected["projected_visitors"], 280)  # Clamped at zero, not capped at capacity
        self.assertEqual(res_projected["projected_occupancy_pct"], 140.0)
        self.assertTrue(res_projected["threshold_warning"])

    # 4. Staffing Calculator Tests
    def test_staffing_calculator(self):
        calc = StaffingCalculator()
        # Headcount 1250, ratio 1:150 => ceil(1250/150) = 9 total staff
        # Active roster = 5 => additional needed = 4
        rules = [
            {"business_type": "lifeguard", "visitors_per_staff": 150, "current_roster": 5}
        ]
        res = calc.calculate(rules=rules, projected_or_current_visitors=1250)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["total_staff_needed"], 9)
        self.assertEqual(res[0]["additional_staff_needed"], 4)
        self.assertEqual(res[0]["status"], "increase_required")

        # Sufficient active staff
        res_suff = calc.calculate(rules=rules, projected_or_current_visitors=200)
        # ceil(200/150) = 2 total needed vs 5 roster => 0 additional needed
        self.assertEqual(res_suff[0]["total_staff_needed"], 2)
        self.assertEqual(res_suff[0]["additional_staff_needed"], 0)
        self.assertEqual(res_suff[0]["status"], "sufficient")

    # 5. Resource Allocator Tests
    def test_resource_allocator_no_overallocation(self):
        allocator = ResourceAllocator()
        inventory = {
            "traffic_officer": 4,
            "police_patrol": 3,
            "ambulance_medic": 1,
            "shuttle_bus": 0,
        }
        demands = [
            {"place_id": "rk_beach", "name": "RK Beach", "occupancy_pct": 90, "has_disruption": 1},
            {"place_id": "kailasagiri", "name": "Kailasagiri", "occupancy_pct": 85, "has_disruption": 0},
        ]
        res = allocator.allocate(demands=demands, inventory=inventory)
        self.assertEqual(res["status"], "ALLOCATION_COMPLETED")
        # Ensure remaining resources are non-negative (no over-allocation)
        for res_type, remaining in res["remaining_inventory"].items():
            self.assertGreaterEqual(remaining, 0)

        # Confirm shortfall was reported for unserved demand
        self.assertGreater(len(res["unserved_demands"]), 0)

    # 6. Tool Tests (All 10 Workflows)
    def test_workflow_1_query_open_places(self):
        tool = QueryOpenPlacesTool(self.db_path)
        res = asyncio.run(tool.run(category=None, max_crowd_pct=95.0))
        self.assertTrue(res.success)
        self.assertIn("places", res.output)
        self.assertGreater(len(res.output["places"]), 0)
        self.assertIsNotNone(res.artifact)
        self.assertIn("columns", res.artifact)

    def test_workflow_2_build_itinerary(self):
        tool = BuildItineraryTool(self.db_path)
        res = asyncio.run(tool.run(session_id="test_sess", budget_inr=1500.0, start_time="09:00"))
        self.assertTrue(res.success)
        self.assertIn("stops", res.output)
        self.assertGreater(len(res.output["stops"]), 0)
        self.assertIn("total_admission_inr", res.output)
        self.assertLessEqual(res.output["total_admission_inr"], 1500.0)

    def test_workflow_3_calculate_route_and_fallback(self):
        tool = CalculateRouteTool(self.db_path)
        # Route from RK Beach to Kailasagiri
        res = asyncio.run(tool.run(origin="rk_beach", destination="kailasagiri"))
        self.assertTrue(res.success)
        self.assertIn("fastest_duration_min", res.output)
        self.assertIn("fastest_mode", res.output)
        self.assertIn("options", res.output)

    def test_workflow_4_check_disruptions(self):
        tool = CheckDisruptionsTool(self.db_path)
        res = asyncio.run(tool.run())
        self.assertTrue(res.success)
        self.assertIn("disruptions", res.output)
        self.assertIn("total_disruptions", res.output)

    def test_workflow_5_query_accommodations(self):
        tool = QueryAccommodationsTool(self.db_path)
        res = asyncio.run(
            tool.run(checkin_date="2026-09-12", nights=2, max_budget_per_night=4000.0)
        )
        self.assertTrue(res.success)
        self.assertIn("accommodations", res.output)
        for acc in res.output["accommodations"]:
            self.assertLessEqual(acc["price_per_night_inr"], 4000.0)
            self.assertEqual(acc["total_stay_price_inr"], acc["price_per_night_inr"] * 2)

    def test_workflow_6_query_events(self):
        tool = QueryEventsTool(self.db_path)
        res = asyncio.run(tool.run(filter_period="all"))
        self.assertTrue(res.success)
        self.assertIn("events", res.output)
        self.assertGreater(len(res.output["events"]), 0)

    def test_workflow_7_rank_crowds_headcount_vs_density(self):
        tool = RankCrowdsTool(self.db_path)
        # Rank by absolute headcount
        res_hc = asyncio.run(tool.run(sort_by="visitor_count"))
        self.assertTrue(res_hc.success)
        rankings_hc = res_hc.output["rankings"]
        self.assertGreater(len(rankings_hc), 0)
        self.assertGreaterEqual(rankings_hc[0]["visitor_count"], rankings_hc[-1]["visitor_count"])

        # Rank by density percentage
        res_den = asyncio.run(tool.run(sort_by="occupancy_pct"))
        self.assertTrue(res_den.success)
        rankings_den = res_den.output["rankings"]
        self.assertGreaterEqual(rankings_den[0]["occupancy_pct"], rankings_den[-1]["occupancy_pct"])

    def test_workflow_8_project_crowd_surge(self):
        tool = ProjectCrowdSurgeTool(self.db_path)
        res = asyncio.run(tool.run(attraction_id="kailasagiri"))
        self.assertTrue(res.success)
        self.assertIn("projected_visitors", res.output)
        self.assertIn("projected_occupancy_pct", res.output)

    def test_workflow_9_recommend_staffing(self):
        tool = RecommendStaffingTool(self.db_path)
        res = asyncio.run(tool.run(attraction_id="rk_beach"))
        self.assertTrue(res.success)
        self.assertIn("staffing_recommendations", res.output)
        self.assertGreater(len(res.output["staffing_recommendations"]), 0)

    def test_workflow_10_allocate_authorities_resources(self):
        tool = AllocateAuthoritiesResourcesTool(self.db_path)
        res = asyncio.run(tool.run(session_id="test_alloc_sess"))
        self.assertTrue(res.success)
        self.assertIn("allocations", res.output)
        self.assertIn("remaining_resources", res.output)

    def test_preferences_persistence_tool(self):
        tool = UpdatePreferencesTool(self.db_path)
        res = asyncio.run(
            tool.run(
                session_id="test_pref_sess",
                preferred_pace="leisurely",
                budget_category="luxury",
                dietary_restrictions="vegetarian",
            )
        )
        self.assertTrue(res.success)
        self.assertEqual(res.output["preferences"]["preferred_pace"], "leisurely")

    # 7. Scenario Trigger and Autonomous Monitoring Replanning
    def test_scenario_trigger_and_autonomous_replan(self):
        monitor = ItineraryMonitor(self.db_path)
        session_id = "test_mon_session"

        # 1. Build initial itinerary including INS Kursura Submarine Museum
        builder = BuildItineraryTool(self.db_path)
        build_res = asyncio.run(
            builder.run(
                session_id=session_id,
                target_date="2026-09-12",
                budget_inr=2000.0,
                start_time="09:00",
            )
        )
        self.assertTrue(build_res.success)
        itin_id = build_res.output["itinerary_id"]

        # Initial check should be healthy
        health_init = asyncio.run(monitor.check_itinerary_health(session_id))
        self.assertTrue(health_init["healthy"])

        # 2. Trigger scenario disruption on INS Kursura Submarine Museum
        trigger_res = trigger_scenario_disruption(
            db_path=self.db_path,
            attraction_id="ins_kursura",
            reason="Emergency electrical maintenance on submarine dehumidification system",
        )
        self.assertTrue(trigger_res["success"])

        # 3. Check health: should now detect disruption
        health_disrupted = asyncio.run(monitor.check_itinerary_health(session_id))
        self.assertFalse(health_disrupted["healthy"])
        self.assertGreater(len(health_disrupted["affected_stops"]), 0)
        self.assertEqual(health_disrupted["affected_stops"][0]["place_id"], "ins_kursura")

        # 4. Trigger autonomous replan
        replan_res = asyncio.run(monitor.autonomous_replan(session_id, health_disrupted))
        self.assertEqual(replan_res["type"], "autonomous_replan")
        self.assertEqual(replan_res["version"], 2)
        self.assertIn("artifact", replan_res)

        # 5. Check health after replan: should be healthy again
        health_after = asyncio.run(monitor.check_itinerary_health(session_id))
        self.assertTrue(health_after["healthy"])


if __name__ == "__main__":
    unittest.main()
