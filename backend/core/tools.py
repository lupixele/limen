"""Generic Tool Protocol and Registry for Agentic Execution."""
import ast
import json
import operator
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class ToolResult:
    success: bool
    output: Any = None
    error: Optional[str] = None
    artifact: Optional[Dict[str, Any]] = None

    def to_llm_content(self) -> str:
        if not self.success:
            return f"Error: {self.error or 'Unknown tool execution error'}"
        if isinstance(self.output, (dict, list)):
            return json.dumps(self.output)
        return str(self.output)


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    json_schema: Dict[str, Any]

    async def run(self, **kwargs) -> ToolResult:
        ...


class CalculatorTool:
    name: str = "calculator"
    description: str = (
        "Evaluate a safe mathematical expression (supports +, -, *, /, //, %, **, parentheses). "
        "Does not allow variables, system calls, or arbitrary Python execution."
    )
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate, e.g. '150 * 42' or '(100 + 50) / 2'",
            }
        },
        "required": ["expression"],
    }

    _OPERATORS: Dict[type, Callable[[Any, Any], Any]] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    _UNARY_OPERATORS: Dict[type, Callable[[Any], Any]] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def _eval_node(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return node.value
            raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self._OPERATORS:
                raise ValueError(f"Unsupported binary operator: {op_type.__name__}")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            if op_type == ast.Pow and isinstance(right, (int, float)) and right > 1000:
                raise ValueError("Exponent too large (max 1000)")
            return self._OPERATORS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self._UNARY_OPERATORS:
                raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
            operand = self._eval_node(node.operand)
            return self._UNARY_OPERATORS[op_type](operand)
        else:
            raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    async def run(self, **kwargs) -> ToolResult:
        expr = kwargs.get("expression")
        if not expr or not isinstance(expr, str):
            return ToolResult(success=False, error="Parameter 'expression' must be a non-empty string.")

        try:
            tree = ast.parse(expr.strip(), mode="eval")
            result = self._eval_node(tree.body)
            return ToolResult(success=True, output=result)
        except ZeroDivisionError:
            return ToolResult(success=False, error="Division by zero")
        except OverflowError:
            return ToolResult(success=False, error="Math overflow error")
        except Exception as e:
            return ToolResult(success=False, error=f"Invalid expression or evaluation error: {str(e)}")


class MockLookupTool:
    name: str = "mock_lookup"
    description: str = (
        "Retrieve data entries from a mock database by key. Available keys: "
        "stock_level, reorder_threshold, unit_cost, item_count, annual_growth, laptop_price, tax_rate, shipping_fee, discount_rate."
    )
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "The exact database key to query.",
            }
        },
        "required": ["key"],
    }

    _DEFAULT_MOCK_DATA: Dict[str, Any] = {
        "unit_cost": 150,
        "item_count": 42,
        "annual_growth": 0.15,
        "laptop_price": 1200,
        "tax_rate": 0.08,
        "shipping_fee": 25,
        "discount_rate": 0.10,
        "stock_level": 30,
        "reorder_threshold": 50,
    }

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self._mock_data = dict(self._DEFAULT_MOCK_DATA)
        if data:
            self._mock_data.update(data)

    def set_value(self, key: str, value: Any) -> None:
        self._mock_data[key.strip().lower()] = value

    async def run(self, **kwargs) -> ToolResult:
        key = kwargs.get("key")
        if not key or not isinstance(key, str):
            return ToolResult(
                success=False,
                error=f"Parameter 'key' must be a non-empty string. Available keys: {list(self._mock_data.keys())}",
            )

        key_clean = key.strip().lower()
        if key_clean in self._mock_data:
            return ToolResult(success=True, output=self._mock_data[key_clean])

        return ToolResult(
            success=False,
            error=f"Key not found: '{key}'. Available keys: {list(self._mock_data.keys())}",
        )


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def get_schemas(self) -> List[Dict[str, Any]]:
        schemas = []
        for tool in self._tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.json_schema,
                },
            })
        return schemas

    async def run_tool(self, name: str, **kwargs) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' not found. Available tools: {list(self._tools.keys())}"
            )

        try:
            return await tool.run(**kwargs)
        except Exception as e:
            return ToolResult(success=False, error=f"Tool execution failed: {str(e)}")
