"""并行任务调度器。

管理多个任务的并行执行，支持优先级排序、并发控制、任务状态跟踪。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine, Dict, List, Optional
from weakref import WeakValueDictionary

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class TaskPriority(IntEnum):
    """任务优先级（数值越小优先级越高）。"""
    ASK_RESPONSE = 0     # 用户追问响应（最高优先级）
    USER_INPUT = 1      # 用户新输入
    CHAT_RESPONSE = 2   # AI聊天响应
    TTS_PLAYBACK = 3    # TTS播放
    TOOL_EXECUTION = 4  # 工具执行（最低优先级）


class TaskStatus(IntEnum):
    """任务状态。"""
    PENDING = 0    # 等待中
    RUNNING = 1    # 执行中
    COMPLETED = 2  # 已完成
    CANCELLED = 3  # 已取消
    FAILED = 4     # 失败


@dataclass
class Task:
    """任务数据结构。"""
    id: str
    name: str
    priority: TaskPriority
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[Exception] = None
    callback: Optional[Callable] = None
    coroutine: Optional[Coroutine] = None
    created_at: float = field(default_factory=asyncio.get_event_loop().time)


class TaskScheduler(QObject):
    """并行任务调度器。

    管理多个任务的并行执行，支持：
    - 优先级排序（P0最高，P4最低）
    - 并发控制（最多MAX_PARALLEL_TASKS个并行）
    - 任务状态跟踪
    - 完成回调
    """

    # 信号
    task_submitted = Signal(str)           # 任务提交
    task_started = Signal(str)             # 任务开始
    task_completed = Signal(str, object)   # 任务完成 (task_id, result)
    task_failed = Signal(str, str)         # 任务失败 (task_id, error)
    task_cancelled = Signal(str)           # 任务取消
    task_queue_changed = Signal(int, int)  # 队列变化 (pending_count, running_count)
    all_idle = Signal()                    # 所有任务完成

    # 最大并行任务数
    MAX_PARALLEL_TASKS = 3

    def __init__(self):
        super().__init__()
        self._tasks: Dict[str, Task] = {}
        self._running: Dict[str, asyncio.Task] = {}
        self._queue: List[str] = []  # 任务ID列表，按优先级排序
        self._lock = asyncio.Lock()
        self._is_shutdown = False

        # 任务ID生成器
        self._id_counter = 0

    # ========== 公共API ==========

    def submit(
        self,
        name: str,
        coroutine: Coroutine,
        priority: TaskPriority = TaskPriority.TOOL_EXECUTION,
        callback: Optional[Callable[[Any], None]] = None,
    ) -> str:
        """提交新任务。

        Args:
            name: 任务名称
            coroutine: 异步协程
            priority: 任务优先级
            callback: 完成回调

        Returns:
            任务ID
        """
        if self._is_shutdown:
            logger.warning("调度器已关闭，无法提交新任务")
            return ""

        self._id_counter += 1
        task_id = f"task_{self._id_counter}"

        task = Task(
            id=task_id,
            name=name,
            priority=priority,
            coroutine=coroutine,
            callback=callback,
        )

        self._tasks[task_id] = task
        self._add_to_queue(task_id)

        logger.info(f"提交任务: {task_id} ({name}), 优先级: {priority.name}")

        self.task_submitted.emit(task_id)
        self.task_queue_changed.emit(len(self._queue), len(self._running))

        # 尝试启动任务
        asyncio.create_task(self._try_start_tasks())

        return task_id

    def submit_sync(
        self,
        name: str,
        func: Callable,
        args: tuple = (),
        priority: TaskPriority = TaskPriority.TOOL_EXECUTION,
        callback: Optional[Callable[[Any], None]] = None,
    ) -> str:
        """提交同步函数任务。

        Args:
            name: 任务名称
            func: 同步函数
            args: 函数参数
            priority: 任务优先级
            callback: 完成回调

        Returns:
            任务ID
        """
        async def wrapper():
            return func(*args)

        return self.submit(name, wrapper(), priority, callback)

    def cancel(self, task_id: str) -> bool:
        """取消任务。

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消
        """
        task = self._tasks.get(task_id)
        if not task:
            return False

        if task.status == TaskStatus.RUNNING:
            # 取消运行中的任务
            asyncio_task = self._running.get(task_id)
            if asyncio_task:
                asyncio_task.cancel()
                logger.info(f"取消任务: {task_id}")
                self.task_cancelled.emit(task_id)
                return True
            return False

        if task.status == TaskStatus.PENDING:
            # 从队列中移除
            if task_id in self._queue:
                self._queue.remove(task_id)
            task.status = TaskStatus.CANCELLED
            logger.info(f"取消任务: {task_id}")
            self.task_cancelled.emit(task_id)
            self.task_queue_changed.emit(len(self._queue), len(self._running))
            return True

        return False

    def cancel_all(self, priority: Optional[TaskPriority] = None) -> int:
        """取消所有任务。

        Args:
            priority: 如果指定，仅取消该优先级的任务

        Returns:
            取消的任务数
        """
        cancelled = 0

        if priority is None:
            # 取消所有
            for task_id in list(self._tasks.keys()):
                if self.cancel(task_id):
                    cancelled += 1
        else:
            # 取消指定优先级
            for task_id, task in self._tasks.items():
                if task.priority == priority and task.status == TaskStatus.PENDING:
                    if self.cancel(task_id):
                        cancelled += 1

        return cancelled

    def get_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态。"""
        task = self._tasks.get(task_id)
        return task.status if task else None

    def get_result(self, task_id: str) -> Any:
        """获取任务结果。"""
        task = self._tasks.get(task_id)
        return task.result if task else None

    def get_queue_info(self) -> dict:
        """获取队列信息。"""
        pending = sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING)
        running = sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING)
        completed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED)

        return {
            "pending": pending,
            "running": running,
            "completed": completed,
            "failed": failed,
            "total": len(self._tasks),
        }

    def shutdown(self) -> None:
        """关闭调度器。"""
        self._is_shutdown = True
        self.cancel_all()
        logger.info("任务调度器已关闭")

    # ========== 私有方法 ==========

    def _add_to_queue(self, task_id: str) -> None:
        """将任务添加到队列（按优先级排序）。"""
        task = self._tasks[task_id]
        if task_id in self._queue:
            return

        # 按优先级插入
        inserted = False
        for i, existing_id in enumerate(self._queue):
            existing_task = self._tasks[existing_id]
            if task.priority < existing_task.priority:
                self._queue.insert(i, task_id)
                inserted = True
                break

        if not inserted:
            self._queue.append(task_id)

    async def _try_start_tasks(self) -> None:
        """尝试启动队列中的任务。"""
        if self._is_shutdown:
            return

        # 检查是否可以启动新任务
        while len(self._running) < self.MAX_PARALLEL_TASKS and self._queue:
            task_id = self._queue.pop(0)
            task = self._tasks.get(task_id)

            if not task or task.status != TaskStatus.PENDING:
                continue

            # 启动任务
            task.status = TaskStatus.RUNNING
            asyncio_task = asyncio.create_task(self._run_task(task))
            self._running[task_id] = asyncio_task

            logger.info(f"启动任务: {task_id}")
            self.task_started.emit(task_id)
            self.task_queue_changed.emit(len(self._queue), len(self._running))

    async def _run_task(self, task: Task) -> None:
        """运行任务。"""
        try:
            if task.coroutine:
                result = await task.coroutine
            else:
                result = None

            task.status = TaskStatus.COMPLETED
            task.result = result

            logger.info(f"任务完成: {task.id}")

            # 执行回调
            if task.callback:
                try:
                    task.callback(result)
                except Exception as e:
                    logger.error(f"任务回调执行失败: {e}")

            self.task_completed.emit(task.id, result)

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            logger.info(f"任务取消: {task.id}")
            self.task_cancelled.emit(task.id)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = e
            logger.error(f"任务失败: {task.id}, 错误: {e}")
            self.task_failed.emit(task.id, str(e))

        finally:
            # 从运行中移除
            self._running.pop(task.id, None)
            self.task_queue_changed.emit(len(self._queue), len(self._running))

            # 检查是否所有任务完成
            if not self._running and not self._queue:
                self.all_idle.emit()

            # 尝试启动下一个任务
            await self._try_start_tasks()


# 全局调度器实例
_global_scheduler: Optional[TaskScheduler] = None


def get_scheduler() -> TaskScheduler:
    """获取全局任务调度器实例。"""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = TaskScheduler()
    return _global_scheduler
