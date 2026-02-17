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

    def to_message(self, failure_count: int = 0) -> str:
        """转为发送给 AI 模型的文本消息（支持分级错误反馈）。

        Phase 6 增强：根据连续失败次数分级返回不同详细程度的错误信息。
        - 首次失败：简短版（1行）
        - 第二次失败：标准版（2-3行，含建议）
        - 连续3次+：详细版（含错误类型、可能原因、建议操作）

        Args:
            failure_count: 当前连续失败次数（0 表示首次或成功）
        """
        if self.is_success:
            return self.output or "(无输出)"
        if self.status == ToolResultStatus.TIMEOUT:
            if failure_count <= 1:
                return "[超时] 工具执行超时"
            return (
                "[超时] 工具执行超时\n"
                "建议: 1)检查服务是否响应 2)如多次超时请向用户说明"
            )
        if self.status == ToolResultStatus.DENIED:
            return f"[权限拒绝] {self.error}" if self.error else "[权限拒绝] 操作被拒绝"
        if self.status == ToolResultStatus.CANCELLED:
            return "[取消] 操作已取消"

        # 错误状态：分级反馈
        error_text = self.error or "未知错误"

        if failure_count <= 1:
            # 简短版
            return f"[错误] {error_text}"
        elif failure_count <= 2:
            # 标准版
            error_type = self._extract_error_type()
            return (
                f"[错误] {error_text}\n"
                f"类型: {error_type}\n"
                f"建议: 1)检查参数和服务状态 2)如多次失败请向用户说明"
            )
        else:
            # 详细版
            error_type = self._extract_error_type()
            return (
                f"[错误] {error_text}\n"
                f"- 错误类型: {error_type}\n"
                f"- 耗时: {self.duration_ms:.0f}ms\n"
                f"- 建议操作:\n"
                f"  1. 检查工具参数是否正确\n"
                f"  2. 检查相关服务是否正常运行\n"
                f"  3. 如果多次失败，向用户说明情况\n"
                f"- 注意: 不要调用其他不相关的工具来替代"
            )

    def _extract_error_type(self) -> str:
        """从错误信息中提取错误类型。"""
        if not self.error:
            return "Unknown"
        # 尝试提取 "ExceptionType: message" 格式
        if ": " in self.error:
            return self.error.split(": ", 1)[0]
        return self.status.value


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
