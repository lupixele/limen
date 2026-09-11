"""Unit tests for FastAPI endpoints in app.py."""
import json
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app import app


class TestAppAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_config(self):
        resp = self.client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("provider_url", data)
        self.assertIn("active_model", data)

    def test_update_config(self):
        original = self.client.get("/api/config").json()
        orig_model = original["active_model"]
        try:
            resp = self.client.post("/api/config", json={"active_model": "test-model-temp"})
            self.assertEqual(resp.status_code, 200)
            resp2 = self.client.get("/api/config")
            self.assertEqual(resp2.json()["active_model"], "test-model-temp")
        finally:
            # Restore original model
            self.client.post("/api/config", json={"active_model": orig_model})

    def test_sessions_lifecycle(self):
        # Create session
        create_resp = self.client.post("/api/sessions", json={"title": "Test Chat"})
        self.assertEqual(create_resp.status_code, 200)
        sess = create_resp.json()
        sess_id = sess["id"]

        # List sessions
        list_resp = self.client.get("/api/sessions")
        self.assertEqual(list_resp.status_code, 200)
        ids = [s["id"] for s in list_resp.json()]
        self.assertIn(sess_id, ids)

        # Get session
        get_resp = self.client.get(f"/api/sessions/{sess_id}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["title"], "Test Chat")

        # Delete session
        del_resp = self.client.delete(f"/api/sessions/{sess_id}")
        self.assertEqual(del_resp.status_code, 200)

    @patch("app.run_agent_loop")
    def test_stream_agent_sse_output(self, mock_loop):
        async def mock_event_gen(*args, **kwargs):
            yield {
                "type": "tool_call",
                "step": 1,
                "tool_name": "mock_lookup",
                "status": "running",
                "args": {"key": "unit_cost"},
                "result_summary": "",
            }
            yield {
                "type": "tool_call",
                "step": 1,
                "tool_name": "mock_lookup",
                "status": "success",
                "args": {"key": "unit_cost"},
                "result_summary": "150",
            }
            yield {
                "type": "final_answer",
                "step": 2,
                "content": "Result is 150",
                "converged": True,
            }
            yield {
                "type": "done",
                "session_id": "test_sess",
                "converged": True,
            }

        mock_loop.side_effect = mock_event_gen

        resp = self.client.post(
            "/api/agent/stream",
            json={
                "instruction": "Look up unit cost",
                "session_id": "test_sess",
                "model": "test-model",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.headers["content-type"])
        body = resp.text
        self.assertIn("data: ", body)
        self.assertIn('"type": "tool_call"', body)
        self.assertIn('"type": "final_answer"', body)
        self.assertIn('"type": "done"', body)


if __name__ == "__main__":
    unittest.main()
