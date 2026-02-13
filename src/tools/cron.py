"""Cron 定时任务工具 — 基于 APScheduler 的定时任务管理。

支持功能：
1. 创建定时任务（cron 表达式 / interval / date）
2. 列出所有任务
3. 取消任务
4. 任务持久化（SQLite 存储，应用重启后自动恢复）

Phase 4.6 优化：
- 延迟导入：APScheduler 仅在实际使用时导入
- 启动速度大幅提升
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus
from src.tools.cron_storage import (
    CronStorage, JobStatus, ScheduleStatus, StoredJob, StoredSchedule, TriggerType,
)

logger = logging.getLogger(__name__)

# 延迟导入标记
_APS_AVAILABLE: bool | None = None
_AsyncIOScheduler = None
_CronTrigger = None
_DateTrigger = None
_IntervalTrigger = None


def _check_apscheduler() -> bool:
    """检查 APScheduler 是否可用，延迟导入。"""
    global _APS_AVAILABLE, _AsyncIOScheduler, _CronTrigger, _DateTrigger, _IntervalTrigger
    if _APS_AVAILABLE is not None:
        return _APS_AVAILABLE

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.date import DateTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        _AsyncIOScheduler = AsyncIOScheduler
        _CronTrigger = CronTrigger
        _DateTrigger = DateTrigger
        _IntervalTrigger = IntervalTrigger
        _APS_AVAILABLE = True
        logger.debug("APScheduler 加载成功")
    except ImportError:
        _APS_AVAILABLE = False
        logger.debug("APScheduler 不可用")

    return _APS_AVAILABLE


class CronTool(BaseTool):
    """定时任务工具。
    
    基于 APScheduler 实现，支持：
    - cron 表达式（标准 cron 语法）
    - 间隔调度（秒/分/时）
    - 指定时间执行
    - 任务持久化（重启后自动恢复）
    """
    
    name = "cron"
    emoji = "⏰"
    title = "定时任务"
    description = "创建、管理和取消定时任务（支持持久化）"
    
    def __init__(self, db_path: Path | str | None = None):
        """初始化定时任务工具。
        
        Args:
            db_path: SQLite 数据库路径,为 None 时使用默认路径
        """
        super().__init__()
        self.scheduler: AsyncIOScheduler | None = None
        self._initialized = False
        self._storage = CronStorage(db_path)
        self._jobs_restored = False
    
    def _ensure_scheduler(self):
        """确保调度器已初始化并恢复持久化任务。"""
        if not _check_apscheduler():
            raise ImportError("APScheduler 不可用。请安装依赖: pip install apscheduler")

        if not self._initialized:
            self.scheduler = _AsyncIOScheduler()
            self.scheduler.start()
            self._initialized = True
            logger.info("APScheduler 已启动")

            # 恢复持久化任务
            if not self._jobs_restored:
                self._restore_jobs()
                self._jobs_restored = True

        return self.scheduler
    
    def _restore_jobs(self) -> None:
        """从存储中恢复任务。"""
        try:
            jobs = self._storage.get_all_jobs()
            restored_count = 0

            for stored_job in jobs:
                try:
                    # 根据触发器类型恢复任务
                    if stored_job.trigger_type == TriggerType.CRON:
                        trigger = _CronTrigger(**stored_job.trigger_config)
                    elif stored_job.trigger_type == TriggerType.INTERVAL:
                        trigger = _IntervalTrigger(**stored_job.trigger_config)
                    elif stored_job.trigger_type == TriggerType.DATE:
                        run_date = datetime.fromisoformat(stored_job.trigger_config["run_date"])
                        # 跳过已过期的一次性任务
                        if run_date < datetime.now():
                            logger.debug(f"跳过已过期任务: {stored_job.job_id}")
                            self._storage.delete_job(stored_job.job_id)
                            continue
                        trigger = _DateTrigger(run_date=run_date)
                    else:
                        logger.warning(f"未知触发器类型: {stored_job.trigger_type}")
                        continue

                    # 添加任务到调度器
                    job = self.scheduler.add_job(
                        func=self._execute_command,
                        trigger=trigger,
                        args=[stored_job.command, stored_job.job_id],
                        id=stored_job.job_id,
                        name=stored_job.description or stored_job.job_id,
                        replace_existing=True,
                    )

                    # 如果任务状态为暂停，则暂停任务
                    if stored_job.status == JobStatus.PAUSED:
                        self.scheduler.pause_job(stored_job.job_id)

                    restored_count += 1
                    logger.debug(f"已恢复任务: {stored_job.job_id}")

                except Exception as e:
                    logger.error(f"恢复任务失败 {stored_job.job_id}: {e}")

            if restored_count > 0:
                logger.info(f"已恢复 {restored_count} 个持久化任务")

        except Exception as e:
            logger.error(f"恢复持久化任务失败: {e}")
    
    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="add_cron",
                description="使用 cron 表达式创建定时任务",
                parameters={
                    "job_id": {
                        "type": "string",
                        "description": "任务唯一标识符",
                    },
                    "cron_expr": {
                        "type": "string",
                        "description": "Cron 表达式，如 '0 9 * * *' 表示每天 9:00",
                    },
                    "command": {
                        "type": "string",
                        "description": "要执行的命令或脚本路径",
                    },
                    "description": {
                        "type": "string",
                        "description": "任务描述（可选）",
                    },
                },
                required_params=["job_id", "cron_expr", "command"],
            ),
            ActionDef(
                name="add_interval",
                description="创建间隔执行的定时任务",
                parameters={
                    "job_id": {
                        "type": "string",
                        "description": "任务唯一标识符",
                    },
                    "interval_seconds": {
                        "type": "integer",
                        "description": "执行间隔（秒）",
                    },
                    "command": {
                        "type": "string",
                        "description": "要执行的命令或脚本路径",
                    },
                    "description": {
                        "type": "string",
                        "description": "任务描述（可选）",
                    },
                },
                required_params=["job_id", "interval_seconds", "command"],
            ),
            ActionDef(
                name="add_once",
                description="创建一次性定时任务（在指定时间执行一次）",
                parameters={
                    "job_id": {
                        "type": "string",
                        "description": "任务唯一标识符",
                    },
                    "run_date": {
                        "type": "string",
                        "description": "执行时间，格式如 '2024-12-31 18:00:00'",
                    },
                    "command": {
                        "type": "string",
                        "description": "要执行的命令或脚本路径",
                    },
                    "description": {
                        "type": "string",
                        "description": "任务描述（可选）",
                    },
                },
                required_params=["job_id", "run_date", "command"],
            ),
            ActionDef(
                name="list_jobs",
                description="列出所有定时任务",
                parameters={},
            ),
            ActionDef(
                name="remove_job",
                description="删除指定的定时任务",
                parameters={
                    "job_id": {
                        "type": "string",
                        "description": "任务标识符",
                    },
                },
                required_params=["job_id"],
            ),
            ActionDef(
                name="pause_job",
                description="暂停指定的定时任务",
                parameters={
                    "job_id": {
                        "type": "string",
                        "description": "任务标识符",
                    },
                },
                required_params=["job_id"],
            ),
            ActionDef(
                name="resume_job",
                description="恢复已暂停的定时任务",
                parameters={
                    "job_id": {
                        "type": "string",
                        "description": "任务标识符",
                    },
                },
                required_params=["job_id"],
            ),
            # ---- 日程管理动作 ----
            ActionDef(
                name="create_schedule",
                description="创建日程事项。可设置提醒时间，到期自动通知。",
                parameters={
                    "title": {
                        "type": "string",
                        "description": "日程标题",
                    },
                    "content": {
                        "type": "string",
                        "description": "日程详细内容（可选）",
                    },
                    "scheduled_time": {
                        "type": "string",
                        "description": "日程时间，格式如 '2024-12-31 18:00:00'（可选）",
                    },
                    "tags": {
                        "type": "string",
                        "description": "标签，多个用逗号分隔（可选）",
                    },
                },
                required_params=["title"],
            ),
            ActionDef(
                name="query_schedules",
                description="查询日程列表，支持按状态和关键词筛选",
                parameters={
                    "status": {
                        "type": "string",
                        "description": "筛选状态: all/pending/completed/upcoming/today，默认 all",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词（可选）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量，默认 20",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="update_schedule",
                description="更新日程信息",
                parameters={
                    "schedule_id": {
                        "type": "integer",
                        "description": "日程 ID",
                    },
                    "title": {
                        "type": "string",
                        "description": "新标题（可选）",
                    },
                    "content": {
                        "type": "string",
                        "description": "新内容（可选）",
                    },
                    "scheduled_time": {
                        "type": "string",
                        "description": "新时间（可选）",
                    },
                },
                required_params=["schedule_id"],
            ),
            ActionDef(
                name="delete_schedule",
                description="删除日程事项",
                parameters={
                    "schedule_id": {
                        "type": "integer",
                        "description": "日程 ID",
                    },
                },
                required_params=["schedule_id"],
            ),
            ActionDef(
                name="complete_schedule",
                description="标记日程为已完成",
                parameters={
                    "schedule_id": {
                        "type": "integer",
                        "description": "日程 ID",
                    },
                },
                required_params=["schedule_id"],
            ),
        ]
    
    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        """执行定时任务操作。"""
        try:
            if action == "add_cron":
                return await self._add_cron_job(params)
            elif action == "add_interval":
                return await self._add_interval_job(params)
            elif action == "add_once":
                return await self._add_once_job(params)
            elif action == "list_jobs":
                return await self._list_jobs()
            elif action == "remove_job":
                return await self._remove_job(params)
            elif action == "pause_job":
                return await self._pause_job(params)
            elif action == "resume_job":
                return await self._resume_job(params)
            # 日程管理
            elif action == "create_schedule":
                return await self._create_schedule(params)
            elif action == "query_schedules":
                return await self._query_schedules(params)
            elif action == "update_schedule":
                return await self._update_schedule(params)
            elif action == "delete_schedule":
                return await self._delete_schedule(params)
            elif action == "complete_schedule":
                return await self._complete_schedule(params)
            else:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"未知动作: {action}",
                )
        except Exception as e:
            logger.error(f"定时任务操作失败: {e}")
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=str(e),
            )
    
    # ----------------------------------------------------------------
    # 任务创建
    # ----------------------------------------------------------------
    
    async def _add_cron_job(self, params: dict[str, Any]) -> ToolResult:
        """添加 cron 定时任务。"""
        scheduler = self._ensure_scheduler()
        
        job_id = params["job_id"]
        cron_expr = params["cron_expr"]
        command = params["command"]
        description = params.get("description", "")
        
        # 解析 cron 表达式
        # 标准格式：minute hour day month day_of_week
        parts = cron_expr.split()
        if len(parts) != 5:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="Cron 表达式格式错误，应为：minute hour day month day_of_week",
            )
        
        minute, hour, day, month, day_of_week = parts
        
        # 创建触发器配置（用于持久化）
        trigger_config = {
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week,
        }
        
        # 创建触发器
        trigger = _CronTrigger(**trigger_config)
        
        # 添加任务
        job = scheduler.add_job(
            func=self._execute_command,
            trigger=trigger,
            args=[command, job_id],
            id=job_id,
            name=description or job_id,
            replace_existing=True,
        )
        
        # 持久化任务
        stored_job = StoredJob(
            job_id=job_id,
            trigger_type=TriggerType.CRON,
            trigger_config=trigger_config,
            command=command,
            description=description,
            created_at=datetime.now(),
            last_run=None,
            status=JobStatus.ACTIVE,
        )
        self._storage.save_job(stored_job)
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已创建 cron 任务: {job_id} ({cron_expr})",
            data={
                "job_id": job_id,
                "cron_expr": cron_expr,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "persisted": True,
            },
        )
    
    async def _add_interval_job(self, params: dict[str, Any]) -> ToolResult:
        """添加间隔执行任务。"""
        scheduler = self._ensure_scheduler()
        
        job_id = params["job_id"]
        interval_seconds = params["interval_seconds"]
        command = params["command"]
        description = params.get("description", "")
        
        # 创建触发器配置（用于持久化）
        trigger_config = {"seconds": interval_seconds}
        
        # 创建触发器
        trigger = _IntervalTrigger(**trigger_config)
        
        # 添加任务
        job = scheduler.add_job(
            func=self._execute_command,
            trigger=trigger,
            args=[command, job_id],
            id=job_id,
            name=description or job_id,
            replace_existing=True,
        )
        
        # 持久化任务
        stored_job = StoredJob(
            job_id=job_id,
            trigger_type=TriggerType.INTERVAL,
            trigger_config=trigger_config,
            command=command,
            description=description,
            created_at=datetime.now(),
            last_run=None,
            status=JobStatus.ACTIVE,
        )
        self._storage.save_job(stored_job)
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已创建间隔任务: {job_id} (每 {interval_seconds} 秒)",
            data={
                "job_id": job_id,
                "interval_seconds": interval_seconds,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "persisted": True,
            },
        )
    
    async def _add_once_job(self, params: dict[str, Any]) -> ToolResult:
        """添加一次性任务。"""
        scheduler = self._ensure_scheduler()
        
        job_id = params["job_id"]
        run_date_str = params["run_date"]
        command = params["command"]
        description = params.get("description", "")
        
        # 解析时间
        try:
            run_date = datetime.strptime(run_date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="时间格式错误，应为：YYYY-MM-DD HH:MM:SS",
            )
        
        # 创建触发器配置（用于持久化）
        trigger_config = {"run_date": run_date.isoformat()}
        
        # 创建触发器
        trigger = _DateTrigger(run_date=run_date)
        
        # 添加任务
        job = scheduler.add_job(
            func=self._execute_command,
            trigger=trigger,
            args=[command, job_id],
            id=job_id,
            name=description or job_id,
            replace_existing=True,
        )
        
        # 持久化任务
        stored_job = StoredJob(
            job_id=job_id,
            trigger_type=TriggerType.DATE,
            trigger_config=trigger_config,
            command=command,
            description=description,
            created_at=datetime.now(),
            last_run=None,
            status=JobStatus.ACTIVE,
        )
        self._storage.save_job(stored_job)
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已创建一次性任务: {job_id} (于 {run_date_str})",
            data={
                "job_id": job_id,
                "run_date": run_date_str,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "persisted": True,
            },
        )
    
    # ----------------------------------------------------------------
    # 任务管理
    # ----------------------------------------------------------------
    
    async def _list_jobs(self) -> ToolResult:
        """列出所有任务（包含持久化状态）。"""
        # 获取存储的任务
        stored_jobs = {j.job_id: j for j in self._storage.get_all_jobs()}
        
        # 获取运行中的任务
        running_jobs = {}
        if self._initialized and self.scheduler:
            for job in self.scheduler.get_jobs():
                running_jobs[job.id] = job
        
        job_list = []
        
        # 合并存储和运行中的任务信息
        all_job_ids = set(stored_jobs.keys()) | set(running_jobs.keys())
        
        for job_id in all_job_ids:
            stored = stored_jobs.get(job_id)
            running = running_jobs.get(job_id)
            
            job_info = {
                "id": job_id,
                "name": running.name if running else (stored.description if stored else job_id),
                "next_run": str(running.next_run_time) if running and running.next_run_time else None,
                "trigger": str(running.trigger) if running else (stored.trigger_type.value if stored else "unknown"),
                "status": stored.status.value if stored else "active",
                "persisted": stored is not None,
            }
            job_list.append(job_info)
        
        if not job_list:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="暂无定时任务",
                data={"jobs": []},
            )
        
        output_lines = [f"共 {len(job_list)} 个定时任务:"]
        for info in job_list:
            status_icon = "⏸" if info["status"] == "paused" else "▶"
            persist_icon = "💾" if info["persisted"] else ""
            output_lines.append(
                f"  {status_icon} {info['id']}: {info['name']} (下次: {info['next_run']}) {persist_icon}"
            )
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(output_lines),
            data={"jobs": job_list},
        )
    
    async def _remove_job(self, params: dict[str, Any]) -> ToolResult:
        """删除任务（同时从存储中删除）。"""
        job_id = params["job_id"]
        
        # 从调度器删除
        scheduler_deleted = False
        if self._initialized and self.scheduler:
            try:
                self.scheduler.remove_job(job_id)
                scheduler_deleted = True
            except Exception:
                pass  # 任务可能不在调度器中
        
        # 从存储删除
        storage_deleted = self._storage.delete_job(job_id)
        
        if scheduler_deleted or storage_deleted:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已删除任务: {job_id}",
                data={"scheduler_deleted": scheduler_deleted, "storage_deleted": storage_deleted},
            )
        else:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"任务不存在: {job_id}",
            )
    
    async def _pause_job(self, params: dict[str, Any]) -> ToolResult:
        """暂停任务（同时更新存储状态）。"""
        job_id = params["job_id"]
        
        # 暂停调度器中的任务
        if self._initialized and self.scheduler:
            try:
                self.scheduler.pause_job(job_id)
            except Exception as e:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"暂停任务失败: {e}",
                )
        
        # 更新存储状态
        self._storage.update_status(job_id, JobStatus.PAUSED)
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已暂停任务: {job_id}",
            data={"status": "paused"},
        )
    
    async def _resume_job(self, params: dict[str, Any]) -> ToolResult:
        """恢复任务（同时更新存储状态）。"""
        job_id = params["job_id"]
        
        # 恢复调度器中的任务
        if self._initialized and self.scheduler:
            try:
                self.scheduler.resume_job(job_id)
            except Exception as e:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"恢复任务失败: {e}",
                )
        
        # 更新存储状态
        self._storage.update_status(job_id, JobStatus.ACTIVE)
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已恢复任务: {job_id}",
            data={"status": "active"},
        )
    
    # ----------------------------------------------------------------
    # 日程管理
    # ----------------------------------------------------------------

    async def _create_schedule(self, params: dict[str, Any]) -> ToolResult:
        """创建日程事项。"""
        import json as _json

        title = params.get("title", "").strip()
        content = params.get("content", "").strip()
        scheduled_time_str = params.get("scheduled_time", "")
        tags_str = params.get("tags", "")

        if not title:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="日程标题不能为空",
            )

        scheduled_time = None
        if scheduled_time_str:
            try:
                scheduled_time = datetime.strptime(scheduled_time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    scheduled_time = datetime.strptime(scheduled_time_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    return ToolResult(
                        status=ToolResultStatus.ERROR,
                        error="时间格式错误，应为: YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD HH:MM",
                    )

        tags_list = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        schedule = StoredSchedule(
            id=None,
            title=title,
            content=content,
            scheduled_time=scheduled_time,
            status=ScheduleStatus.PENDING,
            tags=_json.dumps(tags_list, ensure_ascii=False),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        schedule_id = self._storage.save_schedule(schedule)

        output = f"已创建日程: {title} (ID: {schedule_id})"
        if scheduled_time:
            output += f"\n提醒时间: {scheduled_time_str}"

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={
                "schedule_id": schedule_id,
                "title": title,
                "scheduled_time": scheduled_time_str or None,
                "tags": tags_list,
            },
        )

    async def _query_schedules(self, params: dict[str, Any]) -> ToolResult:
        """查询日程列表。"""
        status = params.get("status", "all")
        keyword = params.get("keyword", "")
        limit = min(params.get("limit", 20), 50)

        schedules = self._storage.query_schedules(
            status=status, keyword=keyword, limit=limit,
        )

        if not schedules:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="暂无日程安排。",
                data={"schedules": [], "count": 0},
            )

        status_icons = {
            "pending": "📌",
            "completed": "✅",
            "cancelled": "❌",
        }

        lines = [f"共 {len(schedules)} 条日程："]
        data_list = []
        for i, s in enumerate(schedules, 1):
            icon = status_icons.get(s.status.value, "📌")
            time_str = s.scheduled_time.strftime("%Y-%m-%d %H:%M") if s.scheduled_time else "无时间"
            lines.append(f"  {i}. {icon} {s.title} (ID:{s.id})")
            lines.append(f"      时间: {time_str} | 状态: {s.status.value}")
            if s.content:
                preview = s.content[:60] + ("..." if len(s.content) > 60 else "")
                lines.append(f"      内容: {preview}")
            data_list.append(s.to_dict())

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={"schedules": data_list, "count": len(data_list)},
        )

    async def _update_schedule(self, params: dict[str, Any]) -> ToolResult:
        """更新日程信息。"""
        schedule_id = params.get("schedule_id")
        if schedule_id is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="缺少 schedule_id",
            )

        fields = {}
        if "title" in params:
            fields["title"] = params["title"]
        if "content" in params:
            fields["content"] = params["content"]
        if "scheduled_time" in params:
            time_str = params["scheduled_time"]
            try:
                fields["scheduled_time"] = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    fields["scheduled_time"] = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    return ToolResult(
                        status=ToolResultStatus.ERROR,
                        error="时间格式错误",
                    )

        if not fields:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="没有可更新的字段",
            )

        ok = self._storage.update_schedule(schedule_id, **fields)
        if ok:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已更新日程 ID:{schedule_id}",
                data={"schedule_id": schedule_id, "updated_fields": list(fields.keys())},
            )
        return ToolResult(
            status=ToolResultStatus.ERROR,
            error=f"日程不存在: ID {schedule_id}",
        )

    async def _delete_schedule(self, params: dict[str, Any]) -> ToolResult:
        """删除日程事项。"""
        schedule_id = params.get("schedule_id")
        if schedule_id is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="缺少 schedule_id",
            )

        # 先获取日程信息用于返回
        schedule = self._storage.get_schedule(schedule_id)
        ok = self._storage.delete_schedule(schedule_id)
        if ok:
            title = schedule.title if schedule else f"ID:{schedule_id}"
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已删除日程: {title}",
                data={"schedule_id": schedule_id, "deleted": True},
            )
        return ToolResult(
            status=ToolResultStatus.ERROR,
            error=f"日程不存在: ID {schedule_id}",
        )

    async def _complete_schedule(self, params: dict[str, Any]) -> ToolResult:
        """标记日程为已完成。"""
        schedule_id = params.get("schedule_id")
        if schedule_id is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="缺少 schedule_id",
            )

        ok = self._storage.complete_schedule(schedule_id)
        if ok:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已完成日程 ID:{schedule_id}",
                data={"schedule_id": schedule_id, "status": "completed"},
            )
        return ToolResult(
            status=ToolResultStatus.ERROR,
            error=f"日程不存在: ID {schedule_id}",
        )

    # ----------------------------------------------------------------
    # 命令执行
    # ----------------------------------------------------------------
    
    async def _execute_command(self, command: str, job_id: str | None = None) -> None:
        """执行定时任务命令。
        
        Args:
            command: 要执行的命令
            job_id: 任务 ID（用于更新最后执行时间）
        """
        import subprocess
        
        logger.info(f"执行定时任务命令: {command}")
        
        try:
            # 使用 PowerShell 执行命令
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if result.returncode == 0:
                logger.info(f"定时任务执行成功: {result.stdout}")
            else:
                logger.error(f"定时任务执行失败: {result.stderr}")
            
            # 更新最后执行时间
            if job_id:
                self._storage.update_last_run(job_id)
        
        except Exception as e:
            logger.error(f"定时任务执行异常: {e}")
    
    def shutdown(self) -> None:
        """关闭调度器。"""
        if self._initialized and self.scheduler:
            self.scheduler.shutdown()
            logger.info("APScheduler 已关闭")
    
    @property
    def storage(self) -> CronStorage:
        """获取存储实例。"""
        return self._storage
