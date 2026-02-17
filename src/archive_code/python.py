"""Python 工具 — 安全的 Python 代码执行沙盒。

支持动作：
- execute: 执行 Python 代码

安全特性：
- AST 白名单解析
- 模块导入限制
- 函数调用限制
- 执行超时保护
- 输出大小限制
"""

from __future__ import annotations

import logging
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus
from src.tools.sandbox import execute_code

logger = logging.getLogger(__name__)


class PythonTool(BaseTool):
    """Python 沙盒执行工具。

    使用 AST 解析和受限命名空间，安全执行用户提交的 Python 代码。
    支持数学计算、数据处理、文本处理等场景。
    
    允许的模块：math, random, datetime, json, re
    允许的操作：基本语法、列表/字典操作、正则表达式等
    禁止的操作：文件访问（除生成目录）、网络请求、系统调用等
    """

    name = "python"
    emoji = "🐍"
    title = "Python 执行"
    description = "安全执行 Python 代码，支持数学计算、数据处理"
    timeout = 30  # 30 秒超时

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="execute",
                description=(
                    "执行 Python 代码。\n"
                    "支持：数学运算(math)、随机数(random)、"
                    "日期时间(datetime)、JSON处理(json)、正则表达式(re)。\n"
                    "示例：\n"
                    "- 计算: '2 + 3 * 4'\n"
                    "- 列表: '[x**2 for x in range(10)]'\n"
                    "- 字典: '{k: v for k, v in items}'\n"
                    "- JSON: \"json.dumps({'a': 1})\"\n"
                    "- 正则: \"re.findall(r'\\d+', 'abc123def456')\"\n"
                    "- 返回值: 用 'result = ...' 赋值，最后会自动返回"
                ),
                parameters={
                    "code": {
                        "type": "string",
                        "description": "要执行的 Python 代码。推荐使用英文符号。",
                    },
                },
                required_params=["code"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        """执行 Python 代码。"""
        if action != "execute":
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )

        code = params.get("code", "").strip()
        if not code:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="代码不能为空",
            )

        # 执行代码
        result = execute_code(code)

        if result.success:
            # 构建输出
            output_parts = []
            
            if result.output:
                output_parts.append(result.output)
            
            # 添加返回值
            if result.return_value is not None:
                return_str = repr(result.return_value)
                if len(return_str) > 1000:
                    return_str = return_str[:1000] + "..."
                output_parts.append(f"[返回值] {return_str}")
            
            output = "\n".join(output_parts) if output_parts else "(无输出)"
            
            logger.info(
                "Python 执行成功，耗时 %.2fms",
                result.duration_ms,
            )
            
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=output,
                data={
                    "return_value": result.return_value,
                    "duration_ms": result.duration_ms,
                },
            )
        else:
            logger.warning("Python 执行失败: %s", result.error)
            
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=result.error,
            )
