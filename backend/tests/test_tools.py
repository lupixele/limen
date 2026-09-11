"""Unit tests for core/tools.py following TDD."""
import asyncio
import unittest
from core.tools import (
    CalculatorTool,
    MockLookupTool,
    ToolRegistry,
    ToolResult,
)


class TestTools(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.calc = CalculatorTool()
        self.lookup = MockLookupTool()
        self.registry.register(self.calc)
        self.registry.register(self.lookup)

    def test_tool_result_serialization(self):
        tr = ToolResult(success=True, output=42)
        self.assertEqual(tr.to_llm_content(), "42")

        tr_err = ToolResult(success=False, output=None, error="Division by zero")
        self.assertIn("Division by zero", tr_err.to_llm_content())

    def test_registry_schemas(self):
        schemas = self.registry.get_schemas()
        self.assertEqual(len(schemas), 2)
        names = [s["function"]["name"] for s in schemas]
        self.assertIn("calculator", names)
        self.assertIn("mock_lookup", names)

    def test_calculator_basic_and_safe_math(self):
        async def run_calc():
            res = await self.calc.run(expression="150 * 42")
            self.assertTrue(res.success)
            self.assertEqual(res.output, 6300)

            res2 = await self.calc.run(expression="(100 + 50) / 2")
            self.assertTrue(res2.success)
            self.assertEqual(res2.output, 75.0)

            # Safety check: disallow builtin calls, imports, eval
            res_unsafe = await self.calc.run(expression="__import__('os').system('dir')")
            self.assertFalse(res_unsafe.success)
            self.assertIn("error", res_unsafe.to_llm_content().lower())

        asyncio.run(run_calc())

    def test_mock_lookup(self):
        async def run_lookup():
            res = await self.lookup.run(key="unit_cost")
            self.assertTrue(res.success)
            self.assertEqual(res.output, 150)

            res_missing = await self.lookup.run(key="non_existent_key")
            self.assertFalse(res_missing.success)
            self.assertIn("Key not found", res_missing.error)

        asyncio.run(run_lookup())

    def test_registry_dispatch_unknown_tool(self):
        async def run_dispatch():
            res = await self.registry.run_tool("unknown_tool", arg=123)
            self.assertFalse(res.success)
            self.assertIn("Tool 'unknown_tool' not found", res.error)

        asyncio.run(run_dispatch())


if __name__ == "__main__":
    unittest.main()
