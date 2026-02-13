"""全局异常处理器 — 捕获并处理未处理异常。

提供三层异常捕获：
1. sys.excepthook: 主线程未捕获异常
2. threading.excepthook: 子线程未捕获异常
3. asyncio 异常处理器: 事件循环中未处理的异常

异常分类：
- NetworkError: 网络连接问题
- ModelError: AI 模型调用问题
- ToolError: 工具执行问题
- ConfigError: 配置问题
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """错误分类。"""

    NETWORK = "network"
    MODEL = "model"
    TOOL = "tool"
    CONFIG = "config"
    UNKNOWN = "unknown"


@dataclass
class ErrorInfo:
    """错误信息封装。"""

    category: ErrorCategory
    message: str
    exception_type: str
    exception_message: str
    traceback_str: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def to_display(self) -> str:
        """生成用户友好的错误提示。"""
        category_names = {
            ErrorCategory.NETWORK: "网络错误",
            ErrorCategory.MODEL: "AI 模型错误",
            ErrorCategory.TOOL: "工具执行错误",
            ErrorCategory.CONFIG: "配置错误",
            ErrorCategory.UNKNOWN: "未知错误",
        }
        return f"[{category_names.get(self.category, '错误')}] {self.message}"


def classify_exception(exc: Exception) -> ErrorCategory:
    """根据异常类型分类错误。"""
    exc_name = type(exc).__name__
    exc_module = type(exc).__module__

    # 网络相关异常
    network_exceptions = {
        "ConnectionError",
        "ConnectionRefusedError",
        "ConnectionResetError",
        "TimeoutError",
        "httpx.ConnectError",
        "httpx.TimeoutException",
        "httpx.NetworkError",
        "APIConnectionError",
        "APITimeoutError",
    }
    if exc_name in network_exceptions or "Connection" in exc_name or "Timeout" in exc_name:
        return ErrorCategory.NETWORK

    # 模型相关异常
    model_exceptions = {
        "RateLimitError",
        "AuthenticationError",
        "ModelNotFoundError",
        "ContextLengthExceededError",
        "ContentPolicyViolationError",
        "APIStatusError",
        "APIError",
    }
    if exc_name in model_exceptions or "API" in exc_name or "Model" in exc_name:
        return ErrorCategory.MODEL

    # 配置相关异常
    config_exceptions = {
        "ConfigError",
        "ValidationError",
        "KeyError",
        "FileNotFoundError",
        "PermissionError",
    }
    if exc_name in config_exceptions:
        return ErrorCategory.CONFIG

    # 工具相关异常
    if "Tool" in exc_name or "Action" in exc_name:
        return ErrorCategory.TOOL

    return ErrorCategory.UNKNOWN


def create_error_info(exc: Exception, context: dict[str, Any] | None = None) -> ErrorInfo:
    """从异常创建 ErrorInfo。"""
    category = classify_exception(exc)
    exc_type = type(exc).__name__

    # 生成用户友好的消息
    message_map = {
        ErrorCategory.NETWORK: "网络连接出现问题，请检查网络设置后重试",
        ErrorCategory.MODEL: "AI 模型调用失败，请稍后重试或切换模型",
        ErrorCategory.TOOL: "工具执行过程中出现错误",
        ErrorCategory.CONFIG: "配置有误，请检查设置",
        ErrorCategory.UNKNOWN: f"发生未知错误: {exc_type}",
    }

    message = message_map.get(category, str(exc))

    return ErrorInfo(
        category=category,
        message=message,
        exception_type=exc_type,
        exception_message=str(exc),
        traceback_str=traceback.format_exc(),
        context=context or {},
    )


class GlobalErrorHandler:
    """全局异常处理器。

    用法：
        handler = GlobalErrorHandler()
        handler.install()

        # 设置错误回调
        handler.on_error = lambda error_info: print(error_info.to_display())
    """

    def __init__(self) -> None:
        self._original_excepthook: Callable | None = None
        self._original_threading_excepthook: Callable | None = None
        self._original_asyncio_handler: Callable | None = None
        self.on_error: Callable[[ErrorInfo], None] | None = None
        self._installed = False

    def install(self) -> None:
        """安装全局异常处理器。"""
        if self._installed:
            return

        # 保存原始处理器
        self._original_excepthook = sys.excepthook
        self._original_threading_excepthook = threading.excepthook

        # 安装主线程异常处理器
        sys.excepthook = self._handle_exception

        # 安装子线程异常处理器 (Python 3.8+)
        if hasattr(threading, "excepthook"):
            threading.excepthook = self._handle_threading_exception

        self._installed = True
        logger.info("全局异常处理器已安装")

    def uninstall(self) -> None:
        """卸载全局异常处理器。"""
        if not self._installed:
            return

        if self._original_excepthook:
            sys.excepthook = self._original_excepthook

        if self._original_threading_excepthook and hasattr(threading, "excepthook"):
            threading.excepthook = self._original_threading_excepthook

        self._installed = False
        logger.info("全局异常处理器已卸载")

    def install_asyncio_handler(self, loop: asyncio.AbstractEventLoop) -> None:
        """为指定的 asyncio 事件循环安装异常处理器。"""
        self._original_asyncio_handler = loop.get_exception_handler()
        loop.set_exception_handler(self._handle_asyncio_exception)
        logger.debug("asyncio 异常处理器已安装")

    def _handle_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: Any,
    ) -> None:
        """处理主线程未捕获异常。"""
        try:
            if isinstance(exc_value, Exception):
                error_info = create_error_info(exc_value)
                logger.error(
                    "未捕获异常: %s: %s\n%s",
                    exc_type.__name__,
                    exc_value,
                    "".join(traceback.format_tb(exc_tb)),
                )

                if self.on_error:
                    try:
                        self.on_error(error_info)
                    except Exception as e:
                        logger.error("错误回调执行失败: %s", e)

            # 调用原始处理器（如果有）
            if self._original_excepthook:
                self._original_excepthook(exc_type, exc_value, exc_tb)

        except Exception as e:
            # 处理器本身出错，记录但不要崩溃
            logger.critical("异常处理器内部错误: %s", e)

    def _handle_threading_exception(self, args: threading.ExceptHookArgs) -> None:
        """处理子线程未捕获异常。"""
        try:
            if args.exc_type and issubclass(args.exc_type, Exception):
                exc = args.exc_value or args.exc_type()
                error_info = create_error_info(exc, context={"thread": args.thread.name if args.thread else "unknown"})

                logger.error(
                    "子线程未捕获异常 [%s]: %s: %s",
                    args.thread.name if args.thread else "unknown",
                    args.exc_type.__name__,
                    args.exc_value,
                )

                if self.on_error:
                    try:
                        self.on_error(error_info)
                    except Exception as e:
                        logger.error("错误回调执行失败: %s", e)

            # 调用原始处理器
            if self._original_threading_excepthook:
                self._original_threading_excepthook(args)

        except Exception as e:
            logger.critical("线程异常处理器内部错误: %s", e)

    def _handle_asyncio_exception(
        self,
        loop: asyncio.AbstractEventLoop,
        context: dict[str, Any],
    ) -> None:
        """处理 asyncio 未捕获异常。"""
        try:
            exc = context.get("exception")
            if exc and isinstance(exc, Exception):
                error_info = create_error_info(
                    exc,
                    context={
                        "task": str(context.get("task")),
                        "message": context.get("message", ""),
                    },
                )

                logger.error(
                    "asyncio 未处理异常: %s: %s",
                    type(exc).__name__,
                    exc,
                )

                if self.on_error:
                    try:
                        self.on_error(error_info)
                    except Exception as e:
                        logger.error("错误回调执行失败: %s", e)

            elif context.get("message"):
                # 没有 exception 但有 message 的情况
                logger.warning("asyncio 警告: %s", context.get("message"))

            # 调用原始处理器
            if self._original_asyncio_handler:
                self._original_asyncio_handler(loop, context)

        except Exception as e:
            logger.critical("asyncio 异常处理器内部错误: %s", e)


# 全局单例
_global_handler: GlobalErrorHandler | None = None


def get_global_handler() -> GlobalErrorHandler:
    """获取全局异常处理器单例。"""
    global _global_handler
    if _global_handler is None:
        _global_handler = GlobalErrorHandler()
    return _global_handler


def install_error_handler(on_error: Callable[[ErrorInfo], None] | None = None) -> GlobalErrorHandler:
    """安装全局异常处理器。

    Args:
        on_error: 错误回调函数，接收 ErrorInfo 参数

    Returns:
        GlobalErrorHandler 实例
    """
    handler = get_global_handler()
    if on_error:
        handler.on_error = on_error
    handler.install()
    return handler
