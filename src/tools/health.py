"""Health 工具 — 健康管理。

支持动作：
- record_health_data: 记录健康数据（追加模式）
- update_health_data: 更新已有记录
- delete_health_data: 删除记录
- query_health_data: 查询记录
- get_health_trends: 趋势分析

借鉴来源：参考项目_changoai/backend/tool_functions.py 健康管理相关函数
存储位置：~/.winclaw/winclaw_tools.db（health_records 表）
"""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator, Optional

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".winclaw" / "winclaw_tools.db"

# 心情选项
_VALID_MOODS = {"happy", "sad", "neutral", "excited", "anxious", "calm", "stressed"}

_MOOD_ICONS = {
    "happy": "😊", "sad": "😢", "neutral": "😐",
    "excited": "🤩", "anxious": "😰", "calm": "😌", "stressed": "😫",
}

# 指标分类：取最新值 vs 列出全部
_METRIC_STRATEGY = {
    # 基础体征 - 取最新值
    "height": "latest",
    "weight": "latest",
    "body_fat": "latest",
    # 生命体征 - 列出全部
    "bp_systolic": "all",
    "bp_diastolic": "all",
    "heart_rate": "all",
    "body_temp": "all",
    "blood_oxygen": "all",
    "blood_glucose": "all",
    # 生活数据 - 取最新值
    "steps": "latest",
    "sleep_hours": "latest",
    "water_intake": "latest",
    # 主观感受 - 取最新值
    "mood": "latest",
    "energy_level": "latest",
}


