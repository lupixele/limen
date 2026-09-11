"""Unit tests for agent/loop.py following TDD."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.tools import CalculatorTool, MockLookupTool, ToolRegistry
from agent.loop import run_agent_loop


class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register(CalculatorTool())
        self.registry.register(MockLookupTool())
        self.provider_url = "http://mock-provider/v1"
        self.api_key = "mock-key"
        self.model = "mock-model"

    def test_immediate_final_answer_without_tools(self):
        """Model decides no tools are needed and directly gives a final answer."""
        mock_response = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "The capital of France is Paris.",
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
                    instruction="What is the capital of France?",
                    registry=self.registry,
                    provider_url=self.provider_url,
                    api_key=self.api_key,
                    model=self.model,
                    max_steps=5,
                ):
                    events.append(event)

            types = [e["type"] for e in events]
            self.assertIn("final_answer", types)
            self.assertIn("done", types)
            final_ev = next(e for e in events if e["type"] == "final_answer")
            self.assertEqual(final_ev["content"], "The capital of France is Paris.")
            self.assertTrue(final_ev["converged"])

        asyncio.run(run())

    def test_adaptive_multi_step_tool_chaining(self):
        """Model calls mock_lookup first, observes result, then calls calculator, then answers."""
        step1_response = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "mock_lookup",
                                    "arguments": json.dumps({"key": "unit_cost"}),
                                },
                            }
                        ],
                    },
                }
            ]
        }

        step2_response = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_2",
                                "type": "function",
                                "function": {
                                    "name": "calculator",
                                    "arguments": json.dumps({"expression": "150 * 3"}),
                                },
                            }
                        ],
                    },
                }
            ]
        }

        step3_response = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "The total cost for 3 units is 450.",
                    },
                }
            ]
        }

        async def run():
            events = []
            with patch("httpx.AsyncClient.post") as mock_post:
                resp1 = MagicMock()
                resp1.status_code = 200
                resp1.json.return_value = step1_response

                resp2 = MagicMock()
                resp2.status_code = 200
                resp2.json.return_value = step2_response

                resp3 = MagicMock()
                resp3.status_code = 200
                resp3.json.return_value = step3_response

                mock_post.side_effect = [resp1, resp2, resp3]

                async for event in run_agent_loop(
                    instruction="Find the unit cost and multiply it by 3",
                    registry=self.registry,
                    provider_url=self.provider_url,
                    api_key=self.api_key,
                    model=self.model,
                    max_steps=5,
                ):
                    events.append(event)

            tool_events = [e for e in events if e["type"] == "tool_call"]
            # 2 calls x 2 events each (running, success)
            self.assertEqual(len(tool_events), 4)
            self.assertEqual(tool_events[0]["tool_name"], "mock_lookup")
            self.assertEqual(tool_events[0]["status"], "running")
            self.assertEqual(tool_events[1]["status"], "success")
            self.assertEqual(tool_events[1]["result_summary"], "150")

            self.assertEqual(tool_events[2]["tool_name"], "calculator")
            self.assertEqual(tool_events[2]["status"], "running")
            self.assertEqual(tool_events[3]["status"], "success")
            self.assertEqual(tool_events[3]["result_summary"], "450")

            final_ev = next(e for e in events if e["type"] == "final_answer")
            self.assertIn("450", final_ev["content"])
            self.assertTrue(final_ev["converged"])

        asyncio.run(run())

    def test_max_steps_limit_exceeded(self):
        """Loop terminates cleanly with converged=False when max_steps is hit."""
        infinite_tool_response = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_loop",
                                "type": "function",
                                "function": {
                                    "name": "calculator",
                                    "arguments": json.dumps({"expression": "1 + 1"}),
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
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = infinite_tool_response
                mock_post.return_value = resp

                async for event in run_agent_loop(
                    instruction="Loop forever",
                    registry=self.registry,
                    provider_url=self.provider_url,
                    api_key=self.api_key,
                    model=self.model,
                    max_steps=3,
                ):
                    events.append(event)

            final_ev = next(e for e in events if e["type"] == "final_answer")
            self.assertFalse(final_ev["converged"])
            self.assertIn("maximum", final_ev["content"].lower())

            done_ev = next(e for e in events if e["type"] == "done")
            self.assertFalse(done_ev["converged"])

        asyncio.run(run())

    def test_plan_artifact_emission(self):
        """Emits generalized plan_artifact if present in response or tool."""
        artifact_response = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": 'Here is the plan:\n```json\n{"columns": ["Task", "Owner"], "rows": [{"Task": "Build", "Owner": "Alice"}]}\n```',
                    },
                }
            ]
        }

        async def run():
            events = []
            with patch("httpx.AsyncClient.post") as mock_post:
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = artifact_response
                mock_post.return_value = resp

                async for event in run_agent_loop(
                    instruction="Generate task table",
                    registry=self.registry,
                    provider_url=self.provider_url,
                    api_key=self.api_key,
                    model=self.model,
                ):
                    events.append(event)

            artifact_events = [e for e in events if e["type"] == "plan_artifact"]
            self.assertEqual(len(artifact_events), 1)
            self.assertEqual(artifact_events[0]["columns"], ["Task", "Owner"])
            self.assertEqual(len(artifact_events[0]["rows"]), 1)

        asyncio.run(run())

    def test_malformed_tool_arguments_graceful_recovery(self):
        """If model returns malformed JSON arguments, it yields error status and continues without crashing."""
        step1_response = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_bad",
                                "type": "function",
                                "function": {
                                    "name": "calculator",
                                    "arguments": "{bad_json",
                                },
                            }
                        ],
                    },
                }
            ]
        }
        step2_response = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "Recovered from bad arguments.",
                    },
                }
            ]
        }

        async def run():
            events = []
            with patch("httpx.AsyncClient.post") as mock_post:
                resp1 = MagicMock()
                resp1.status_code = 200
                resp1.json.return_value = step1_response

                resp2 = MagicMock()
                resp2.status_code = 200
                resp2.json.return_value = step2_response

                mock_post.side_effect = [resp1, resp2]

                async for event in run_agent_loop(
                    instruction="Calculate with bad format",
                    registry=self.registry,
                    provider_url=self.provider_url,
                    api_key=self.api_key,
                    model=self.model,
                ):
                    events.append(event)

            tool_events = [e for e in events if e["type"] == "tool_call"]
            self.assertEqual(tool_events[1]["status"], "error")
            final_ev = next(e for e in events if e["type"] == "final_answer")
            self.assertTrue(final_ev["converged"])

        asyncio.run(run())

    def test_provider_error_handling(self):
        """If the LLM provider returns a 500 error, loop emits error event cleanly."""
        async def run():
            events = []
            with patch("httpx.AsyncClient.post") as mock_post:
                resp = MagicMock()
                resp.status_code = 500
                resp.text = "Internal Server Error"
                mock_post.return_value = resp

                async for event in run_agent_loop(
                    instruction="Hello",
                    registry=self.registry,
                    provider_url=self.provider_url,
                    api_key=self.api_key,
                    model=self.model,
                ):
                    events.append(event)

            error_ev = next(e for e in events if e["type"] == "error")
            self.assertIn("500", error_ev["message"])
            done_ev = next(e for e in events if e["type"] == "done")
            self.assertFalse(done_ev["converged"])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
