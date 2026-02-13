"""Medication 工具 — 服药管理（CRUD）。

支持动作：
- add_medication: 添加新药物，建立用药计划
- query_medications: 查询药物列表和今日服药状态
- mark_medication_taken: 标记已服药
- update_medication: 更新药物信息
- delete_medication: 停用药物（软删除）

存储位置：~/.winclaw/winclaw_tools.db（medications + medication_logs 表）
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".winclaw" / "winclaw_tools.db"

# 有效频率值
_VALID_FREQUENCIES = ("daily", "twice", "three_times", "as_needed")

# 状态图标
_STATUS_ICONS = {
    "taken": "✅",
    "missed": "❌",
    "skipped": "⏭️",
    "pending": "⏳",
}


class MedicationTool(BaseTool):
    """服药管理工具。

    支持药物的添加、查询、标记服用、更新和停用，
    数据存储到 ~/.winclaw/winclaw_tools.db 的 medications 和 medication_logs 表。
    """

    name = "medication"
    emoji = "💊"
    title = "服药管理"
    description = "添加药物、查询服药计划、标记已服药、更新和停用药物"

    def __init__(self, db_path: str = ""):
        super().__init__()
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._db_path))
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """初始化数据库表"""
        with self._conn() as conn:
            # 药物信息表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS medications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    dosage TEXT,
                    frequency TEXT,
                    time_slots TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    instructions TEXT,
                    remaining_days INTEGER,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_medications_active ON medications(is_active)
            """)

            # 服药记录表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS medication_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    medication_id INTEGER NOT NULL,
                    scheduled_time TEXT NOT NULL,
                    actual_time TEXT,
                    status TEXT NOT NULL,
                    quantity INTEGER,
                    notes TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_medication_logs_date ON medication_logs(scheduled_time)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_medication_logs_med_id ON medication_logs(medication_id)
            """)
            conn.commit()

    # ------------------------------------------------------------------

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="add_medication",
                description="添加新药物，建立用药计划",
                parameters={
                    "name": {
                        "type": "string",
                        "description": "药物名称",
                    },
                    "dosage": {
                        "type": "string",
                        "description": "剂量，如 1片、10ml（可选）",
                    },
                    "frequency": {
                        "type": "string",
                        "description": "频率: daily/twice/three_times/as_needed",
                    },
                    "time_slots": {
                        "type": "string",
                        "description": "服药时间，JSON数组如 [\"08:00\"] 或 [\"08:00\",\"20:00\"]",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期 YYYY-MM-DD，默认今天（可选）",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期 YYYY-MM-DD（可选）",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "用药说明（可选）",
                    },
                    "remaining_days": {
                        "type": "integer",
                        "description": "剩余可用天数（可选）",
                    },
                },
                required_params=["name", "frequency", "time_slots"],
            ),
            ActionDef(
                name="query_medications",
                description="查询药物列表和今日服药状态",
                parameters={
                    "status": {
                        "type": "string",
                        "description": "筛选: active/all，默认 active",
                    },
                    "date": {
                        "type": "string",
                        "description": "查询日期 YYYY-MM-DD，默认今天",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="mark_medication_taken",
                description="标记已服药",
                parameters={
                    "medication_id": {
                        "type": "integer",
                        "description": "药物ID",
                    },
                    "actual_time": {
                        "type": "string",
                        "description": "实际服药时间 YYYY-MM-DD HH:MM，默认当前时间（可选）",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "服用数量，默认1",
                    },
                    "notes": {
                        "type": "string",
                        "description": "备注（可选）",
                    },
                },
                required_params=["medication_id"],
            ),
            ActionDef(
                name="update_medication",
                description="更新药物信息",
                parameters={
                    "medication_id": {
                        "type": "integer",
                        "description": "药物ID",
                    },
                    "name": {
                        "type": "string",
                        "description": "新名称（可选）",
                    },
                    "dosage": {
                        "type": "string",
                        "description": "新剂量（可选）",
                    },
                    "frequency": {
                        "type": "string",
                        "description": "新频率（可选）",
                    },
                    "time_slots": {
                        "type": "string",
                        "description": "新时间 JSON数组（可选）",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "新开始日期（可选）",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "新结束日期（可选）",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "新说明（可选）",
                    },
                    "remaining_days": {
                        "type": "integer",
                        "description": "新剩余天数（可选）",
                    },
                },
                required_params=["medication_id"],
            ),
            ActionDef(
                name="delete_medication",
                description="停用药物（软删除）",
                parameters={
                    "medication_id": {
                        "type": "integer",
                        "description": "药物ID",
                    },
                },
                required_params=["medication_id"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "add_medication": self._add_medication,
            "query_medications": self._query_medications,
            "mark_medication_taken": self._mark_medication_taken,
            "update_medication": self._update_medication,
            "delete_medication": self._delete_medication,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"不支持的动作: {action}")
        try:
            return handler(params)
        except Exception as e:
            logger.error("服药管理操作失败: %s", e)
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))

    # ------------------------------------------------------------------

    def _add_medication(self, params: dict[str, Any]) -> ToolResult:
        """添加新药物"""
        name = params.get("name", "").strip()
        dosage = params.get("dosage", "").strip()
        frequency = params.get("frequency", "").strip()
        time_slots_str = params.get("time_slots", "").strip()
        start_date = params.get("start_date", "").strip()
        end_date = params.get("end_date", "").strip()
        instructions = params.get("instructions", "").strip()
        remaining_days = params.get("remaining_days")

        # 校验必填
        if not name:
            return ToolResult(status=ToolResultStatus.ERROR, error="请提供药物名称")
        if not frequency:
            return ToolResult(status=ToolResultStatus.ERROR, error="请提供服药频率")
        if frequency not in _VALID_FREQUENCIES:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"频率无效，可选: {', '.join(_VALID_FREQUENCIES)}",
            )
        if not time_slots_str:
            return ToolResult(status=ToolResultStatus.ERROR, error="请指定服药时间")

        # 解析 time_slots
        try:
            time_slots = json.loads(time_slots_str)
            if not isinstance(time_slots, list) or not time_slots:
                raise ValueError("time_slots 必须是非空数组")
        except json.JSONDecodeError:
            return ToolResult(status=ToolResultStatus.ERROR, error="time_slots 必须是有效的 JSON 数组")

        # 默认日期
        today = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = today

        now = datetime.now()
        created_at = now.isoformat()
        updated_at = now.isoformat()

        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT INTO medications (
                    name, dosage, frequency, time_slots, start_date, end_date,
                    instructions, remaining_days, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (
                name, dosage or None, frequency,
                json.dumps(time_slots, ensure_ascii=False),
                start_date, end_date or None,
                instructions or None, remaining_days,
                created_at, updated_at,
            ))
            conn.commit()
            medication_id = cursor.lastrowid

        # 构建今日计划输出
        output = f"💊 已添加药物 (ID: {medication_id})\n"
        output += f"  名称: {name}\n"
        output += f"  剂量: {dosage or '未指定'}\n"
        output += f"  频率: {frequency}\n"
        output += f"  时间: {', '.join(time_slots)}\n"
        if start_date:
            output += f"  开始: {start_date}\n"
        if end_date:
            output += f"  结束: {end_date}\n"

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={
                "medication_id": medication_id,
                "name": name,
                "frequency": frequency,
                "time_slots": time_slots,
            },
        )

    def _query_medications(self, params: dict[str, Any]) -> ToolResult:
        """查询药物列表和今日服药状态"""
        status_filter = params.get("status", "active").strip()
        query_date = params.get("date", "").strip()

        # 默认今天
        if not query_date:
            query_date = datetime.now().strftime("%Y-%m-%d")

        # 查询药物
        with self._conn() as conn:
            if status_filter == "all":
                sql = "SELECT * FROM medications ORDER BY is_active DESC, id DESC"
                rows = conn.execute(sql).fetchall()
            else:
                sql = "SELECT * FROM medications WHERE is_active = 1 ORDER BY id DESC"
                rows = conn.execute(sql).fetchall()

            if not rows:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output="暂无药物记录。",
                    data={"medications": [], "date": query_date, "total_taken": 0, "total_pending": 0},
                )

            # 查询当日服药记录
            log_rows = conn.execute("""
                SELECT medication_id, scheduled_time, status
                FROM medication_logs
                WHERE date(scheduled_time) = ?
            """, (query_date,)).fetchall()

        # 构建记录映射
        log_map: dict[int, list[str]] = {}
        for med_id, sched_time, log_status in log_rows:
            if med_id not in log_map:
                log_map[med_id] = []
            log_map[med_id].append(log_status)

        # 汇总统计
        total_taken = 0
        total_pending = 0

        # 构建输出
        lines = [f"💊 服药计划 ({query_date}):"]
        med_list = []

        for row in rows:
            (med_id, name, dosage, frequency, time_slots_json, start_date,
             end_date, instructions, remaining_days, is_active, created_at, updated_at) = row

            # 解析时间
            try:
                time_slots = json.loads(time_slots_json) if time_slots_json else []
            except json.JSONDecodeError:
                time_slots = []

            # 状态
            status_icon = "" if is_active else " (已停用)"
            logs = log_map.get(med_id, [])

            # 检查每个时间点
            for slot in time_slots:
                slot_status = "taken" if "taken" in logs else "pending"
                if slot_status == "taken":
                    total_taken += 1
                else:
                    total_pending += 1

                icon = _STATUS_ICONS.get(slot_status, "⏳")
                status_text = "已服" if slot_status == "taken" else "待服"
                lines.append(f"  {icon} {name} - {dosage or '1次'} - {slot} {status_text}{status_icon}")

            med_list.append({
                "id": med_id,
                "name": name,
                "dosage": dosage,
                "frequency": frequency,
                "time_slots": time_slots,
                "is_active": bool(is_active),
            })

        lines.append(f"\n今日完成: {total_taken}/{total_taken + total_pending}")

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={
                "medications": med_list,
                "date": query_date,
                "total_taken": total_taken,
                "total_pending": total_pending,
            },
        )

    def _mark_medication_taken(self, params: dict[str, Any]) -> ToolResult:
        """标记已服药"""
        medication_id = params.get("medication_id")
        actual_time = params.get("actual_time", "").strip()
        quantity = params.get("quantity", 1)
        notes = params.get("notes", "").strip()

        if medication_id is None:
            return ToolResult(status=ToolResultStatus.ERROR, error="请提供药物ID")

        # 查找药物
        with self._conn() as conn:
            row = conn.execute(
                "SELECT name, time_slots FROM medications WHERE id = ?",
                (medication_id,),
            ).fetchone()
            if not row:
                return ToolResult(status=ToolResultStatus.ERROR, error=f"药物不存在: ID {medication_id}")

            name, time_slots_json = row

            # 解析时间
            try:
                time_slots = json.loads(time_slots_json) if time_slots_json else []
            except json.JSONDecodeError:
                time_slots = []

        # 确定实际时间
        if not actual_time:
            now = datetime.now()
        else:
            try:
                # 尝试解析完整时间
                if len(actual_time) == 16:  # YYYY-MM-DD HH:MM
                    now = datetime.strptime(actual_time, "%Y-%m-%d %H:%M")
                elif len(actual_time) == 10:  # YYYY-MM-DD
                    now = datetime.strptime(actual_time, "%Y-%m-%d")
                else:
                    now = datetime.now()
            except ValueError:
                now = datetime.now()

        scheduled_time = now.strftime("%Y-%m-%d %H:%M")
        actual_time_str = now.isoformat()
        now_str = now.isoformat()

        # 插入记录
        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT INTO medication_logs (
                    medication_id, scheduled_time, actual_time, status, quantity, notes, created_at
                ) VALUES (?, ?, ?, 'taken', ?, ?, ?)
            """, (medication_id, scheduled_time, actual_time_str, quantity, notes or None, now_str))
            conn.commit()
            log_id = cursor.lastrowid

        output = f"✅ 已记录服药 (ID: {log_id})\n"
        output += f"  药物: {name}\n"
        output += f"  时间: {scheduled_time}\n"
        if quantity > 1:
            output += f"  数量: {quantity}\n"
        if notes:
            output += f"  备注: {notes}\n"

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={
                "log_id": log_id,
                "medication_id": medication_id,
                "name": name,
                "scheduled_time": scheduled_time,
                "quantity": quantity,
            },
        )

    def _update_medication(self, params: dict[str, Any]) -> ToolResult:
        """更新药物信息"""
        medication_id = params.get("medication_id")
        if medication_id is None:
            return ToolResult(status=ToolResultStatus.ERROR, error="请提供药物ID")

        # 收集要更新的字段
        updates: dict[str, Any] = {}
        for key in ("name", "dosage", "frequency", "time_slots", "start_date",
                    "end_date", "instructions", "remaining_days"):
            if key in params and params[key]:
                value = params[key]
                # 解析 JSON 字段
                if key == "time_slots" and isinstance(value, str):
                    try:
                        json.loads(value)  # 验证 JSON
                    except json.JSONDecodeError:
                        return ToolResult(status=ToolResultStatus.ERROR, error="time_slots 必须是有效的 JSON")
                updates[key] = value

        if not updates:
            return ToolResult(status=ToolResultStatus.ERROR, error="没有可更新的字段")

        updates["updated_at"] = datetime.now().isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [medication_id]

        with self._conn() as conn:
            cursor = conn.execute(
                f"UPDATE medications SET {set_clause} WHERE id = ?",
                values,
            )
            conn.commit()
            if cursor.rowcount == 0:
                return ToolResult(status=ToolResultStatus.ERROR, error=f"药物不存在: ID {medication_id}")

        # 获取更新后的信息
        with self._conn() as conn:
            row = conn.execute(
                "SELECT name, dosage, frequency, time_slots FROM medications WHERE id = ?",
                (medication_id,),
            ).fetchone()
            name, dosage, frequency, time_slots_json = row
            time_slots = json.loads(time_slots_json) if time_slots_json else []

        output = f"✅ 已更新药物 (ID: {medication_id})\n"
        output += f"  名称: {name}\n"
        output += f"  剂量: {dosage or '未指定'}\n"
        output += f"  频率: {frequency}\n"
        if time_slots:
            output += f"  时间: {', '.join(time_slots)}\n"

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={
                "medication_id": medication_id,
                "updated_fields": list(updates.keys()),
            },
        )

    def _delete_medication(self, params: dict[str, Any]) -> ToolResult:
        """停用药物（软删除）"""
        medication_id = params.get("medication_id")
        if medication_id is None:
            return ToolResult(status=ToolResultStatus.ERROR, error="请提供药物ID")

        now = datetime.now().isoformat()

        with self._conn() as conn:
            # 获取药物信息
            row = conn.execute(
                "SELECT name FROM medications WHERE id = ?",
                (medication_id,),
            ).fetchone()
            if not row:
                return ToolResult(status=ToolResultStatus.ERROR, error=f"药物不存在: ID {medication_id}")

            name = row[0]

            # 软删除
            cursor = conn.execute(
                "UPDATE medications SET is_active = 0, updated_at = ? WHERE id = ?",
                (now, medication_id),
            )
            conn.commit()

        output = f"✅ 已停用药物 (ID: {medication_id})\n"
        output += f"  名称: {name}\n"
        output += f"  状态: 已停用（可恢复）\n"

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={
                "medication_id": medication_id,
                "name": name,
                "is_active": False,
            },
        )