class HealthTool(BaseTool):
    """健康管理工具。

    支持健康数据的记录、查询、趋势分析。
    数据存储到 ~/.winclaw/winclaw_tools.db 的 health_records 表。
    采用追加模式，每次记录创建新行，支持同一天多次记录。
    """

    name = "health"
    emoji = "🏥"
    title = "健康管理"
    description = "记录健康数据、查询历史、趋势分析（体重/血压/心率等）"

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
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS health_records (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_date     TEXT    NOT NULL,
                    record_time     TEXT    NOT NULL,
                    -- 基础体征
                    height          INTEGER,
                    weight          INTEGER,
                    body_fat        INTEGER,
                    -- 生命体征
                    bp_systolic     INTEGER,
                    bp_diastolic    INTEGER,
                    heart_rate      INTEGER,
                    body_temp       INTEGER,
                    blood_oxygen    INTEGER,
                    blood_glucose   INTEGER,
                    -- 生活数据
                    steps           INTEGER,
                    sleep_hours     INTEGER,
                    water_intake    INTEGER,
                    -- 主观感受
                    mood            TEXT,
                    energy_level    INTEGER,
                    notes           TEXT,
                    -- 时间戳
                    created_at      TEXT    NOT NULL,
                    updated_at      TEXT    NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_health_date
                ON health_records(record_date DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_health_date_time
                ON health_records(record_date, record_time DESC)
            """)
            conn.commit()

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="record_health_data",
                description="记录健康数据（追加模式，支持只填部分指标）",
                parameters={
                    "date": {
                        "type": "string",
                        "description": "记录日期 YYYY-MM-DD，默认今天",
                    },
                    "time": {
                        "type": "string",
                        "description": "记录时间 HH:MM，默认当前时间",
                    },
                    "height": {
                        "type": "number",
                        "description": "身高(cm)",
                    },
                    "weight": {
                        "type": "number",
                        "description": "体重(kg)，支持小数如 65.5",
                    },
                    "body_fat": {
                        "type": "number",
                        "description": "体脂率(%)，支持小数",
                    },
                    "blood_pressure": {
                        "type": "string",
                        "description": "血压，格式如 120/80（可选）",
                    },
                    "bp_systolic": {
                        "type": "integer",
                        "description": "收缩压(mmHg)，直接传数字更准确",
                    },
                    "bp_diastolic": {
                        "type": "integer",
                        "description": "舒张压(mmHg)，直接传数字更准确",
                    },
                    "heart_rate": {
                        "type": "integer",
                        "description": "心率(bpm)",
                    },
                    "body_temp": {
                        "type": "number",
                        "description": "体温(摄氏度)，支持小数如 36.5",
                    },
                    "blood_oxygen": {
                        "type": "integer",
                        "description": "血氧饱和度(%)",
                    },
                    "blood_glucose": {
                        "type": "number",
                        "description": "血糖(mmol/L)，支持小数",
                    },
                    "steps": {
                        "type": "integer",
                        "description": "步数",
                    },
                    "sleep_hours": {
                        "type": "number",
                        "description": "睡眠时长(小时)，支持小数如 7.5",
                    },
                    "water_intake": {
                        "type": "integer",
                        "description": "饮水量(ml)",
                    },
                    "mood": {
                        "type": "string",
                        "description": "心情: happy/sad/neutral/excited/anxious/calm/stressed",
                    },
                    "energy_level": {
                        "type": "integer",
                        "description": "精力水平 1-10",
                    },
                    "notes": {
                        "type": "string",
                        "description": "备注",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="update_health_data",
                description="更新已有的健康记录（用于纠正错误数据）",
                parameters={
                    "record_id": {
                        "type": "integer",
                        "description": "要更新的记录 ID",
                    },
                    "date": {
                        "type": "string",
                        "description": "新记录日期 YYYY-MM-DD（可选）",
                    },
                    "time": {
                        "type": "string",
                        "description": "新记录时间 HH:MM（可选）",
                    },
                    "height": {
                        "type": "number",
                        "description": "身高(cm)（可选）",
                    },
                    "weight": {
                        "type": "number",
                        "description": "体重(kg)（可选）",
                    },
                    "body_fat": {
                        "type": "number",
                        "description": "体脂率(%)(可选)",
                    },
                    "blood_pressure": {
                        "type": "string",
                        "description": "血压（可选）",
                    },
                    "bp_systolic": {
                        "type": "integer",
                        "description": "收缩压（可选）",
                    },
                    "bp_diastolic": {
                        "type": "integer",
                        "description": "舒张压（可选）",
                    },
                    "heart_rate": {
                        "type": "integer",
                        "description": "心率（可选）",
                    },
                    "body_temp": {
                        "type": "number",
                        "description": "体温（可选）",
                    },
                    "blood_oxygen": {
                        "type": "integer",
                        "description": "血氧（可选）",
                    },
                    "blood_glucose": {
                        "type": "number",
                        "description": "血糖（可选）",
                    },
                    "steps": {
                        "type": "integer",
                        "description": "步数（可选）",
                    },
                    "sleep_hours": {
                        "type": "number",
                        "description": "睡眠时长（可选）",
                    },
                    "water_intake": {
                        "type": "integer",
                        "description": "饮水量（可选）",
                    },
                    "mood": {
                        "type": "string",
                        "description": "心情（可选）",
                    },
                    "energy_level": {
                        "type": "integer",
                        "description": "精力水平（可选）",
                    },
                    "notes": {
                        "type": "string",
                        "description": "备注（可选）",
                    },
                },
                required_params=["record_id"],
            ),
            ActionDef(
                name="delete_health_data",
                description="删除指定的健康记录",
                parameters={
                    "record_id": {
                        "type": "integer",
                        "description": "要删除的记录 ID",
                    },
                },
                required_params=["record_id"],
            ),
            ActionDef(
                name="query_health_data",
                description="查询健康记录，支持按时间范围和指标类型筛选",
                parameters={
                    "date_range": {
                        "type": "string",
                        "description": "时间范围: today/yesterday/week/month/year/all，默认 today",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "自定义开始日期 YYYY-MM-DD（可选）",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "自定义结束日期 YYYY-MM-DD（可选）",
                    },
                    "metric": {
                        "type": "string",
                        "description": "指定查询的指标类型(可选): weight/blood_pressure/heart_rate 等",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回条数，默认 20",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="get_health_trends",
                description="获取指定指标的趋势数据，用于分析变化",
                parameters={
                    "metric": {
                        "type": "string",
                        "description": "要分析的指标: weight/blood_pressure/heart_rate/body_temp/blood_glucose/sleep_hours 等",
                    },
                    "period": {
                        "type": "string",
                        "description": "分析周期: week/month/quarter/year，默认 month",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "自定义开始日期（可选）",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "自定义结束日期（可选）",
                    },
                },
                required_params=["metric"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "record_health_data": self._record_health_data,
            "update_health_data": self._update_health_data,
            "delete_health_data": self._delete_health_data,
            "query_health_data": self._query_health_data,
            "get_health_trends": self._get_health_trends,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"不支持的动作: {action}")
        try:
            return handler(params)
        except Exception as e:
            logger.error("健康管理操作失败: %s", e)
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _parse_bp(self, bp_str: str) -> tuple[int, int] | None:
        """解析血压字符串，如 '120/80'"""
        if not bp_str:
            return None
        match = re.match(r"^(\d+)\s*/\s*(\d+)$", bp_str.strip())
        if match:
            return int(match.group(1)), int(match.group(2))
        return None

    def _to_cents(self, value: float | int | None) -> int | None:
        """将浮点数转为整数存储（x10）"""
        if value is None:
            return None
        return int(round(float(value) * 10))

    def _from_cents(self, value: int | None) -> float | None:
        """将整数转为浮点数（/10）"""
        if value is None:
            return None
        return value / 10

    def _calculate_bmi(self, weight_cents: int | None, height: int | None) -> float | None:
        """计算BMI"""
        if weight_cents is None or height is None or height == 0:
            return None
        weight_kg = weight_cents / 10
        return round(weight_kg / ((height / 100) ** 2), 1)

    def _check_warnings(
        self,
        bp_systolic: int | None,
        bp_diastolic: int | None,
        heart_rate: int | None,
        body_temp: int | None,
        blood_oxygen: int | None,
        blood_glucose: int | None,
        bmi: float | None,
    ) -> list[str]:
        """检查健康警告"""
        warnings = []

        # 血压
        if bp_systolic and (bp_systolic >= 140 or bp_diastolic and bp_diastolic >= 90):
            warnings.append("⚠️ 血压偏高: 收缩压≥140或舒张压≥90")
        if bp_systolic and bp_systolic < 90:
            warnings.append("⚠️ 血压偏低: 收缩压<90")
        if bp_diastolic and bp_diastolic < 60:
            warnings.append("⚠️ 舒张压偏低: <60")

        # 心率
        if heart_rate and heart_rate > 100:
            warnings.append("⚠️ 心率偏快: >100 bpm")
        if heart_rate and heart_rate < 50:
            warnings.append("⚠️ 心率偏慢: <50 bpm")

        # 血糖
        if blood_glucose and blood_glucose > 70:  # >7.0 mmol/L
            warnings.append("⚠️ 血糖偏高: >7.0 mmol/L")
        if blood_glucose and blood_glucose < 39:  # <3.9 mmol/L
            warnings.append("⚠️ 血糖偏低: <3.9 mmol/L")

        # 体温
        if body_temp and body_temp > 373:  # >37.3°C
            warnings.append("⚠️ 体温偏高: >37.3°C")

        # 血氧
        if blood_oxygen and blood_oxygen < 95:
            warnings.append("⚠️ 血氧偏低: <95%")

        # BMI
        if bmi:
            if bmi >= 28.0:
                warnings.append(f"⚠️ BMI肥胖: {bmi} ≥28.0")
            elif bmi >= 24.0:
                warnings.append(f"⚠️ BMI超重: {bmi} ≥24.0")
            elif bmi < 18.5:
                warnings.append(f"⚠️ BMI偏瘦: {bmi} <18.5")

        return warnings

    def _get_date_range(self, date_range: str, start_date: str, end_date: str) -> tuple[str, str]:
        """解析日期范围参数"""
        today = datetime.now().strftime("%Y-%m-%d")

        if start_date and end_date:
            return start_date, end_date

        if date_range == "today":
            return today, today
        elif date_range == "yesterday":
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            return yesterday, yesterday
        elif date_range == "week":
            start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            return start, today
        elif date_range == "month":
            start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            return start, today
        elif date_range == "year":
            start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            return start, today
        else:  # all or default
            return "1900-01-01", today

    # ------------------------------------------------------------------
    # 动作实现
    # ------------------------------------------------------------------

    def _record_health_data(self, params: dict[str, Any]) -> ToolResult:
        # 日期时间处理
        now = datetime.now()
        record_date = params.get("date", "").strip() or now.strftime("%Y-%m-%d")
        record_time = params.get("time", "").strip() or now.strftime("%H:%M")

        # 验证日期格式
        try:
            datetime.strptime(record_date, "%Y-%m-%d")
        except ValueError:
            return ToolResult(status=ToolResultStatus.ERROR, error="日期格式错误，请使用 YYYY-MM-DD")

        # 验证时间格式
        try:
            datetime.strptime(record_time, "%H:%M")
        except ValueError:
            return ToolResult(status=ToolResultStatus.ERROR, error="时间格式错误，请使用 HH:MM")

        # 血压处理：优先使用独立参数
        bp_systolic = params.get("bp_systolic")
        bp_diastolic = params.get("bp_diastolic")

        if bp_systolic is not None or bp_diastolic is not None:
            # 独立参数：必须两者都有
            if bp_systolic is None or bp_diastolic is None:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error="血压需同时填写收缩压和舒张压"
                )
        else:
            # 尝试解析字符串格式
            bp_str = params.get("blood_pressure", "").strip()
            if bp_str:
                parsed = self._parse_bp(bp_str)
                if parsed:
                    bp_systolic, bp_diastolic = parsed
                else:
                    return ToolResult(
                        status=ToolResultStatus.ERROR,
                        error="血压格式错误，请使用如 120/80 格式"
                    )

        # 心情校验
        mood = params.get("mood", "").strip() or None
        if mood and mood not in _VALID_MOODS:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"心情值无效，可选: {', '.join(sorted(_VALID_MOODS))}"
            )

        # 准备字段值
        fields = {
            "height": params.get("height"),
            "weight": self._to_cents(params.get("weight")),
            "body_fat": self._to_cents(params.get("body_fat")),
            "bp_systolic": bp_systolic,
            "bp_diastolic": bp_diastolic,
            "heart_rate": params.get("heart_rate"),
            "body_temp": self._to_cents(params.get("body_temp")),
            "blood_oxygen": params.get("blood_oxygen"),
            "blood_glucose": self._to_cents(params.get("blood_glucose")),
            "steps": params.get("steps"),
            "sleep_hours": self._to_cents(params.get("sleep_hours")),
            "water_intake": params.get("water_intake"),
            "mood": mood,
            "energy_level": params.get("energy_level"),
            "notes": params.get("notes", "").strip() or None,
        }

        # 至少要有一个指标
        if not any(v is not None for v in fields.values()):
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="至少需要记录一项健康数据"
            )

        # 范围校验
        if fields.get("height") and (fields["height"] < 100 or fields["height"] > 250):
            return ToolResult(status=ToolResultStatus.ERROR, error="身高范围: 100-250 cm")
        if fields.get("weight") and (fields["weight"] < 300 or fields["weight"] > 2000):
            return ToolResult(status=ToolResultStatus.ERROR, error="体重范围: 30-200 kg")
        if fields.get("bp_systolic") and (fields["bp_systolic"] < 60 or fields["bp_systolic"] > 250):
            return ToolResult(status=ToolResultStatus.ERROR, error="收缩压范围: 60-250 mmHg")
        if fields.get("bp_diastolic") and (fields["bp_diastolic"] < 40 or fields["bp_diastolic"] > 150):
            return ToolResult(status=ToolResultStatus.ERROR, error="舒张压范围: 40-150 mmHg")
        if fields.get("heart_rate") and (fields["heart_rate"] < 40 or fields["heart_rate"] > 200):
            return ToolResult(status=ToolResultStatus.ERROR, error="心率范围: 40-200 bpm")
        if fields.get("energy_level") and (fields["energy_level"] < 1 or fields["energy_level"] > 10):
            return ToolResult(status=ToolResultStatus.ERROR, error="精力范围: 1-10")

        # 计算BMI（仅用于警告检测和返回）
        bmi = self._calculate_bmi(fields.get("weight"), fields.get("height"))

        # 生成健康警告
        warnings = self._check_warnings(
            fields.get("bp_systolic"),
            fields.get("bp_diastolic"),
            fields.get("heart_rate"),
            fields.get("body_temp"),
            fields.get("blood_oxygen"),
            fields.get("blood_glucose"),
            bmi,
        )

        # 插入数据库
        created_at = now.isoformat()
        updated_at = created_at

        # 构建字段列表（包含必填字段）
        all_fields = {"record_date": record_date, "record_time": record_time, 
                      "created_at": created_at, "updated_at": updated_at}
        all_fields.update({k: v for k, v in fields.items() if v is not None})

        field_names = ", ".join(all_fields.keys())
        placeholders = ", ".join("?" * len(all_fields))
        values = tuple(all_fields.values())

        with self._conn() as conn:
            cursor = conn.execute(f"""
                INSERT INTO health_records ({field_names})
                VALUES ({placeholders})
            """, values)
            conn.commit()
            record_id = cursor.lastrowid

        # 构建输出
        output_parts = [f"✅ 健康数据已记录！(ID: {record_id})"]
        output_parts.append(f"📅 {record_date} {record_time}")

        if fields.get("weight") and fields.get("height"):
            output_parts.append(f"⚖️ 体重: {fields['weight']/10} kg | 身高: {fields['height']} cm → BMI: {bmi}")

        if bp_systolic and bp_diastolic:
            output_parts.append(f"💓 血压: {bp_systolic}/{bp_diastolic} mmHg")

        if fields.get("heart_rate"):
            output_parts.append(f"❤️ 心率: {fields['heart_rate']} bpm")

        if fields.get("body_temp"):
            output_parts.append(f"🌡️ 体温: {fields['body_temp']/10} °C")

        if fields.get("blood_oxygen"):
            output_parts.append(f"🩸 血氧: {fields['blood_oxygen']}%")

        if fields.get("blood_glucose"):
            output_parts.append(f"🧪 血糖: {fields['blood_glucose']/10} mmol/L")

        if fields.get("steps"):
            output_parts.append(f"👟 步数: {fields['steps']} 步")

        if fields.get("sleep_hours"):
            output_parts.append(f"😴 睡眠: {fields['sleep_hours']/10} 小时")

        if fields.get("water_intake"):
            output_parts.append(f"💧 饮水: {fields['water_intake']} ml")

        if mood:
            mood_icon = _MOOD_ICONS.get(mood, "")
            output_parts.append(f"{mood_icon} 心情: {mood}")

        if fields.get("energy_level"):
            output_parts.append(f"⚡ 精力: {fields['energy_level']}/10")

        if warnings:
            output_parts.append("")
            output_parts.extend(warnings)

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(output_parts),
            data={
                "record_id": record_id,
                "date": record_date,
                "time": record_time,
                "bmi": bmi,
                "warnings": warnings,
            },
        )

    def _update_health_data(self, params: dict[str, Any]) -> ToolResult:
        record_id = params.get("record_id")
        if not record_id:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少 record_id")

        # 查找记录
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM health_records WHERE id = ?",
                (record_id,)
            ).fetchone()
            if not row:
                return ToolResult(status=ToolResultStatus.ERROR, error=f"记录不存在: ID {record_id}")

        # 构建更新字段
        updates = {}
        fields_map = {
            "height": lambda v: v,
            "weight": self._to_cents,
            "body_fat": self._to_cents,
            "steps": lambda v: v,
            "sleep_hours": self._to_cents,
            "water_intake": lambda v: v,
            "heart_rate": lambda v: v,
            "blood_oxygen": lambda v: v,
            "energy_level": lambda v: v,
            "notes": lambda v: v if v else None,
        }

        # 血压处理
        bp_systolic = params.get("bp_systolic")
        bp_diastolic = params.get("bp_diastolic")
        if bp_systolic is not None or bp_diastolic is not None:
            if bp_systolic is None or bp_diastolic is None:
                return ToolResult(status=ToolResultStatus.ERROR, error="血压需同时填写收缩压和舒张压")
            updates["bp_systolic"] = bp_systolic
            updates["bp_diastolic"] = bp_diastolic

        # 解析字符串血压
        bp_str = params.get("blood_pressure", "").strip()
        if bp_str and not updates:
            parsed = self._parse_bp(bp_str)
            if parsed:
                updates["bp_systolic"], updates["bp_diastolic"] = parsed

        # 心情校验
        mood = params.get("mood", "").strip() or None
        if mood and mood not in _VALID_MOODS:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"心情值无效，可选: {', '.join(sorted(_VALID_MOODS))}"
            )
        if mood:
            updates["mood"] = mood

        # 处理其他字段
        for key, converter in fields_map.items():
            if key in params and params[key] is not None:
                updates[key] = converter(params[key])

        if "date" in params and params["date"]:
            updates["record_date"] = params["date"]
        if "time" in params and params["time"]:
            updates["record_time"] = params["time"]

        if not updates:
            return ToolResult(status=ToolResultStatus.ERROR, error="没有可更新的字段")

        updates["updated_at"] = datetime.now().isoformat()

        # 执行更新
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [record_id]

        with self._conn() as conn:
            conn.execute(f"UPDATE health_records SET {set_clause} WHERE id = ?", values)
            conn.commit()

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"✅ 已更新健康记录 ID: {record_id}",
            data={"record_id": record_id, "updated_fields": list(updates.keys())},
        )

    def _delete_health_data(self, params: dict[str, Any]) -> ToolResult:
        record_id = params.get("record_id")
        if not record_id:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少 record_id")

        with self._conn() as conn:
            # 查找记录
            row = conn.execute(
                "SELECT record_date, record_time FROM health_records WHERE id = ?",
                (record_id,)
            ).fetchone()
            if not row:
                return ToolResult(status=ToolResultStatus.ERROR, error=f"记录不存在: ID {record_id}")

            # 删除
            conn.execute("DELETE FROM health_records WHERE id = ?", (record_id,))
            conn.commit()

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"✅ 已删除健康记录 ID: {record_id} ({row[0]} {row[1]})",
            data={"record_id": record_id, "deleted": True},
        )

    def _query_health_data(self, params: dict[str, Any]) -> ToolResult:
        date_range = params.get("date_range", "today")
        start_date = params.get("start_date", "").strip()
        end_date = params.get("end_date", "").strip()
        metric = params.get("metric", "").strip()
        limit = min(params.get("limit", 20), 100)

        start, end = self._get_date_range(date_range, start_date, end_date)

        # 构建查询
        if metric:
            col_map = {
                "weight": "weight",
                "height": "height",
                "body_fat": "body_fat",
                "blood_pressure": ("bp_systolic", "bp_diastolic"),
                "bp_systolic": "bp_systolic",
                "bp_diastolic": "bp_diastolic",
                "heart_rate": "heart_rate",
                "body_temp": "body_temp",
                "blood_oxygen": "blood_oxygen",
                "blood_glucose": "blood_glucose",
                "steps": "steps",
                "sleep_hours": "sleep_hours",
                "water_intake": "water_intake",
                "mood": "mood",
                "energy_level": "energy_level",
            }
            col = col_map.get(metric)
            if not col:
                return ToolResult(status=ToolResultStatus.ERROR, error=f"未知指标: {metric}")

            if isinstance(col, tuple):
                where_clause = f"(bp_systolic IS NOT NULL OR bp_diastolic IS NOT NULL)"
            else:
                where_clause = f"{col} IS NOT NULL"
        else:
            where_clause = "1=1"

        sql = f"""
            SELECT * FROM health_records
            WHERE record_date >= ? AND record_date <= ?
            AND {where_clause}
            ORDER BY record_date DESC, record_time DESC, id DESC
            LIMIT ?
        """
        with self._conn() as conn:
            rows = conn.execute(sql, (start, end, limit)).fetchall()

        if not rows:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="未找到符合条件的健康记录。",
                data={"records": [], "count": 0},
            )

        # 构建输出
        output_lines = [f"📊 健康数据 ({len(rows)} 条):"]
        data_list = []

        for row in rows:
            r = dict(zip([
                "id", "record_date", "record_time", "height", "weight", "body_fat",
                "bp_systolic", "bp_diastolic", "heart_rate", "body_temp",
                "blood_oxygen", "blood_glucose", "steps", "sleep_hours",
                "water_intake", "mood", "energy_level", "notes", "created_at", "updated_at"
            ], row))

            line_parts = [f"  📅 {r['record_date']} {r['record_time']} (ID:{r['id']})"]

            if r["weight"] and r["height"]:
                bmi = self._calculate_bmi(r["weight"], r["height"])
                line_parts.append(f"⚖️ {r['weight']/10}kg BMI:{bmi}")
            if r["bp_systolic"] and r["bp_diastolic"]:
                line_parts.append(f"💓 {r['bp_systolic']}/{r['bp_diastolic']}")
            if r["heart_rate"]:
                line_parts.append(f"❤️ {r['heart_rate']}")
            if r["body_temp"]:
                line_parts.append(f"🌡️ {r['body_temp']/10}°C")
            if r["blood_oxygen"]:
                line_parts.append(f"🩸 {r['blood_oxygen']}%")
            if r["blood_glucose"]:
                line_parts.append(f"🧪 {r['blood_glucose']/10}")
            if r["steps"]:
                line_parts.append(f"👟 {r['steps']}步")
            if r["sleep_hours"]:
                line_parts.append(f"😴 {r['sleep_hours']/10}h")
            if r["water_intake"]:
                line_parts.append(f"💧 {r['water_intake']}ml")
            if r["mood"]:
                line_parts.append(f"{_MOOD_ICONS.get(r['mood'], '')}{r['mood']}")
            if r["energy_level"]:
                line_parts.append(f"⚡{r['energy_level']}/10")

            output_lines.append(" | ".join(line_parts))
            data_list.append(r)

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(output_lines),
            data={"records": data_list, "count": len(data_list)},
        )

    def _get_health_trends(self, params: dict[str, Any]) -> ToolResult:
        metric = params.get("metric", "").strip()
        if not metric:
            return ToolResult(status=ToolResultStatus.ERROR, error="请指定要分析的指标")

        period = params.get("period", "month")
        start_date = params.get("start_date", "").strip()
        end_date = params.get("end_date", "").strip()

        # 计算日期范围
        today = datetime.now().strftime("%Y-%m-%d")
        if start_date and end_date:
            start, end = start_date, end_date
        elif period == "week":
            start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            end = today
        elif period == "month":
            start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            end = today
        elif period == "quarter":
            start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            end = today
        elif period == "year":
            start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            end = today
        else:
            start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            end = today

        # 列名映射
        col_map = {
            "weight": "weight",
            "height": "height",
            "body_fat": "body_fat",
            "blood_pressure": ("bp_systolic", "bp_diastolic"),
            "heart_rate": "heart_rate",
            "body_temp": "body_temp",
            "blood_oxygen": "blood_oxygen",
            "blood_glucose": "blood_glucose",
            "steps": "steps",
            "sleep_hours": "sleep_hours",
            "water_intake": "water_intake",
        }

        col = col_map.get(metric)
        if not col:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"不支持分析该指标: {metric}")

        # 查询数据
        if isinstance(col, tuple):
            sql = f"""
                SELECT record_date, {col[0]}, {col[1]}
                FROM health_records
                WHERE record_date >= ? AND record_date <= ?
                AND ({col[0]} IS NOT NULL OR {col[1]} IS NOT NULL)
                ORDER BY record_date ASC
            """
            with self._conn() as conn:
                rows = conn.execute(sql, (start, end)).fetchall()

            # 转换为数据点
            data_points = {}
            for r in rows:
                date, sys, dia = r
                if sys or dia:
                    data_points[date] = (sys, dia)

            # 输出
            if not data_points:
                return ToolResult(status=ToolResultStatus.SUCCESS,
                    output=f"📈 {metric} 趋势 ({start} ~ {end}):\n该时段无记录。",
                    data={"metric": metric, "data": {}})

            output_lines = [f"📈 血压趋势 ({start} ~ {end}):"]
            values = []
            for date in sorted(data_points.keys()):
                sys, dia = data_points[date]
                if sys and dia:
                    output_lines.append(f"  {date[-5:]}: {sys}/{dia} mmHg")
                    values.append(sys)
                    values.append(dia)

        else:
            sql = f"""
                SELECT record_date, {col}
                FROM health_records
                WHERE record_date >= ? AND record_date <= ?
                AND {col} IS NOT NULL
                ORDER BY record_date ASC
            """
            with self._conn() as conn:
                rows = conn.execute(sql, (start, end)).fetchall()

            # 按天聚合（取每天最新值）
            daily = {}
            for r in rows:
                date, val = r
                if val is not None:
                    daily[date] = val  # 已有就是最新的（ORDER BY ASC）

            if not daily:
                return ToolResult(status=ToolResultStatus.SUCCESS,
                    output=f"📈 {metric} 趋势 ({start} ~ {end}):\n该时段无记录。",
                    data={"metric": metric, "data": {}})

            output_lines = [f"📈 {metric} 趋势 ({start} ~ {end}):"]
            values = []
            for date in sorted(daily.keys()):
                val = daily[date]
                # 单位转换显示
                if metric in ("weight", "body_fat", "body_temp", "blood_glucose", "sleep_hours"):
                    display = f"{val/10}"
                else:
                    display = str(val)
                output_lines.append(f"  {date[-5:]}: {display}")
                values.append(val)

            # 统计
            if values:
                min_val = min(values)
                max_val = max(values)
                avg_val = sum(values) / len(values)
                change = values[-1] - values[0] if len(values) > 1 else 0

                unit = ""
                if metric == "weight":
                    unit = "kg"
                elif metric == "body_temp":
                    unit = "°C"
                elif metric == "blood_glucose":
                    unit = "mmol/L"
                elif metric == "sleep_hours":
                    unit = "h"

                output_lines.append(f"\n📊 统计: 最高 {min_val/10 if metric in ('weight','body_fat','body_temp','blood_glucose','sleep_hours') else min_val}{unit} | 最低 {max_val/10 if metric in ('weight','body_fat','body_temp','blood_glucose','sleep_hours') else max_val}{unit} | 平均 {round(avg_val/10 if metric in ('weight','body_fat','body_temp','blood_glucose','sleep_hours') else avg_val, 1)}{unit}")

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(output_lines),
            data={"metric": metric, "start": start, "end": end, "data": daily if not isinstance(col, tuple) else data_points},
        )
