"""Diary 工具 — 日记管理（CRUD）。

支持动作：
- write_diary: 写日记（含心情、天气、标签）
- query_diary: 查询日记（按时间范围/关键词/心情筛选）
- update_diary: 更新日记内容
- delete_diary: 删除日记

借鉴来源：参考项目_changoai/backend/tool_functions.py diary 相关函数
存储位置：~/.winclaw/winclaw_tools.db（diaries 表）
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".winclaw" / "winclaw_tools.db"

_MOOD_ICONS = {
    "happy": "😊", "sad": "😢", "neutral": "😐",
    "excited": "🤩", "anxious": "😰", "calm": "😌", "stressed": "😫",
}
_WEATHER_ICONS = {
    "sunny": "☀️", "cloudy": "☁️", "rainy": "🌧️", "snowy": "❄️",
    "windy": "🌬️", "foggy": "🌫️",
}


class DiaryTool(BaseTool):
    """日记管理工具。

    支持日记的创建、查询、更新、删除，
    每篇日记可附加心情、天气和自定义标签。
    数据存储到 ~/.winclaw/winclaw_tools.db 的 diaries 表。
    """

    name = "diary"
    emoji = "📔"
    title = "日记管理"
    description = "写日记、查询日记、更新和删除日记，支持心情/天气/标签"

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
                CREATE TABLE IF NOT EXISTS diaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    diary_date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    mood TEXT,
                    weather TEXT,
                    tags TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_diaries_date
                ON diaries(diary_date DESC)
            """)
            conn.commit()

    # ------------------------------------------------------------------

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="write_diary",
                description="写日记。自动以今天日期归档，支持心情/天气/标签。",
                parameters={
                    "title": {
                        "type": "string",
                        "description": "日记标题",
                    },
                    "content": {
                        "type": "string",
                        "description": "日记正文",
                    },
                    "mood": {
                        "type": "string",
                        "description": "心情: happy/sad/neutral/excited/anxious/calm/stressed（可选）",
                    },
                    "weather": {
                        "type": "string",
                        "description": "天气: sunny/cloudy/rainy/snowy/windy/foggy（可选）",
                    },
                    "tags": {
                        "type": "string",
                        "description": "标签，多个用逗号分隔（可选）",
                    },
                },
                required_params=["title", "content"],
            ),
            ActionDef(
                name="query_diary",
                description="查询日记，支持按时间范围、关键词、心情筛选",
                parameters={
                    "date_range": {
                        "type": "string",
                        "description": "时间范围: today/week/month/year/all，默认 all",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词（可选）",
                    },
                    "mood": {
                        "type": "string",
                        "description": "按心情筛选（可选）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量，默认 10",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="update_diary",
                description="更新日记内容",
                parameters={
                    "diary_id": {
                        "type": "integer",
                        "description": "日记 ID",
                    },
                    "title": {
                        "type": "string",
                        "description": "新标题（可选）",
                    },
                    "content": {
                        "type": "string",
                        "description": "新正文（可选）",
                    },
                    "mood": {
                        "type": "string",
                        "description": "新心情（可选）",
                    },
                },
                required_params=["diary_id"],
            ),
            ActionDef(
                name="delete_diary",
                description="删除日记",
                parameters={
                    "diary_id": {
                        "type": "integer",
                        "description": "日记 ID",
                    },
                },
                required_params=["diary_id"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "write_diary": self._write_diary,
            "query_diary": self._query_diary,
            "update_diary": self._update_diary,
            "delete_diary": self._delete_diary,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"不支持的动作: {action}")
        try:
            return handler(params)
        except Exception as e:
            logger.error("日记操作失败: %s", e)
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))

    # ------------------------------------------------------------------

    def _write_diary(self, params: dict[str, Any]) -> ToolResult:
        title = params.get("title", "").strip()
        content = params.get("content", "").strip()
        mood = params.get("mood", "")
        weather = params.get("weather", "")
        tags_str = params.get("tags", "")

        if not title or not content:
            return ToolResult(status=ToolResultStatus.ERROR, error="标题和内容不能为空")

        tags_list = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT INTO diaries (diary_date, title, content, mood, weather, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                today, title, content,
                mood or None, weather or None,
                json.dumps(tags_list, ensure_ascii=False),
                now.isoformat(), now.isoformat(),
            ))
            conn.commit()
            diary_id = cursor.lastrowid

        mood_icon = _MOOD_ICONS.get(mood, "")
        weather_icon = _WEATHER_ICONS.get(weather, "")

        output = f"日记已保存！(ID: {diary_id})\n📅 {today} | 📝 {title}"
        if mood:
            output += f"\n{mood_icon} 心情: {mood}"
        if weather:
            output += f"\n{weather_icon} 天气: {weather}"
        if tags_list:
            output += f"\n🏷️ 标签: {', '.join(tags_list)}"

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={
                "diary_id": diary_id, "date": today, "title": title,
                "mood": mood or None, "weather": weather or None,
                "tags": tags_list,
            },
        )

    def _query_diary(self, params: dict[str, Any]) -> ToolResult:
        date_range = params.get("date_range", "all")
        keyword = params.get("keyword", "")
        mood = params.get("mood", "")
        limit = min(params.get("limit", 10), 50)

        clauses: list[str] = []
        values: list[Any] = []

        today = datetime.now()
        if date_range == "today":
            clauses.append("diary_date = ?")
            values.append(today.strftime("%Y-%m-%d"))
        elif date_range == "week":
            clauses.append("diary_date >= ?")
            values.append((today - timedelta(days=7)).strftime("%Y-%m-%d"))
        elif date_range == "month":
            clauses.append("diary_date >= ?")
            values.append((today - timedelta(days=30)).strftime("%Y-%m-%d"))
        elif date_range == "year":
            clauses.append("diary_date >= ?")
            values.append((today - timedelta(days=365)).strftime("%Y-%m-%d"))

        if keyword:
            clauses.append("(title LIKE ? OR content LIKE ?)")
            values.extend([f"%{keyword}%", f"%{keyword}%"])
        if mood:
            clauses.append("mood = ?")
            values.append(mood)

        where = " AND ".join(clauses) if clauses else "1=1"
        sql = (
            f"SELECT id, diary_date, title, content, mood, weather, tags, created_at "
            f"FROM diaries WHERE {where} ORDER BY diary_date DESC LIMIT ?"
        )
        values.append(limit)

        with self._conn() as conn:
            rows = conn.execute(sql, values).fetchall()

        if not rows:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="未找到符合条件的日记。",
                data={"diaries": [], "count": 0},
            )

        lines = [f"找到 {len(rows)} 篇日记："]
        data_list = []
        for i, row in enumerate(rows, 1):
            did, ddate, dtitle, dcontent, dmood, dweather, dtags, dcreated = row
            mood_icon = _MOOD_ICONS.get(dmood or "", "")
            preview = dcontent[:80] + ("..." if len(dcontent) > 80 else "")
            lines.append(f"  {i}. 📝 {dtitle} (ID:{did})")
            lines.append(f"      📅 {ddate} {mood_icon}{dmood or ''}")
            lines.append(f"      💭 {preview}")
            data_list.append({
                "id": did, "date": ddate, "title": dtitle,
                "content_preview": preview, "mood": dmood, "weather": dweather,
            })

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={"diaries": data_list, "count": len(data_list)},
        )

    def _update_diary(self, params: dict[str, Any]) -> ToolResult:
        diary_id = params.get("diary_id")
        if diary_id is None:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少 diary_id")

        updates: dict[str, Any] = {}
        for key in ("title", "content", "mood"):
            if key in params and params[key]:
                updates[key] = params[key]
        if not updates:
            return ToolResult(status=ToolResultStatus.ERROR, error="没有可更新的字段")

        updates["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [diary_id]

        with self._conn() as conn:
            cursor = conn.execute(f"UPDATE diaries SET {set_clause} WHERE id = ?", values)
            conn.commit()
            if cursor.rowcount == 0:
                return ToolResult(status=ToolResultStatus.ERROR, error=f"日记不存在: ID {diary_id}")

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已更新日记 ID:{diary_id}",
            data={"diary_id": diary_id, "updated_fields": list(updates.keys())},
        )

    def _delete_diary(self, params: dict[str, Any]) -> ToolResult:
        diary_id = params.get("diary_id")
        if diary_id is None:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少 diary_id")

        with self._conn() as conn:
            # 获取信息
            row = conn.execute("SELECT title, diary_date FROM diaries WHERE id = ?", (diary_id,)).fetchone()
            if not row:
                return ToolResult(status=ToolResultStatus.ERROR, error=f"日记不存在: ID {diary_id}")
            title, ddate = row
            conn.execute("DELETE FROM diaries WHERE id = ?", (diary_id,))
            conn.commit()

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已删除日记: {title} ({ddate})",
            data={"diary_id": diary_id, "deleted": True},
        )
