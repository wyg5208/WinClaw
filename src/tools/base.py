"""工具基类 — 所有工具的统一接口规范。

每个工具实现 BaseTool 抽象类，提供：
- 元信息（name / description / actions）
- execute() 执行方法
- get_schema() 生成 OpenAI function calling 兼容的 JSON Schema
"""

from __future__ import annotations

import asyncio
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolResultStatus(str, Enum):
    """工具执行结果状态。"""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    DENIED = "denied"  # 权限被拒绝
    CANCELLED = "cancelled"  # 用户取消


@dataclass
class ToolResult:
    """工具执行结果。"""

    status: ToolResultStatus = ToolResultStatus.SUCCESS
    output: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.status == ToolResultStatus.SUCCESS

    def to_message(self) -> str:
        """转为发送给 AI 模型的文本消息。"""
        if self.is_success:
            return self.output or "(无输出)"
        if self.status == ToolResultStatus.TIMEOUT:
            return f"[超时] 工具执行超时"
        if self.status == ToolResultStatus.DENIED:
            return f"[权限拒绝] {self.error}" if self.error else "[权限拒绝] 操作被拒绝"
        if self.status == ToolResultStatus.CANCELLED:
            return "[取消] 操作已取消"
        return f"[错误] {self.error}" if self.error else f"[{self.status.value}]"


@dataclass
class ActionDef:
    """单个工具动作的定义。"""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON Schema 格式
    required_params: list[str] = field(default_factory=list)


# 默认工具超时时间（秒）
DEFAULT_TOOL_TIMEOUT = 60


class BaseTool(ABC):
    """工具基类。所有工具必须继承此类。"""

    name: str = ""
    emoji: str = "🔧"
    title: str = ""
    description: str = ""
    # 工具执行超时时间（秒），子类可覆盖
    timeout: float = DEFAULT_TOOL_TIMEOUT

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.name:
            cls.name = cls.__name__.lower().replace("tool", "")

    @abstractmethod
    def get_actions(self) -> list[ActionDef]:
        """返回此工具支持的所有动作定义。"""
        ...

    @abstractmethod
    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        """执行指定动作。

        Args:
            action: 动作名称
            params: 动作参数

        Returns:
            ToolResult 执行结果
        """
        ...

    async def safe_execute(self, action: str, params: dict[str, Any], timeout: float | None = None) -> ToolResult:
        """带计时、超时和异常捕获的执行包装器。

        Args:
            action: 动作名称
            params: 动作参数
            timeout: 超时时间（秒），None 则使用类默认值

        Returns:
            ToolResult 执行结果
        """
        start = time.perf_counter()
        actual_timeout = timeout if timeout is not None else self.timeout

        try:
            # 包装超时
            result = await asyncio.wait_for(
                self.execute(action, params),
                timeout=actual_timeout,
            )
        except asyncio.TimeoutError:
            result = ToolResult(
                status=ToolResultStatus.TIMEOUT,
                error=f"工具执行超时 ({actual_timeout}秒)",
            )
        except asyncio.CancelledError:
            result = ToolResult(
                status=ToolResultStatus.CANCELLED,
                error="操作已取消",
            )
        except PermissionError as e:
            result = ToolResult(
                status=ToolResultStatus.DENIED,
                error=f"权限不足: {e}",
            )
        except FileNotFoundError as e:
            result = ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"文件不存在: {e}",
            )
        except Exception as e:
            # 捕获所有其他异常，记录详细堆栈
            exc_type = type(e).__name__
            exc_msg = str(e)
            tb_str = traceback.format_exc()
            logger_msg = f"工具执行异常: {exc_type}: {exc_msg}\n{tb_str}"
            
            # 尝试使用 logging，但如果失败则忽略
            try:
                import logging
                logging.getLogger(__name__).error(logger_msg)
            except Exception:
                pass
            
            result = ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"{exc_type}: {exc_msg}",
            )

        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    def get_schema(self) -> list[dict[str, Any]]:
        """生成 OpenAI function calling 兼容的 tools schema 列表。

        每个 action 生成一个 function 定义，function name 格式为 `{tool_name}_{action_name}`。
        """
        schemas = []
        for action in self.get_actions():
            func_name = f"{self.name}_{action.name}"
            schema: dict[str, Any] = {
                "type": "function",
                "function": {
                    "name": func_name,
                    "description": f"[{self.title}] {action.description}",
                    "parameters": {
                        "type": "object",
                        "properties": action.parameters,
                        "required": action.required_params,
                    },
                },
            }
            schemas.append(schema)
        return schemas

    async def close(self) -> None:
        """清理资源。子类可覆盖以释放资源（如关闭浏览器、释放模型等）。"""
        pass
