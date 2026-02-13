"""Qt + asyncio 事件循环桥接层。

使用 qasync 库实现 PySide6 与 asyncio 的共存，确保：
1. Qt UI 响应流畅，不阻塞主线程
2. asyncio 任务正常执行
3. 无死锁、无事件循环冲突
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Callable, Coroutine

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop


class AsyncBridge(QObject):
    """异步桥接器：在 Qt 事件循环中运行 asyncio 任务。"""

    # 信号：用于从异步任务向 UI 线程发送结果
    task_finished = Signal(object, object)  # (result, error)
    task_progress = Signal(str, object)  # (task_id, progress_data)

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._app: QApplication | None = None

    def setup(self, app: QApplication) -> asyncio.AbstractEventLoop:
        """设置事件循环桥接。

        Args:
            app: Qt 应用程序实例

        Returns:
            asyncio 事件循环实例
        """
        self._app = app
        # 使用 qasync 创建与 Qt 集成的事件循环
        self._loop = QEventLoop(app)
        asyncio.set_event_loop(self._loop)
        return self._loop

    def run(self) -> None:
        """启动事件循环（阻塞）。"""
        if self._loop is None:
            raise RuntimeError("必须先调用 setup()")
        self._loop.run_forever()

    def stop(self) -> None:
        """停止事件循环。"""
        if self._loop:
            self._loop.stop()

    def create_task(
        self,
        coro: Coroutine[Any, Any, Any],
        callback: Callable[[Any], None] | None = None,
        error_callback: Callable[[Exception], None] | None = None,
    ) -> asyncio.Task[Any]:
        """创建异步任务并在完成时通知 UI。

        Args:
            coro: 要运行的协程
            callback: 成功完成时的回调函数
            error_callback: 发生错误时的回调函数

        Returns:
            asyncio.Task 实例
        """
        if self._loop is None:
            raise RuntimeError("必须先调用 setup()")

        task = self._loop.create_task(coro)

        # 连接信号到回调
        if callback or error_callback:
            self._connect_task_signals(task, callback, error_callback)

        return task

    def _connect_task_signals(
        self,
        task: asyncio.Task[Any],
        callback: Callable[[Any], None] | None,
        error_callback: Callable[[Exception], None] | None,
    ) -> None:
        """连接任务完成信号到回调。"""

        def on_done(t: asyncio.Task[Any]) -> None:
            try:
                result = t.result()
                if callback:
                    # 使用信号确保在主线程执行
                    self.task_finished.emit(result, None)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                if error_callback:
                    self.task_finished.emit(None, e)

        task.add_done_callback(on_done)

    def run_coroutine(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """同步运行协程并返回结果（用于非 UI 线程调用）。

        警告：此方法会阻塞直到协程完成，不要在主线程使用。
        """
        if self._loop is None:
            raise RuntimeError("必须先调用 setup()")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def schedule_in_main_thread(self, func: Callable[..., None], *args: Any) -> None:
        """在主线程中调度函数执行。

        Args:
            func: 要执行的函数
            *args: 函数参数
        """
        if self._app:
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG

            QMetaObject.invokeMethod(
                self,
                lambda: func(*args),
                Qt.ConnectionType.QueuedConnection,
            )


class TaskRunner(QObject):
    """任务运行器：封装常用异步任务模式。"""

    started = Signal(str)  # task_id
    finished = Signal(str, object)  # (task_id, result)
    error = Signal(str, str)  # (task_id, error_message)
    progress = Signal(str, object)  # (task_id, progress_data)

    def __init__(self, bridge: AsyncBridge) -> None:
        super().__init__()
        self._bridge = bridge
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def run(
        self,
        task_id: str,
        coro: Coroutine[Any, Any, Any],
    ) -> asyncio.Task[Any]:
        """运行异步任务并自动处理信号。

        Args:
            task_id: 任务唯一标识
            coro: 要运行的协程

        Returns:
            asyncio.Task 实例
        """
        self.started.emit(task_id)

        async def wrapped() -> Any:
            try:
                result = await coro
                self.finished.emit(task_id, result)
                return result
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.error.emit(task_id, str(e))
                raise

        task = self._bridge.create_task(wrapped())
        self._tasks[task_id] = task
        return task

    def cancel(self, task_id: str) -> bool:
        """取消指定任务。

        Args:
            task_id: 任务唯一标识

        Returns:
            是否成功取消
        """
        task = self._tasks.get(task_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def cancel_all(self) -> None:
        """取消所有运行中的任务。"""
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        self._tasks.clear()


def create_application() -> QApplication:
    """创建 Qt 应用程序实例。

    Returns:
        QApplication 实例
    """
    from src import __version__
    app = QApplication(sys.argv)
    app.setApplicationName("WinClaw")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("OpenClaw")
    
    # 设置默认字体，避免 Windows 回退到 MS Sans Serif
    from PySide6.QtGui import QFont
    default_font = QFont("Segoe UI", 9)
    default_font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(default_font)
    
    return app


def setup_async_bridge(app: QApplication) -> AsyncBridge:
    """设置异步桥接。

    Args:
        app: Qt 应用程序实例

    Returns:
        AsyncBridge 实例
    """
    bridge = AsyncBridge()
    bridge.setup(app)
    return bridge
