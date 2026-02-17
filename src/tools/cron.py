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
    CronStorage, JobStatus, JobType, ScheduleStatus, StoredJob, StoredSchedule, TriggerType,
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
    
    def __init__(self, db_path: Path | str | None = None, 
                 model_registry=None, tool_registry=None, event_bus=None):
        """初始化定时任务工具。
        
        Args:
            db_path: SQLite 数据库路径,为 None 时使用默认路径
            model_registry: 模型注册表（用于执行 AI 任务）
            tool_registry: 工具注册表（用于执行 AI 任务）
            event_bus: 事件总线（用于发布任务执行状态）
        """
        super().__init__()
        self.scheduler: AsyncIOScheduler | None = None
        self._initialized = False
        self._storage = CronStorage(db_path)
        self._jobs_restored = False
        self._model_registry = model_registry
        self._tool_registry = tool_registry
        self._event_bus = event_bus
    
    def set_agent_dependencies(self, model_registry, tool_registry, event_bus=None) -> None:
        """设置 Agent 依赖（用于执行 AI 任务）。
        
        Args:
            model_registry: 模型注册表
            tool_registry: 工具注册表
            event_bus: 事件总线（用于发布任务执行状态）
        """
        self._model_registry = model_registry
        self._tool_registry = tool_registry
        if event_bus:
            self._event_bus = event_bus
        logger.info("CronTool 已设置 Agent 依赖")
    
    def _get_default_max_steps(self) -> int:
        """从配置文件读取默认的最大执行步数。
        
        Returns:
            默认最大步数，如果配置文件不存在或未配置则返回 60
        """
        try:
            from pathlib import Path
            import tomllib
            
            # 尝试读取配置文件
            config_paths = [
                Path(__file__).parent.parent.parent / "config" / "default.toml",
                Path.home() / ".winclaw" / "default.toml",
            ]
            
            for config_path in config_paths:
                if config_path.exists():
                    with open(config_path, "rb") as f:
                        config = tomllib.load(f)
                        if "agent" in config and "max_steps" in config["agent"]:
                            return config["agent"]["max_steps"]
        except Exception as e:
            logger.debug(f"读取默认步数配置失败: {e}")
        
        # 默认返回 60（与 Agent 默认值一致）
        return 60
    
    async def _emit_cron_event(self, job_id: str, job_type: str, description: str,
                                status: str, result: str = "", error: str = "",
                                duration_ms: float = 0.0) -> None:
        """发布定时任务事件。
        
        Args:
            job_id: 任务ID
            job_type: 任务类型
            description: 任务描述
            status: 状态 (started/finished/error)
            result: 执行结果
            error: 错误信息
            duration_ms: 执行时长（毫秒）
        """
        if self._event_bus:
            try:
                from src.core.events import CronJobEvent, EventType
                event = CronJobEvent(
                    job_id=job_id,
                    job_type=job_type,
                    description=description,
                    status=status,
                    result=result,
                    error=error,
                    duration_ms=duration_ms,
                )
                event_type = {
                    "started": EventType.CRON_JOB_STARTED,
                    "finished": EventType.CRON_JOB_FINISHED,
                    "error": EventType.CRON_JOB_ERROR,
                }.get(status, EventType.CRON_JOB_STARTED)
                await self._event_bus.emit(event_type, event)
                logger.debug(f"已发布定时任务事件: {job_id} - {status}")
            except Exception as e:
                logger.warning(f"发布定时任务事件失败: {e}")
    
    def _emit_cron_event_sync(self, job_id: str, job_type: str, description: str,
                                status: str, result: str = "", error: str = "",
                                duration_ms: float = 0.0) -> None:
        """同步方式发布定时任务事件（用于命令任务）。"""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._emit_cron_event(
                job_id, job_type, description, status, result, error, duration_ms
            ))
        except RuntimeError:
            # 没有事件循环，尝试创建一个
            asyncio.run(self._emit_cron_event(
                job_id, job_type, description, status, result, error, duration_ms
            ))
    
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
    
    # 已知的 Linux 命令列表，用于检测无效的命令任务
    _LINUX_ONLY_COMMANDS = frozenset([
        'notify_send', 'notify-send', 'zenity', 'xmessage', 'kdialog',
        'xdg-open', 'gnome-terminal', 'xterm', 'crontab',
    ])
    
    def _is_invalid_command(self, command: str) -> str | None:
        """检测命令是否包含 Windows 上不可用的 Linux 命令。
        
        Returns:
            如果无效返回错误描述，否则返回 None
        """
        cmd_lower = command.lower().strip()
        for linux_cmd in self._LINUX_ONLY_COMMANDS:
            if cmd_lower.startswith(linux_cmd) or f' {linux_cmd}' in cmd_lower:
                return f"命令 '{linux_cmd}' 是 Linux 命令，在 Windows 上不可用"
        return None
    
    def _restore_jobs(self) -> None:
        """从存储中恢复任务。"""
        try:
            jobs = self._storage.get_all_jobs()
            restored_count = 0
            skipped_count = 0

            for stored_job in jobs:
                try:
                    # 检测命令任务是否包含无效的 Linux 命令
                    if stored_job.job_type != JobType.AI_TASK and stored_job.command:
                        invalid_reason = self._is_invalid_command(stored_job.command)
                        if invalid_reason:
                            logger.warning(
                                f"跳过无效命令任务 {stored_job.job_id}: {invalid_reason}。"
                                f"已自动删除，建议使用 add_ai_task 重新创建。"
                            )
                            self._storage.update_last_result(
                                stored_job.job_id, 
                                f"已自动移除: {invalid_reason}。请使用 add_ai_task 重新创建通知类任务。"
                            )
                            self._storage.delete_job(stored_job.job_id)
                            skipped_count += 1
                            continue
                    
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

                    # 根据任务类型选择执行函数
                    if stored_job.job_type == JobType.AI_TASK:
                        # AI 任务
                        func = self._execute_ai_task
                        args = [
                            stored_job.task_instruction,
                            stored_job.job_id,
                            stored_job.max_steps,
                            stored_job.result_action,
                            stored_job.result_file,
                        ]
                    else:
                        # 命令任务
                        func = self._execute_command
                        args = [stored_job.command, stored_job.job_id]

                    # 添加任务到调度器
                    job = self.scheduler.add_job(
                        func=func,
                        trigger=trigger,
                        args=args,
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
            if skipped_count > 0:
                logger.info(f"已跳过并删除 {skipped_count} 个无效命令任务")

        except Exception as e:
            logger.error(f"恢复持久化任务失败: {e}")
    
    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="add_cron",
                description=(
                    "使用 cron 表达式创建定时Shell命令任务（仅适合运行 PowerShell/CMD 命令）。"
                    "如果需要定时发送通知、提醒、执行AI指令等，请使用 add_ai_task。"
                ),
                parameters={
                    "job_id": {
                        "type": "string",
                        "description": "任务唯一标识符，如 'daily_backup'",
                    },
                    "cron_expr": {
                        "type": "string",
                        "description": "Cron 表达式（5段: 分 时 日 月 周），如 '0 9 * * *' 表示每天9:00",
                    },
                    "command": {
                        "type": "string",
                        "description": "要执行的 PowerShell 命令（注意：这是 Windows 系统，不支持 Linux 命令如 notify-send）",
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
                description=(
                    "创建间隔执行的Shell命令任务（仅适合运行 PowerShell/CMD 命令）。"
                    "如果需要定时发送通知、提醒、执行AI指令等，请使用 add_ai_task。"
                ),
                parameters={
                    "job_id": {
                        "type": "string",
                        "description": "任务唯一标识符，如 'check_disk'",
                    },
                    "interval_seconds": {
                        "type": "integer",
                        "description": "执行间隔（秒）",
                    },
                    "command": {
                        "type": "string",
                        "description": "要执行的 PowerShell 命令",
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
                description=(
                    "创建一次性Shell命令任务（在指定时间执行一次 PowerShell 命令）。"
                    "如果需要定时发送通知、提醒、执行AI指令等，请使用 add_ai_task。"
                ),
                parameters={
                    "job_id": {
                        "type": "string",
                        "description": "任务唯一标识符，如 'run_once_report'",
                    },
                    "run_date": {
                        "type": "string",
                        "description": "执行时间，格式如 '2026-12-31 18:00:00'",
                    },
                    "command": {
                        "type": "string",
                        "description": "要执行的 PowerShell 命令",
                    },
                    "description": {
                        "type": "string",
                        "description": "任务描述（可选）",
                    },
                },
                required_params=["job_id", "run_date", "command"],
            ),
            # ---- AI 任务动作 ----
            ActionDef(
                name="add_ai_task",
                description=(
                    "【推荐】创建定时AI任务。到时间后AI自动执行指令，如：发送通知/提醒、搜索信息、发送邮件、生成报告等。"
                    "支持三种触发方式：cron(定时)、interval(间隔)、once(一次性)。"
                    "所有需要通知/提醒的定时任务都应使用此动作，而非 add_cron。"
                ),
                parameters={
                    "job_id": {
                        "type": "string",
                        "description": "任务唯一标识符，如 'water_reminder' 或 'daily_news'",
                    },
                    "trigger_type": {
                        "type": "string",
                        "description": "触发类型: cron(定时)/interval(间隔)/once(一次性)",
                    },
                    "cron_expr": {
                        "type": "string",
                        "description": "Cron表达式（trigger_type为cron时必填），如 '0 9 * * *' 表示每天9点，'0/30 9-18 * * 1-5' 表示工作日9-18点每30分钟",
                    },
                    "interval_seconds": {
                        "type": "integer",
                        "description": "间隔秒数（trigger_type为interval时必填），如 1800 表示每30分钟",
                    },
                    "run_date": {
                        "type": "string",
                        "description": "一次性执行时间（trigger_type为once时必填），格式如 '2026-02-16 10:00:00'",
                    },
                    "task_instruction": {
                        "type": "string",
                        "description": "AI执行指令，如 '发送系统通知提醒用户喝水' 或 '搜索本周AI新闻生成摘要保存到 D:/weekly_news.md'",
                    },
                    "max_steps": {
                        "type": "integer",
                        "description": "AI任务最大执行步数，默认60，简单提醒任务可设为5-10",
                    },
                    "result_action": {
                        "type": "string",
                        "description": "结果处理方式: notify（发送通知）/ append_file（追加到文件）/ ignore（忽略），默认 notify",
                    },
                    "result_file": {
                        "type": "string",
                        "description": "结果保存文件路径（当result_action为append_file时使用）",
                    },
                    "description": {
                        "type": "string",
                        "description": "任务描述（可选）",
                    },
                },
                required_params=["job_id", "trigger_type", "task_instruction"],
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
            elif action == "add_ai_task":
                return await self._add_ai_task(params)
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
        # 参数验证
        job_id = params.get("job_id")
        cron_expr = params.get("cron_expr")
        command = params.get("command")
        if not job_id:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 job_id（任务唯一标识符）")
        if not cron_expr:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 cron_expr（Cron 表达式）")
        if not command:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 command（要执行的命令）。注意：如果需要发送通知/提醒，请改用 add_ai_task 动作")
        
        scheduler = self._ensure_scheduler()
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
        # 参数验证
        job_id = params.get("job_id")
        interval_seconds = params.get("interval_seconds")
        command = params.get("command")
        if not job_id:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 job_id（任务唯一标识符）")
        if not interval_seconds:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 interval_seconds（间隔秒数）")
        if not command:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 command（要执行的命令）。注意：如果需要发送通知/提醒，请改用 add_ai_task 动作")
        
        scheduler = self._ensure_scheduler()
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
        # 参数验证
        job_id = params.get("job_id")
        run_date_str = params.get("run_date")
        command = params.get("command")
        if not job_id:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 job_id（任务唯一标识符）")
        if not run_date_str:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 run_date（执行时间，格式 'YYYY-MM-DD HH:MM:SS'）")
        if not command:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 command（要执行的命令）。注意：如果需要发送通知/提醒，请改用 add_ai_task 动作")
        
        scheduler = self._ensure_scheduler()
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
    
    async def _add_ai_task(self, params: dict[str, Any]) -> ToolResult:
        """添加 AI 任务。
        
        支持三种触发类型：
        - cron: Cron 表达式触发
        - interval: 间隔触发
        - once: 一次性触发
        """
        # 参数验证
        job_id = params.get("job_id")
        task_instruction = params.get("task_instruction")
        if not job_id:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 job_id（任务唯一标识符，如 'water_reminder'）")
        if not task_instruction:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 task_instruction（AI执行指令，如 '发送系统通知提醒用户喝水'）")
        
        scheduler = self._ensure_scheduler()
        trigger_type = params.get("trigger_type", "once")
        # 从配置文件读取默认步数，如果未配置则使用 60
        default_max_steps = self._get_default_max_steps()
        max_steps = params.get("max_steps", default_max_steps)
        result_action = params.get("result_action", "notify")
        result_file = params.get("result_file", "")
        description = params.get("description", "")
        
        # 解析触发器配置
        trigger = None
        trigger_config = {}
        
        if trigger_type == "cron":
            cron_expr = params.get("cron_expr", "")
            if not cron_expr:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error="cron 触发类型需要提供 cron_expr 参数",
                )
            parts = cron_expr.split()
            if len(parts) != 5:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error="Cron 表达式格式错误，应为：minute hour day month day_of_week",
                )
            trigger_config = {
                "minute": parts[0],
                "hour": parts[1],
                "day": parts[2],
                "month": parts[3],
                "day_of_week": parts[4],
            }
            trigger = _CronTrigger(**trigger_config)
            
        elif trigger_type == "interval":
            interval_seconds = params.get("interval_seconds")
            if not interval_seconds:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error="interval 触发类型需要提供 interval_seconds 参数",
                )
            trigger_config = {"seconds": interval_seconds}
            trigger = _IntervalTrigger(**trigger_config)
            
        elif trigger_type == "once":
            run_date_str = params.get("run_date", "")
            if not run_date_str:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error="once 触发类型需要提供 run_date 参数",
                )
            try:
                run_date = datetime.strptime(run_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error="时间格式错误，应为：YYYY-MM-DD HH:MM:SS",
                )
            trigger_config = {"run_date": run_date.isoformat()}
            trigger = _DateTrigger(run_date=run_date)
            
        else:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"未知的触发类型: {trigger_type}",
            )
        
        # 添加任务到调度器
        job = scheduler.add_job(
            func=self._execute_ai_task,
            trigger=trigger,
            args=[task_instruction, job_id, max_steps, result_action, result_file],
            id=job_id,
            name=description or job_id,
            replace_existing=True,
        )
        
        # 持久化任务
        stored_job = StoredJob(
            job_id=job_id,
            trigger_type=TriggerType.CRON if trigger_type == "cron" else (TriggerType.INTERVAL if trigger_type == "interval" else TriggerType.DATE),
            trigger_config=trigger_config,
            command="",  # AI 任务不使用 command 字段
            description=description,
            created_at=datetime.now(),
            last_run=None,
            status=JobStatus.ACTIVE,
            job_type=JobType.AI_TASK,
            task_instruction=task_instruction,
            max_steps=max_steps,
            result_action=result_action,
            result_file=result_file,
        )
        self._storage.save_job(stored_job)
        
        trigger_desc = {
            "cron": f"cron表达式 {params.get('cron_expr', '')}",
            "interval": f"每 {params.get('interval_seconds', 0)} 秒",
            "once": f"于 {params.get('run_date', '')}",
        }.get(trigger_type, "")
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已创建定时AI任务: {job_id} ({trigger_desc})",
            data={
                "job_id": job_id,
                "trigger_type": trigger_type,
                "task_instruction": task_instruction[:100] + "..." if len(task_instruction) > 100 else task_instruction,
                "max_steps": max_steps,
                "result_action": result_action,
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
            
            job_type = stored.job_type.value if stored and stored.job_type else "command"
            job_type_icon = "🤖" if job_type == "ai_task" else "💻"
            last_result = stored.last_result if stored and stored.last_result else ""
            last_run = stored.last_run.strftime("%Y-%m-%d %H:%M") if stored and stored.last_run else "从未执行"
            
            job_info = {
                "id": job_id,
                "name": running.name if running else (stored.description if stored else job_id),
                "next_run": str(running.next_run_time) if running and running.next_run_time else None,
                "trigger": str(running.trigger) if running else (stored.trigger_type.value if stored else "unknown"),
                "status": stored.status.value if stored else "active",
                "persisted": stored is not None,
                "job_type": job_type,
                "last_run": last_run,
                "last_result": last_result,
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
            job_type_icon = "🤖" if info["job_type"] == "ai_task" else "💻"
            
            # 显示基本信息
            line = f"  {status_icon} {job_type_icon} {info['id']}: {info['name']}"
            if info["next_run"]:
                line += f" (下次: {info['next_run']})"
            line += f" {persist_icon}"
            output_lines.append(line)
            
            # 显示执行时间和结果
            if info["last_run"]:
                result_preview = info["last_result"][:100] + "..." if len(info["last_result"]) > 100 else info["last_result"]
                output_lines.append(f"      上次: {info['last_run']} | 结果: {result_preview}")
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(output_lines),
            data={"jobs": job_list},
        )
    
    async def _remove_job(self, params: dict[str, Any]) -> ToolResult:
        """删除任务（同时从存储中删除）。"""
        job_id = params.get("job_id")
        if not job_id:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 job_id")
        
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
        job_id = params.get("job_id")
        if not job_id:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 job_id")
        
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
        job_id = params.get("job_id")
        if not job_id:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少必填参数 job_id")
        
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
        import time
        
        logger.info(f"执行定时任务命令: {command}")
        
        # 预检查：命令是否包含 Windows 不支持的 Linux 命令
        invalid_reason = self._is_invalid_command(command)
        if invalid_reason:
            error_msg = f"{invalid_reason}。此任务已自动移除，请使用 add_ai_task 重新创建通知类任务。"
            logger.error(f"定时任务命令无效: {error_msg}")
            if job_id:
                self._storage.update_last_result(job_id, f"错误: {error_msg}")
                # 自动从调度器和存储中删除无效任务
                if self._initialized and self.scheduler:
                    try:
                        self.scheduler.remove_job(job_id)
                    except Exception:
                        pass
                self._storage.delete_job(job_id)
            return
        
        # 获取任务信息
        job_info = self._storage.get_job(job_id) if job_id else None
        job_type = job_info.job_type.value if job_info else "command"
        description = job_info.description if job_info else command[:50]
        
        # 发布开始事件
        start_time = time.time()
        self._emit_cron_event_sync(job_id or "unknown", job_type, description, "started")
        
        try:
            # 使用 PowerShell 执行命令
            # 设置 UTF-8 编码环境，避免中文乱码问题
            import os
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=300,
                env=env,
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            if result.returncode == 0:
                logger.info(f"定时任务执行成功: {result.stdout}")
                result_text = f"成功: {result.stdout}"
                # 发布完成事件
                self._emit_cron_event_sync(job_id or "unknown", job_type, description, 
                                           "finished", result=result_text[:500], duration_ms=duration_ms)
            else:
                error_msg = result.stderr
                
                # 检测常见的 Linux 命令在 Windows 上不可用的情况
                linux_commands = ['notify_send', 'notify-send', 'zenity', 'xmessage', 'kdialog']
                for cmd in linux_commands:
                    if cmd in command.lower() or cmd.replace('_', '-') in command.lower():
                        error_msg += (
                            f"\n\n提示: '{cmd}' 是 Linux 命令，在 Windows 上不可用。"
                            f"\n建议使用 AI 任务类型的定时任务，并将结果处理设置为 '发送通知'。"
                        )
                        break
                
                logger.error(f"定时任务执行失败: {error_msg}")
                result_text = f"失败: {error_msg}"
                # 发布错误事件
                self._emit_cron_event_sync(job_id or "unknown", job_type, description, 
                                           "error", error=result_text[:500], duration_ms=duration_ms)
            
            # 更新最后执行时间和结果
            if job_id:
                self._storage.update_last_run(job_id)
                self._storage.update_last_result(job_id, result_text[:5000])
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"定时任务执行异常: {e}")
            if job_id:
                self._storage.update_last_result(job_id, f"异常: {str(e)[:500]}")
            # 发布错误事件
            self._emit_cron_event_sync(job_id or "unknown", job_type, description, 
                                       "error", error=str(e)[:500], duration_ms=duration_ms)
    
    async def _execute_ai_task(
        self, 
        task_instruction: str, 
        job_id: str | None = None,
        max_steps: int = 10,
        result_action: str = "notify",
        result_file: str = "",
    ) -> None:
        """执行 AI 任务。
        
        Args:
            task_instruction: 要执行的 AI 指令
            job_id: 任务 ID（用于更新最后执行时间）
            max_steps: 最大执行步数
            result_action: 结果处理方式
            result_file: 结果保存文件路径
        """
        import time
        
        logger.info(f"执行定时 AI 任务: {task_instruction[:100]}...")
        
        # 获取任务信息
        job_info = self._storage.get_job(job_id) if job_id else None
        description = job_info.description if job_info else task_instruction[:50]
        
        # 发布开始事件
        start_time = time.time()
        await self._emit_cron_event(job_id or "unknown", "ai_task", description, "started")
        
        # 检查是否有所需的依赖
        if self._model_registry is None or self._tool_registry is None:
            logger.error("AI 任务执行失败：未配置模型注册表或工具注册表")
            self._storage.update_last_result(job_id, "错误：未配置模型注册表或工具注册表")
            await self._emit_cron_event(job_id or "unknown", "ai_task", description, 
                                        "error", error="未配置模型注册表或工具注册表")
            return
        
        try:
            # 延迟导入 Agent
            from src.core.agent import Agent
            
            # 选择默认模型
            model_key = "deepseek-chat"
            if self._model_registry.get(model_key) is None:
                # 尝试获取第一个可用的模型
                models = self._model_registry.list_models()
                if models:
                    model_key = models[0].key
                else:
                    logger.error("AI 任务执行失败：没有可用的模型")
                    self._storage.update_last_result(job_id, "错误：没有可用的模型")
                    await self._emit_cron_event(job_id or "unknown", "ai_task", description, 
                                                "error", error="没有可用的模型")
                    return
            
            # 创建 Agent 实例
            agent = Agent(
                model_registry=self._model_registry,
                tool_registry=self._tool_registry,
                model_key=model_key,
                max_steps=max_steps,
            )
            
            # 执行任务 - 直接 await，因为当前方法本身就是 async
            # APScheduler 的 AsyncIOScheduler 会正确处理 async 函数
            response = await agent.chat(task_instruction)
            
            duration_ms = (time.time() - start_time) * 1000
            
            result_text = response.content if response.content else "任务执行完成"
            logger.info(f"AI 任务执行完成: {result_text[:200]}...")
            
            # 保存执行结果到数据库
            if job_id:
                self._storage.update_last_run(job_id)
                self._storage.update_last_result(job_id, result_text[:5000])  # 限制结果长度
            
            # 发布完成事件
            await self._emit_cron_event(job_id or "unknown", "ai_task", description, 
                                         "finished", result=result_text[:500], duration_ms=duration_ms)
            
            # 处理结果
            await self._handle_ai_task_result(
                result_text=result_text,
                result_action=result_action,
                result_file=result_file,
                job_id=job_id,
            )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = f"AI 任务执行异常: {str(e)}"
            logger.error(error_msg)
            if job_id:
                self._storage.update_last_result(job_id, f"错误: {str(e)[:500]}")
            
            # 发布错误事件
            await self._emit_cron_event(job_id or "unknown", "ai_task", description, 
                                         "error", error=str(e)[:500], duration_ms=duration_ms)
            
            # 发送错误通知
            if result_action == "notify":
                try:
                    from src.tools.notify import NotifyTool
                    notify = NotifyTool()
                    await notify.execute("send", {
                        "title": "定时AI任务执行失败",
                        "message": f"任务指令: {task_instruction[:50]}...\n错误: {str(e)}",
                    })
                except Exception:
                    pass
    
    async def _handle_ai_task_result(
        self,
        result_text: str,
        result_action: str,
        result_file: str,
        job_id: str | None,
    ) -> None:
        """处理 AI 任务执行结果。
        
        Args:
            result_text: 执行结果文本
            result_action: 处理方式
            result_file: 保存文件路径
            job_id: 任务 ID
        """
        from datetime import datetime
        
        if result_action == "notify":
            # 发送系统通知
            try:
                from src.tools.notify import NotifyTool
                notify = NotifyTool()
                # 截断过长的消息
                message = result_text[:500] + "..." if len(result_text) > 500 else result_text
                await notify.execute("send", {
                    "title": "定时AI任务已完成",
                    "message": message,
                })
                logger.info("已发送任务完成通知")
            except Exception as e:
                logger.error(f"发送通知失败: {e}")
                
        elif result_action == "append_file" and result_file:
            # 追加到文件
            try:
                from src.tools.file import FileTool
                file_tool = FileTool()
                
                # 直接追加新内容（使用 append 模式）
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_content = f"\n\n--- {timestamp} ---\n{result_text}\n"
                
                # 使用 execute 方法追加写入
                write_result = await file_tool.execute("write", {
                    "path": result_file,
                    "content": new_content,
                    "append": True,
                })
                
                if write_result.status == ToolResultStatus.SUCCESS:
                    logger.info(f"结果已追加到文件: {result_file}")
                else:
                    logger.error(f"追加文件失败: {write_result.error}")
            except Exception as e:
                logger.error(f"追加文件失败: {e}")
        
        # ignore 模式下只记录日志，不做任何处理
    
    def shutdown(self) -> None:
        """关闭调度器。"""
        if self._initialized and self.scheduler:
            self.scheduler.shutdown()
            logger.info("APScheduler 已关闭")
    
    @property
    def storage(self) -> CronStorage:
        """获取存储实例。"""
        return self._storage
