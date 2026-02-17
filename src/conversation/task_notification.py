"""任务通知处理器。

处理后台任务完成时的UI通知和状态更新。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, Signal

from .task_scheduler import TaskPriority, get_scheduler

logger = logging.getLogger(__name__)


class TaskNotificationHandler(QObject):
    """任务通知处理器。

    负责：
    - 监听任务状态变化
    - 更新UI显示
    - 显示完成通知
    """

    # 信号
    task_status_changed = Signal(str, str)  # (task_id, status)
    task_count_changed = Signal(int, int)   # (pending_count, running_count)
    all_tasks_completed = Signal()          # 所有任务完成

    def __init__(
        self,
        main_window: Optional[Any] = None,
        on_task_complete: Optional[Callable[[str, Any], None]] = None,
        on_task_fail: Optional[Callable[[str, str], None]] = None,
    ):
        """初始化任务通知处理器。

        Args:
            main_window: 主窗口实例
            on_task_complete: 任务完成回调
            on_task_fail: 任务失败回调
        """
        super().__init__()
        self._main_window = main_window
        self._on_task_complete = on_task_complete
        self._on_task_fail = on_task_fail
        self._scheduler = get_scheduler()

        # 记录任务名称
        self._task_names: dict[str, str] = {}

        self._connect_signals()

    def _connect_signals(self) -> None:
        """连接信号。"""
        # 连接调度器信号
        self._scheduler.task_submitted.connect(self._on_task_submitted)
        self._scheduler.task_started.connect(self._on_task_started)
        self._scheduler.task_completed.connect(self._on_task_completed)
        self._scheduler.task_failed.connect(self._on_task_failed)
        self._scheduler.task_cancelled.connect(self._on_task_cancelled)
        self._scheduler.task_queue_changed.connect(self._on_queue_changed)
        self._scheduler.all_idle.connect(self._on_all_idle)

    def submit_task(
        self,
        name: str,
        coroutine,
        priority: TaskPriority = TaskPriority.TOOL_EXECUTION,
    ) -> str:
        """提交任务。

        Args:
            name: 任务名称
            coroutine: 协程
            priority: 优先级

        Returns:
            任务ID
        """
        task_id = self._scheduler.submit(name, coroutine, priority)
        self._task_names[task_id] = name
        return task_id

    def cancel_task(self, task_id: str) -> bool:
        """取消任务。

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消
        """
        return self._scheduler.cancel(task_id)

    def cancel_all_tasks(self, priority: Optional[TaskPriority] = None) -> int:
        """取消所有任务。

        Args:
            priority: 优先级筛选

        Returns:
            取消的任务数
        """
        return self._scheduler.cancel_all(priority)

    def get_queue_info(self) -> dict:
        """获取队列信息。"""
        return self._scheduler.get_queue_info()

    # ========== 信号处理 ==========

    def _on_task_submitted(self, task_id: str) -> None:
        """任务提交处理。"""
        name = self._task_names.get(task_id, "未知任务")
        logger.info(f"任务已提交: {task_id} ({name})")
        self.task_status_changed.emit(task_id, "submitted")

        # 更新UI
        if self._main_window:
            self._main_window.add_tool_log(f"📝 任务已提交: {name}")

    def _on_task_started(self, task_id: str) -> None:
        """任务开始处理。"""
        name = self._task_names.get(task_id, "未知任务")
        logger.info(f"任务开始: {task_id} ({name})")
        self.task_status_changed.emit(task_id, "running")

        # 更新UI
        if self._main_window:
            self._main_window.add_tool_log(f"🔄 任务执行中: {name}")

    def _on_task_completed(self, task_id: str, result: Any) -> None:
        """任务完成处理。"""
        name = self._task_names.get(task_id, "未知任务")
        logger.info(f"任务完成: {task_id} ({name})")
        self.task_status_changed.emit(task_id, "completed")

        # 更新UI
        if self._main_window:
            self._main_window.add_tool_log(f"✅ 任务完成: {name}")

            # 执行回调
            if self._on_task_complete:
                try:
                    self._on_task_complete(task_id, result)
                except Exception as e:
                    logger.error(f"任务完成回调错误: {e}")

    def _on_task_failed(self, task_id: str, error: str) -> None:
        """任务失败处理。"""
        name = self._task_names.get(task_id, "未知任务")
        logger.error(f"任务失败: {task_id} ({name}), 错误: {error}")
        self.task_status_changed.emit(task_id, "failed")

        # 更新UI
        if self._main_window:
            self._main_window.add_tool_log(f"❌ 任务失败: {name} - {error}")

            # 执行回调
            if self._on_task_fail:
                try:
                    self._on_task_fail(task_id, error)
                except Exception as e:
                    logger.error(f"任务失败回调错误: {e}")

    def _on_task_cancelled(self, task_id: str) -> None:
        """任务取消处理。"""
        name = self._task_names.get(task_id, "未知任务")
        logger.info(f"任务取消: {task_id} ({name})")
        self.task_status_changed.emit(task_id, "cancelled")

    def _on_queue_changed(self, pending: int, running: int) -> None:
        """队列变化处理。"""
        self.task_count_changed.emit(pending, running)

        # 更新UI状态栏
        if self._main_window:
            if running > 0:
                self._main_window.set_tool_status(f"🔄 {running}个任务执行中")
            elif pending > 0:
                self._main_window.set_tool_status(f"📝 {pending}个任务等待中")
            else:
                self._main_window.set_tool_status("空闲")

    def _on_all_idle(self) -> None:
        """所有任务完成处理。"""
        logger.info("所有任务已完成")
        self.all_tasks_completed.emit()

        # 更新UI
        if self._main_window:
            self._main_window.set_tool_status("完成")
            self._main_window.add_tool_log("🎉 所有任务已完成")


class TaskResultHandler(QObject):
    """任务结果处理器。

    专门处理任务结果，根据任务类型执行不同操作。
    """

    # 信号
    tool_result_ready = Signal(str, dict)  # (task_id, result)
    chat_result_ready = Signal(str, str)  # (task_id, text)

    def __init__(self, main_window: Optional[Any] = None):
        """初始化结果处理器。

        Args:
            main_window: 主窗口实例
        """
        super().__init__()
        self._main_window = main_window
        self._notification_handler = TaskNotificationHandler(main_window)

        # 连接信号
        self._notification_handler.task_completed.connect(self._handle_result)

    def _handle_result(self, task_id: str, result: Any) -> None:
        """处理任务结果。"""
        # 根据结果类型处理
        if isinstance(result, dict):
            # 工具执行结果
            self.tool_result_ready.emit(task_id, result)
        elif isinstance(result, str):
            # 聊天结果
            self.chat_result_ready.emit(task_id, result)

    def submit_tool_task(
        self,
        name: str,
        coro,
    ) -> str:
        """提交工具执行任务。"""
        return self._notification_handler.submit_task(
            name,
            coro,
            TaskPriority.TOOL_EXECUTION,
        )

    def submit_chat_task(
        self,
        name: str,
        coro,
    ) -> str:
        """提交聊天任务。"""
        return self._notification_handler.submit_task(
            name,
            coro,
            TaskPriority.CHAT_RESPONSE,
        )

    def submit_user_task(
        self,
        name: str,
        coro,
    ) -> str:
        """提交用户输入任务（最高优先级）。"""
        return self._notification_handler.submit_task(
            name,
            coro,
            TaskPriority.USER_INPUT,
        )
