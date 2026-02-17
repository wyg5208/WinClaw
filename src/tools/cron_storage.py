"""Cron 定时任务持久化存储 — 基于 SQLite 的任务存储。

功能:
1. 任务持久化存储
2. 应用重启后自动恢复任务
3. 任务状态跟踪（活动/暂停）
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)


class TriggerType(str, Enum):
    """触发器类型。"""
    CRON = "cron"
    INTERVAL = "interval"
    DATE = "date"


class JobType(str, Enum):
    """任务类型。"""
    COMMAND = "command"  # 外部命令任务
    AI_TASK = "ai_task"  # AI 任务


class JobStatus(str, Enum):
    """任务状态。"""
    ACTIVE = "active"
    PAUSED = "paused"


class ScheduleStatus(str, Enum):
    """日程状态。"""
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class StoredJob:
    """存储的任务数据。"""
    job_id: str
    trigger_type: TriggerType
    trigger_config: dict[str, Any]
    command: str
    description: str
    created_at: datetime
    last_run: datetime | None
    status: JobStatus
    # 新增字段：支持 AI 任务
    job_type: JobType = JobType.COMMAND  # 任务类型：command/ai_task
    task_instruction: str = ""  # AI 任务指令
    max_steps: int = 10  # AI 任务最大执行步数
    result_action: str = "notify"  # 结果处理：notify/append_file/ignore
    result_file: str = ""  # 结果保存文件路径
    last_result: str = ""  # 上次执行结果
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "job_id": self.job_id,
            "trigger_type": self.trigger_type.value,
            "trigger_config": self.trigger_config,
            "command": self.command,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_result": self.last_result,
            "status": self.status.value,
            "job_type": self.job_type.value,
            "task_instruction": self.task_instruction,
            "max_steps": self.max_steps,
            "result_action": self.result_action,
            "result_file": self.result_file,
        }
    
    @classmethod
    def from_row(cls, row: tuple) -> StoredJob:
        """从数据库行创建对象。"""
        # 兼容旧数据结构：只有8个字段时使用默认值
        if len(row) == 8:
            job_id, trigger_type, trigger_config, command, description, created_at, last_run, status = row
            return cls(
                job_id=job_id,
                trigger_type=TriggerType(trigger_type),
                trigger_config=json.loads(trigger_config) if trigger_config else {},
                command=command,
                description=description or "",
                created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(),
                last_run=datetime.fromisoformat(last_run) if last_run else None,
                status=JobStatus(status) if status else JobStatus.ACTIVE,
            )
        # 13个字段（旧格式，无last_result）
        # 顺序: job_id, trigger_type, trigger_config, command, description, created_at, last_run, status, job_type, task_instruction, max_steps, result_action, result_file
        if len(row) == 13:
            (job_id, trigger_type, trigger_config, command, description, created_at, last_run, status,
             job_type, task_instruction, max_steps, result_action, result_file) = row
            return cls(
                job_id=job_id,
                trigger_type=TriggerType(trigger_type),
                trigger_config=json.loads(trigger_config) if trigger_config else {},
                command=command,
                description=description or "",
                created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(),
                last_run=datetime.fromisoformat(last_run) if last_run else None,
                status=JobStatus(status) if status else JobStatus.ACTIVE,
                job_type=JobType(job_type) if job_type else JobType.COMMAND,
                task_instruction=task_instruction or "",
                max_steps=max_steps or 10,
                result_action=result_action or "notify",
                result_file=result_file or "",
            )
        # 14个字段（新格式，有last_result）
        # 顺序: job_id, trigger_type, trigger_config, command, description, created_at, last_run, status, last_result, job_type, task_instruction, max_steps, result_action, result_file
        (job_id, trigger_type, trigger_config, command, description, created_at, last_run, status, last_result,
         job_type, task_instruction, max_steps, result_action, result_file) = row
        return cls(
            job_id=job_id,
            trigger_type=TriggerType(trigger_type),
            trigger_config=json.loads(trigger_config) if trigger_config else {},
            command=command,
            description=description or "",
            created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(),
            last_run=datetime.fromisoformat(last_run) if last_run else None,
            status=JobStatus(status) if status else JobStatus.ACTIVE,
            job_type=JobType(job_type) if job_type else JobType.COMMAND,
            task_instruction=task_instruction or "",
            max_steps=max_steps or 10,
            result_action=result_action or "notify",
            result_file=result_file or "",
            last_result=last_result or "",
        )


@dataclass
class StoredSchedule:
    """存储的日程数据。"""
    id: int | None
    title: str
    content: str
    scheduled_time: datetime | None
    status: ScheduleStatus
    tags: str  # JSON 字符串
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None,
            "status": self.status.value,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_row(cls, row: tuple) -> StoredSchedule:
        """从数据库行创建对象。"""
        sid, title, content, scheduled_time, status, tags, created_at, updated_at = row
        return cls(
            id=sid,
            title=title,
            content=content or "",
            scheduled_time=datetime.fromisoformat(scheduled_time) if scheduled_time else None,
            status=ScheduleStatus(status) if status else ScheduleStatus.PENDING,
            tags=tags or "[]",
            created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(),
            updated_at=datetime.fromisoformat(updated_at) if updated_at else datetime.now(),
        )


class CronStorage:
    """Cron 任务持久化存储。"""
    
    # 默认数据库路径
    DEFAULT_DB_PATH = Path.home() / ".winclaw" / "cron_jobs.db"
    
    def __init__(self, db_path: Path | str | None = None):
        """初始化存储。
        
        Args:
            db_path: 数据库文件路径,为 None 时使用默认路径
        """
        self._db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"CronStorage 初始化完成: {self._db_path}")
    
    def _init_db(self) -> None:
        """初始化数据库表。"""
        with self._get_connection() as conn:
            # 创建任务表（支持 AI 任务）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cron_jobs (
                    job_id TEXT PRIMARY KEY,
                    trigger_type TEXT NOT NULL,
                    trigger_config TEXT NOT NULL,
                    command TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    last_run TEXT,
                    last_result TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    job_type TEXT NOT NULL DEFAULT 'command',
                    task_instruction TEXT DEFAULT '',
                    max_steps INTEGER DEFAULT 10,
                    result_action TEXT DEFAULT 'notify',
                    result_file TEXT DEFAULT ''
                )
            """)
            # 尝试添加新列（兼容旧数据库）
            try:
                conn.execute("ALTER TABLE cron_jobs ADD COLUMN job_type TEXT NOT NULL DEFAULT 'command'")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE cron_jobs ADD COLUMN task_instruction TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE cron_jobs ADD COLUMN max_steps INTEGER DEFAULT 10")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE cron_jobs ADD COLUMN result_action TEXT DEFAULT 'notify'")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE cron_jobs ADD COLUMN result_file TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE cron_jobs ADD COLUMN last_result TEXT")
            except sqlite3.OperationalError:
                pass
            conn.commit()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT DEFAULT '',
                    scheduled_time TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    tags TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_schedules_status
                ON schedules(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_schedules_scheduled_time
                ON schedules(scheduled_time)
            """)
            conn.commit()
    
    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """获取数据库连接。"""
        conn = sqlite3.connect(str(self._db_path))
        try:
            yield conn
        finally:
            conn.close()
    
    def save_job(self, job: StoredJob) -> None:
        """保存任务。
            
        Args:
            job: 要保存的任务
        """
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cron_jobs 
                (job_id, trigger_type, trigger_config, command, description, created_at, last_run, last_result, status,
                 job_type, task_instruction, max_steps, result_action, result_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.job_id,
                job.trigger_type.value,
                json.dumps(job.trigger_config),
                job.command,
                job.description,
                job.created_at.isoformat(),
                job.last_run.isoformat() if job.last_run else None,
                job.last_result,
                job.status.value,
                job.job_type.value,
                job.task_instruction,
                job.max_steps,
                job.result_action,
                job.result_file,
            ))
            conn.commit()
        logger.debug(f"任务已保存: {job.job_id}")
    
    def get_job(self, job_id: str) -> StoredJob | None:
        """获取指定任务。
        
        Args:
            job_id: 任务ID
            
        Returns:
            任务对象,不存在返回 None
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT job_id, trigger_type, trigger_config, command, description, created_at, last_run, status, last_result,
                       job_type, task_instruction, max_steps, result_action, result_file 
                FROM cron_jobs WHERE job_id = ?""",
                (job_id,)
            )
            row = cursor.fetchone()
            if row:
                return StoredJob.from_row(row)
        return None
    
    def get_all_jobs(self) -> list[StoredJob]:
        """获取所有任务。
        
        Returns:
            任务列表
        """
        jobs = []
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT job_id, trigger_type, trigger_config, command, description, created_at, last_run, status, last_result,
                       job_type, task_instruction, max_steps, result_action, result_file 
                FROM cron_jobs
            """)
            for row in cursor.fetchall():
                jobs.append(StoredJob.from_row(row))
        return jobs
    
    def get_active_jobs(self) -> list[StoredJob]:
        """获取所有活动状态的任务。
        
        Returns:
            活动任务列表
        """
        jobs = []
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT job_id, trigger_type, trigger_config, command, description, created_at, last_run, status, last_result,
                       job_type, task_instruction, max_steps, result_action, result_file 
                FROM cron_jobs WHERE status = ?""",
                (JobStatus.ACTIVE.value,)
            )
            for row in cursor.fetchall():
                jobs.append(StoredJob.from_row(row))
        return jobs
    
    def delete_job(self, job_id: str) -> bool:
        """删除任务。
        
        Args:
            job_id: 任务ID
            
        Returns:
            是否删除成功
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM cron_jobs WHERE job_id = ?",
                (job_id,)
            )
            conn.commit()
            deleted = cursor.rowcount > 0
        if deleted:
            logger.debug(f"任务已删除: {job_id}")
        return deleted
    
    def update_status(self, job_id: str, status: JobStatus) -> bool:
        """更新任务状态。
        
        Args:
            job_id: 任务ID
            status: 新状态
            
        Returns:
            是否更新成功
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE cron_jobs SET status = ? WHERE job_id = ?",
                (status.value, job_id)
            )
            conn.commit()
            updated = cursor.rowcount > 0
        if updated:
            logger.debug(f"任务状态已更新: {job_id} -> {status.value}")
        return updated
    
    def update_last_run(self, job_id: str, last_run: datetime | None = None) -> bool:
        """更新任务最后执行时间。
        
        Args:
            job_id: 任务ID
            last_run: 最后执行时间,为 None 时使用当前时间
            
        Returns:
            是否更新成功
        """
        if last_run is None:
            last_run = datetime.now()
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE cron_jobs SET last_run = ? WHERE job_id = ?",
                (last_run.isoformat(), job_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def update_last_result(self, job_id: str, result: str) -> bool:
        """更新任务执行结果。
        
        Args:
            job_id: 任务ID
            result: 执行结果文本
            
        Returns:
            是否更新成功
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE cron_jobs SET last_result = ? WHERE job_id = ?",
                (result, job_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def clear_all(self) -> int:
        """清空所有任务。
        
        Returns:
            删除的任务数量
        """
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM cron_jobs")
            conn.commit()
            count = cursor.rowcount
        logger.info(f"已清空所有任务: {count} 条")
        return count
    
    def get_job_count(self) -> int:
        """获取任务总数。
        
        Returns:
            任务数量
        """
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cron_jobs")
            return cursor.fetchone()[0]

    # ----------------------------------------------------------------
    # 日程管理方法
    # ----------------------------------------------------------------

    def save_schedule(self, schedule: StoredSchedule) -> int:
        """保存日程，返回日程 ID。"""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            if schedule.id is not None:
                # 更新
                conn.execute("""
                    INSERT OR REPLACE INTO schedules
                    (id, title, content, scheduled_time, status, tags, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    schedule.id,
                    schedule.title,
                    schedule.content,
                    schedule.scheduled_time.isoformat() if schedule.scheduled_time else None,
                    schedule.status.value,
                    schedule.tags,
                    schedule.created_at.isoformat(),
                    now,
                ))
                conn.commit()
                return schedule.id
            else:
                # 新建
                cursor = conn.execute("""
                    INSERT INTO schedules
                    (title, content, scheduled_time, status, tags, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    schedule.title,
                    schedule.content,
                    schedule.scheduled_time.isoformat() if schedule.scheduled_time else None,
                    schedule.status.value,
                    schedule.tags,
                    now,
                    now,
                ))
                conn.commit()
                return cursor.lastrowid or 0

    def get_schedule(self, schedule_id: int) -> StoredSchedule | None:
        """获取指定日程。"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, title, content, scheduled_time, status, tags, created_at, updated_at "
                "FROM schedules WHERE id = ?",
                (schedule_id,)
            )
            row = cursor.fetchone()
            if row:
                return StoredSchedule.from_row(row)
        return None

    def query_schedules(
        self,
        status: str = "all",
        keyword: str = "",
        limit: int = 20,
    ) -> list[StoredSchedule]:
        """查询日程列表。"""
        clauses = []
        params: list[Any] = []

        if status and status != "all":
            if status == "upcoming":
                clauses.append("status = 'pending' AND scheduled_time >= ?")
                params.append(datetime.now().isoformat())
            elif status == "today":
                today = datetime.now().strftime("%Y-%m-%d")
                clauses.append("scheduled_time LIKE ?")
                params.append(f"{today}%")
            else:
                clauses.append("status = ?")
                params.append(status)

        if keyword:
            clauses.append("(title LIKE ? OR content LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = (
            f"SELECT id, title, content, scheduled_time, status, tags, created_at, updated_at "
            f"FROM schedules WHERE {where} "
            f"ORDER BY COALESCE(scheduled_time, updated_at) DESC LIMIT ?"
        )
        params.append(limit)

        schedules = []
        with self._get_connection() as conn:
            cursor = conn.execute(sql, params)
            for row in cursor.fetchall():
                schedules.append(StoredSchedule.from_row(row))
        return schedules

    def update_schedule(self, schedule_id: int, **fields: Any) -> bool:
        """更新日程字段。"""
        allowed = {"title", "content", "scheduled_time", "status", "tags"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return False

        updates["updated_at"] = datetime.now().isoformat()
        # 处理 datetime 类型的 scheduled_time
        if "scheduled_time" in updates and isinstance(updates["scheduled_time"], datetime):
            updates["scheduled_time"] = updates["scheduled_time"].isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [schedule_id]

        with self._get_connection() as conn:
            cursor = conn.execute(
                f"UPDATE schedules SET {set_clause} WHERE id = ?", values
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_schedule(self, schedule_id: int) -> bool:
        """删除日程。"""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            conn.commit()
            return cursor.rowcount > 0

    def complete_schedule(self, schedule_id: int) -> bool:
        """标记日程为已完成。"""
        return self.update_schedule(schedule_id, status=ScheduleStatus.COMPLETED.value)

