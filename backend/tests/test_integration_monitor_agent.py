"""Integration tests for automatic tourism monitoring, session isolation, and agent loop correctness."""
import asyncio
import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app import app, create_agent_registry, get_session_context, session_store
from agent.loop import run_agent_loop
from agent.prompt import build_system_prompt
from core.sessions import SessionStore
from core.tools import ToolRegistry, ToolResult
from tourism.db import get_db_connection, init_db
from tourism.monitor import ItineraryMonitor, global_monitor
from tourism.seeds import seed_scenario_data


class TestIntegrationMonitorAgent(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_limen.db"
        init_db(self.db_path)
        seed_scenario_data(self.db_path)

        self.client = TestClient(app)
        self.test_session_id = "test_sess_integration_01"

    def tearDown(self):
        global_monitor.stop_monitoring(self.test_session_id)
        self.tmp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Trusted Session Tool Binding & Session Isolation
    # -------------------------------------------------------------------------
    def test_trusted_session_tool_binding_overrides_model_injection(self):
        """Model cannot access or target another session; loop enforces trusted session binding."""
        trusted_session = "session_user_alice"
        attacker_target = "session_user_bob"

        captured_args = {}

        class SpyStatefulTool:
            name: str = "spy_stateful_tool"
            description: str = "A stateful tool that requires session_id."
            json_schema = {
                "type": "object",
                "properties": {"session_id": {"type": "string"}, "action": {"type": "string"}},
                "required": ["session_id"],
            }

            async def run(self, **kwargs) -> ToolResult:
                nonlocal captured_args
                captured_args = dict(kwargs)
                return ToolResult(success=True, output={"status": "ok"})

        registry = ToolRegistry()
        registry.register(SpyStatefulTool())

        # Mock LLM response that maliciously injects attacker_target
        mock_response = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "Accessing victim session",
                        "tool_calls": [
                            {
                                "id": "call_injected",
                                "type": "function",
                                "function": {
                                    "name": "spy_stateful_tool",
                                    "arguments": json.dumps({
                                        "session_id": attacker_target,
                                        "action": "leak_data",
                                    }),
                                },
                            }
                        ],
                    },
                }
            ]
        }

        async def run():
            events = []
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_resp_obj = MagicMock()
                mock_resp_obj.status_code = 200
                mock_resp_obj.json.return_value = mock_response
                mock_post.return_value = mock_resp_obj

                async for event in run_agent_loop(
                    instruction="Run spy tool",
                    registry=registry,
                    provider_url="http://mock/v1",
                    api_key="mock",
                    model="mock-model",
                    session_id=trusted_session,
                    max_steps=1,
                ):
                    events.append(event)
            return events

        events = asyncio.run(run())
        self.assertEqual(captured_args.get("session_id"), trusted_session)
        self.assertNotEqual(captured_args.get("session_id"), attacker_target)

        # Check SSE events have correct session_id and invocation_id
        tool_events = [e for e in events if e.get("type") == "tool_call"]
        self.assertTrue(len(tool_events) >= 1)
        for te in tool_events:
            self.assertEqual(te["session_id"], trusted_session)
            self.assertTrue(te["invocation_id"].startswith("inv_call_injected"))

    # -------------------------------------------------------------------------
    # 2. Saved Context Retrieval and Injection
    # -------------------------------------------------------------------------
    def test_saved_context_retrieval_and_prompt_formatting(self):
        """Preferences and active itinerary are persisted and injected into session context."""
        sess_id = "sess_saved_ctx_test"
        conn = get_db_connection(self.db_path)
        cur = conn.cursor()

        # Insert preferences
        cur.execute(
            """
            INSERT INTO session_preferences (
                session_id, target_city, target_date, budget_limit, budget_currency, party_size, interests_json, updated_at
            ) VALUES (?, 'Visakhapatnam', '2026-10-15', 3500.0, 'INR', 2, ?, ?)
        """,
            (sess_id, json.dumps(["museum", "beach"]), datetime.now(timezone.utc).isoformat()),
        )

        # Insert active itinerary
        cur.execute(
            """
            INSERT INTO itineraries (
                id, session_id, title, target_date, status, stops_json, total_cost, unpriced_items, summary, version, created_at, updated_at
            ) VALUES ('itin_001', ?, 'Coastal Tour', '2026-10-15', 'saved', '[]', 500.0, 0, 'Coastal experience', 1, ?, ?)
        """,
            (sess_id, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

        ctx = get_session_context(sess_id, db_path=self.db_path)
        self.assertEqual(ctx["session_id"], sess_id)
        self.assertIsNotNone(ctx["preferences"])
        self.assertEqual(ctx["preferences"]["budget_limit"], 3500.0)
        self.assertEqual(ctx["preferences"]["party_size"], 2)
        self.assertIsNotNone(ctx["active_itinerary"])
        self.assertEqual(ctx["active_itinerary"]["itinerary_id"], "itin_001")

        # Test prompt incorporates this saved context
        system_prompt = build_system_prompt(tools=None, context=ctx, include_tourism_context=True)
        self.assertIn("sess_saved_ctx_test", system_prompt)
        self.assertIn("3500.0 INR", system_prompt)
        self.assertIn("itin_001", system_prompt)

    # -------------------------------------------------------------------------
    # 3. Safe Config Masking and Test Connection Endpoint
    # -------------------------------------------------------------------------
    def test_safe_config_masking_and_no_secret_leak(self):
        """GET /api/config masks api_key; POST /api/config ignores masked placeholder strings."""
        resp = self.client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("sk-", data.get("api_key", ""))
        self.assertIn("api_key_masked", data)
        self.assertIn("has_api_key", data)

        # Attempt to save config with masked string (as the frontend would if left untouched)
        masked_val = data["api_key_masked"]
        save_resp = self.client.post("/api/config", json={"api_key": masked_val})
        self.assertEqual(save_resp.status_code, 200)

        # Real secret should not be destroyed by saving masked placeholder
        resp2 = self.client.get("/api/config")
        self.assertEqual(resp2.json()["has_api_key"], data["has_api_key"])

    def test_test_connection_endpoint_restored(self):
        """POST /api/test-connection is present, returns status, and does not leak API keys."""
        resp = self.client.post("/api/test-connection")
        self.assertEqual(resp.status_code, 200)
        res_data = resp.json()
        self.assertIn("ok", res_data)
        self.assertIn("status", res_data)
        self.assertNotIn("api_key", res_data)

    # -------------------------------------------------------------------------
    # 4. Scenario Trigger Changes Data Only (No Scripted Agent Response)
    # -------------------------------------------------------------------------
    def test_scenario_trigger_changes_data_only(self):
        """Trigger updates SQLite records without directly generating an agent response."""
        resp = self.client.post(
            "/api/tourism/trigger-scenario",
            json={
                "attraction_id": "ins_kursura",
                "reason": "Test maintenance closure",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        # Ensure it didn't fabricate an agent response in the trigger endpoint
        self.assertNotIn("final_answer", body)

        # Verify underlying database was modified
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT has_emergency_closure, closure_reason FROM attractions WHERE id = 'ins_kursura'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row["has_emergency_closure"], 1)
        self.assertIn("Test maintenance closure", row["closure_reason"])

    # -------------------------------------------------------------------------
    # 5. Monitoring: Interval, Stop, No Overlap
    # -------------------------------------------------------------------------
    def test_monitoring_no_overlap_and_stop_semantics(self):
        """Starting monitoring twice for the same session returns already_running; stop stops cleanly."""
        async def run_test():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                sess_id = f"sess_mon_{int(time.time() * 1000)}"

                # 1. Start monitoring
                resp1 = await client.post(
                    "/api/tourism/monitor/start",
                    json={"session_id": sess_id, "interval_seconds": 0.5, "max_ticks": 5},
                )
                self.assertEqual(resp1.status_code, 200)
                self.assertEqual(resp1.json()["status"], "started")

                # 2. Attempt duplicate start -> strictly no overlap
                resp2 = await client.post(
                    "/api/tourism/monitor/start",
                    json={"session_id": sess_id, "interval_seconds": 0.5, "max_ticks": 5},
                )
                self.assertEqual(resp2.status_code, 200)
                self.assertEqual(resp2.json()["status"], "already_running")

                # 3. Check status
                stat_resp = await client.get(f"/api/tourism/monitor/status?session_id={sess_id}")
                self.assertEqual(stat_resp.status_code, 200)
                self.assertTrue(stat_resp.json()["active"])

                # 4. Stop monitoring
                stop_resp = await client.post(f"/api/tourism/monitor/stop?session_id={sess_id}")
                self.assertEqual(stop_resp.status_code, 200)
                self.assertEqual(stop_resp.json()["status"], "stopped")

                # 5. Verify status inactive
                stat_resp2 = await client.get(f"/api/tourism/monitor/status?session_id={sess_id}")
                self.assertFalse(stat_resp2.json()["active"])

        asyncio.run(run_test())

    # -------------------------------------------------------------------------
    # 6. Autonomous Replan via Agent / Tools on Disrupted Health
    # -------------------------------------------------------------------------
    def test_autonomous_replan_increments_version_and_persists(self):
        """Disrupted stop triggers autonomous replanning, increments itinerary version, and marks revised."""
        sess_id = "sess_replan_verify"
        monitor = ItineraryMonitor(db_path=self.db_path)

        conn = get_db_connection(self.db_path)
        cur = conn.cursor()

        # Seed initial saved itinerary with 2 stops
        initial_stops = [
            {"stop_order": 1, "place_id": "ins_kursura", "name": "INS Kursura Submarine Museum"},
            {"stop_order": 2, "place_id": "kailasagiri", "name": "Kailasagiri"},
        ]
        cur.execute(
            """
            INSERT INTO itineraries (
                id, session_id, title, target_date, status, stops_json, total_cost, unpriced_items, summary, version, created_at, updated_at
            ) VALUES ('itin_orig_101', ?, 'Original Plan', '2026-10-10', 'saved', ?, 150.0, 0, 'Original Submarine Tour', 1, ?, ?)
        """,
            (sess_id, json.dumps(initial_stops), datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
        )

        # Trigger disruption on ins_kursura in the isolated DB
        cur.execute(
            "UPDATE attractions SET has_emergency_closure = 1, closure_reason = 'Electrical outage' WHERE id = 'ins_kursura'"
        )
        conn.commit()
        conn.close()

        # Check itinerary health -> must detect disruption
        health = asyncio.run(monitor.check_itinerary_health(sess_id))
        self.assertFalse(health["healthy"])
        self.assertTrue(len(health["affected_stops"]) >= 1)
        self.assertTrue(any(a["place_id"] == "ins_kursura" for a in health["affected_stops"]))

        # Execute autonomous replan
        replan_event = asyncio.run(monitor.autonomous_replan(sess_id, health))
        self.assertEqual(replan_event["type"], "autonomous_replan")
        self.assertEqual(replan_event["version"], 2)
        self.assertEqual(replan_event["old_itinerary_id"], "itin_orig_101")

        # Verify new itinerary persisted in SQLite
        conn = get_db_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, status, version, summary FROM itineraries WHERE session_id = ? ORDER BY version DESC LIMIT 1", (sess_id,))
        new_row = cur.fetchone()
        conn.close()

        self.assertEqual(new_row["version"], 2)
        self.assertEqual(new_row["status"], "revised")
        self.assertIn("Autonomous Replan", new_row["summary"])

    # -------------------------------------------------------------------------
    # 7. Agent Run Failure Persistence
    # -------------------------------------------------------------------------
    def test_agent_failure_persistence_preserves_partial_evidence(self):
        """When an agent run encounters an unhandled failure, partial turns and tool records are saved."""
        sess_id = f"sess_fail_{int(time.time() * 1000)}"

        with patch("app.run_agent_loop") as mock_loop:
            async def failing_loop(*args, **kwargs):
                # Yield one tool call
                yield {
                    "type": "tool_call",
                    "step": 1,
                    "tool_name": "mock_lookup",
                    "status": "success",
                    "args": {"key": "unit_cost"},
                    "result_summary": "150",
                    "output": 150,
                }
                # Then raise unexpected error
                raise RuntimeError("Simulated crash in downstream service")

            mock_loop.side_effect = failing_loop

            resp = self.client.post(
                "/api/agent/stream",
                json={
                    "instruction": "Do something that crashes",
                    "session_id": sess_id,
                    "model": "mock-model",
                },
            )
            self.assertEqual(resp.status_code, 200)

            # Check that partial turn was persisted in session_store
            session_data = session_store.get_session(sess_id)
            self.assertIsNotNone(session_data)
            assistant_turns = [t for t in session_data.get("turns", []) if t.get("role") == "assistant"]
            self.assertTrue(len(assistant_turns) >= 1)
            last_turn = assistant_turns[-1]
            self.assertEqual(last_turn.get("status"), "failed")
            # Verify the partial tool execution was preserved
            tools = last_turn.get("tools", [])
            self.assertTrue(len(tools) >= 1)
            self.assertEqual(tools[0]["tool_name"], "mock_lookup")

    # -------------------------------------------------------------------------
    # 8. Cancellation Endpoint & Semantics
    # -------------------------------------------------------------------------
    def test_agent_run_cancellation_endpoint(self):
        """POST /api/agent/cancel cleanly handles cancellation requests."""
        resp = self.client.post("/api/agent/cancel", json={"session_id": "non_existent_sess"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
