"""超时管理器。

管理用户回答追问的超时处理，支持多种超时策略。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, Signal, QTimer

from .ask_parser import TimeoutStrategy

logger = logging.getLogger(__name__)


class TimeoutManager(QObject):
    """管理用户回答超时。

    支持的超时策略：
    - auto_select: 自动选择推荐答案
    - wait_forever: 永远等待
    - retry: 重试一次后放弃
    - default: 使用默认值
    - skip: 跳过该步骤
    """

    # 信号
    timeout_triggered = Signal(str, object)  # 超时触发 (strategy, default_value)
    user_responded = Signal(str)            # 用户响应

    def __init__(self, default_timeout: int = 30):
        """初始化超时管理器。

        Args:
            default_timeout: 默认超时秒数
        """
        super().__init__()
        self._default_timeout = default_timeout
        self._timer: Optional[QTimer] = None
        self._current_strategy: Optional[TimeoutStrategy] = None
        self._current_default: Any = None
        self._current_callback: Optional[Callable] = None
        self._is_active = False

    @property
    def is_active(self) -> bool:
        """是否处于活动状态。"""
        return self._is_active

    def start(
        self,
        strategy: TimeoutStrategy,
        default_value: Any = None,
        timeout_seconds: Optional[int] = None,
        callback: Optional[Callable] = None,
    ) -> None:
        """启动超时计时器。

        Args:
            strategy: 超时策略
            default_value: 默认值（用于auto_select和default策略）
            timeout_seconds: 超时秒数，如果为None则使用默认值
            callback: 超时回调函数
        """
        # 停止已有的计时器
        self.cancel()

        self._current_strategy = strategy
        self._current_default = default_value
        self._current_callback = callback

        # wait_forever 策略不需要计时器
        if strategy == TimeoutStrategy.WAIT_FOREVER:
            self._is_active = True
            logger.info("启动超时管理器: wait_forever (无限等待)")
            return

        # 其他策略启动计时器
        timeout = timeout_seconds or self._default_timeout
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._timer.start(timeout * 1000)

        self._is_active = True
        logger.info(f"启动超时管理器: {strategy.value}, 超时 {timeout}秒")

    def cancel(self) -> None:
        """取消超时计时器（用户响应时调用）。"""
        if self._timer:
            self._timer.stop()
            self._timer = None

        self._is_active = False
        self._current_strategy = None
        self._current_default = None
        self._current_callback = None

        logger.debug("取消超时计时器")

    def on_user_response(self, response: str) -> None:
        """用户响应时调用。

        Args:
            response: 用户的响应内容
        """
        if not self._is_active:
            return

        logger.info(f"用户响应: {response}")
        self.cancel()
        self.user_responded.emit(response)

    def _on_timeout(self) -> None:
        """超时触发处理。"""
        if not self._current_strategy:
            return

        logger.info(f"超时触发: {self._current_strategy.value}")

        # 执行超时策略
        self.timeout_triggered.emit(
            self._current_strategy.value,
            self._current_default
        )

        # 执行回调
        if self._current_callback:
            try:
                self._current_callback(self._current_strategy, self._current_default)
            except Exception as e:
                logger.error(f"超时回调执行失败: {e}")

        # auto_select 和 default 策略超时后继续等待
        # retry 策略只重试一次
        # skip 策略直接结束
        if self._current_strategy in (TimeoutStrategy.AUTO_SELECT, TimeoutStrategy.DEFAULT):
            # 继续等待用户响应，但不设置新的超时
            self._current_strategy = TimeoutStrategy.WAIT_FOREVER
            self._is_active = True
        elif self._current_strategy == TimeoutStrategy.RETRY:
            # 重试一次，设置新的短超时
            self._timer = QTimer()
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._on_retry_timeout)
            self._timer.start(5000)  # 5秒后再次超时
            logger.info("进入重试模式，5秒后再次超时")
        else:
            # skip 策略直接结束
            self._is_active = False

    def _on_retry_timeout(self) -> None:
        """重试超时处理。"""
        logger.info("重试超时，放弃等待")
        self.timeout_triggered.emit(TimeoutStrategy.SKIP.value, None)
        self._is_active = False
        self._timer = None
