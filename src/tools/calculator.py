"""Calculator 工具 — 安全的数学表达式计算器。

支持动作：
- calculate: 计算数学表达式（加减乘除、括号、幂运算、百分比）

借鉴来源：参考项目_changoai/backend/tool_functions.py calculate()
"""

from __future__ import annotations

import ast
import logging
import math
import operator
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

# 安全的运算符映射
_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# 安全的数学常量和函数
_SAFE_NAMES: dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "int": int,
    "float": float,
}


def _safe_eval(node: ast.AST) -> float | int:
    """递归安全求值 AST 节点（不使用 eval，完全安全）。"""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"不支持的常量类型: {type(node.value).__name__}")
    elif isinstance(node, ast.BinOp):
        op_func = _SAFE_OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        # 防止除以零
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise ZeroDivisionError("除数不能为零")
        # 防止过大的幂运算
        if isinstance(node.op, ast.Pow):
            if isinstance(right, (int, float)) and abs(right) > 1000:
                raise ValueError("指数过大（最大 1000）")
        return op_func(left, right)
    elif isinstance(node, ast.UnaryOp):
        op_func = _SAFE_OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
        return op_func(_safe_eval(node.operand))
    elif isinstance(node, ast.Call):
        # 安全函数调用（如 sqrt(4)、abs(-3)）
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_NAMES:
            func = _SAFE_NAMES[node.func.id]
            if callable(func):
                args = [_safe_eval(arg) for arg in node.args]
                return func(*args)
        raise ValueError(f"不允许的函数调用: {ast.dump(node.func)}")
    elif isinstance(node, ast.Name):
        # 安全常量引用（如 pi、e）
        if node.id in _SAFE_NAMES:
            val = _SAFE_NAMES[node.id]
            if not callable(val):
                return val
        raise ValueError(f"不允许的变量: {node.id}")
    else:
        raise ValueError(f"不支持的表达式类型: {type(node).__name__}")


class CalculatorTool(BaseTool):
    """安全的数学计算器工具。

    使用 AST 解析而非 eval，完全避免代码注入风险。
    支持：四则运算、括号、幂运算（**）、取模（%）、
    数学常量（pi、e）、数学函数（sqrt、abs、round）。
    """

    name = "calculator"
    emoji = "🔢"
    title = "计算器"
    description = "安全的数学表达式计算器，支持四则运算、括号、幂运算和常用数学函数"

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="calculate",
                description=(
                    "计算数学表达式。支持 +、-、*、/、//（整除）、%（取余）、**（幂）、"
                    "括号、pi、e、sqrt()、abs()、round()。"
                    "示例: '2 + 3 * 4', 'sqrt(144)', '3.14 * 10**2'"
                ),
                parameters={
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 '2 + 3 * 4'、'sqrt(144)'、'pi * 10**2'",
                    },
                },
                required_params=["expression"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        if action != "calculate":
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return self._calculate(params)

    def _calculate(self, params: dict[str, Any]) -> ToolResult:
        expression = params.get("expression", "").strip()
        if not expression:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="表达式不能为空",
            )

        # 预处理：替换中文符号
        expr = (
            expression
            .replace("×", "*")
            .replace("÷", "/")
            .replace("（", "(")
            .replace("）", ")")
        )

        try:
            tree = ast.parse(expr, mode="eval")
            result = _safe_eval(tree)

            # 格式化结果
            if isinstance(result, float):
                # 如果结果是整数浮点数（如 4.0），显示为整数
                if result == int(result) and not math.isinf(result):
                    result_str = str(int(result))
                else:
                    result_str = f"{result:.10g}"
            else:
                result_str = str(result)

            logger.info("计算: %s = %s", expression, result_str)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"计算结果: {expression} = {result_str}",
                data={
                    "expression": expression,
                    "result": result if not math.isinf(result) else str(result),
                    "result_str": result_str,
                },
            )
        except ZeroDivisionError:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"计算错误: 除数不能为零 ({expression})",
            )
        except (ValueError, TypeError) as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"表达式错误: {e}",
            )
        except SyntaxError:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"表达式语法错误: {expression}",
            )
