"""Statistics 工具 — 使用统计查询。

支持动作：
- get_usage_stats: 获取使用统计信息（对话数、消息数、工具使用次数等）

借鉴来源：参考项目_changoai/backend/tool_functions.py get_my_statistics()
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

# 默认对话历史数据库路径（与 core/storage.py 一致）
_DEFAULT_HISTORY_DB = Path.home() / ".winclaw" / "history.db"


class StatisticsTool(BaseTool):
    """使用统计工具。

    从 WinClaw 的对话历史数据库中读取统计信息，
    包括会话数、消息数、使用的模型分布等。
    只读操作，不修改数据。
    """

    name = "statistics"
    emoji = "📊"
    title = "使用统计"
    description = "获取 WinClaw 使用统计信息（对话数、消息数等）"

    def __init__(self, db_path: str = ""):
        self._db_path = Path(db_path) if db_path else _DEFAULT_HISTORY_DB

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="get_usage_stats",
                description=(
                    "获取 WinClaw 使用统计信息，包括总会话数、总消息数、"
                    "最近活跃时间、使用的模型分布等。"
                ),
                parameters={
                    "period": {
                        "type": "string",
                        "description": "统计周期: 'all'(全部), 'today'(今天), 'week'(最近7天), 'month'(最近30天)",
                        "enum": ["all", "today", "week", "month"],
                    },
                },
                required_params=[],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        if action != "get_usage_stats":
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return self._get_usage_stats(params)

    def _get_usage_stats(self, params: dict[str, Any]) -> ToolResult:
        period = params.get("period", "all").strip()

        if not self._db_path.exists():
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="暂无使用数据（数据库尚未创建）。",
                data={"session_count": 0, "message_count": 0},
            )

        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row

            # 计算时间范围过滤条件
            time_filter = ""
            period_text = "全部"
            if period == "today":
                time_filter = f"AND created_at >= '{datetime.now().strftime('%Y-%m-%d')}'"
                period_text = "今天"
            elif period == "week":
                from datetime import timedelta
                week_ago = (datetime.now() - timedelta(days=7)).isoformat()
                time_filter = f"AND created_at >= '{week_ago}'"
                period_text = "最近 7 天"
            elif period == "month":
                from datetime import timedelta
                month_ago = (datetime.now() - timedelta(days=30)).isoformat()
                time_filter = f"AND created_at >= '{month_ago}'"
                period_text = "最近 30 天"

            # 会话统计
            session_count = conn.execute(
                f"SELECT COUNT(*) FROM sessions WHERE 1=1 {time_filter}"
            ).fetchone()[0]

            # 消息统计
            msg_filter = time_filter.replace("created_at", "m.created_at") if time_filter else ""
            message_count = conn.execute(
                f"SELECT COUNT(*) FROM messages m WHERE 1=1 {msg_filter}"
            ).fetchone()[0]

            # 用户消息数
            user_msg_count = conn.execute(
                f"SELECT COUNT(*) FROM messages m WHERE m.role = 'user' {msg_filter}"
            ).fetchone()[0]

            # AI 消息数
            ai_msg_count = conn.execute(
                f"SELECT COUNT(*) FROM messages m WHERE m.role = 'assistant' {msg_filter}"
            ).fetchone()[0]

            # 工具调用数
            tool_msg_count = conn.execute(
                f"SELECT COUNT(*) FROM messages m WHERE m.role = 'tool' {msg_filter}"
            ).fetchone()[0]

            # 模型使用分布（全量统计）
            model_rows = conn.execute(
                "SELECT model_key, COUNT(*) as cnt FROM sessions "
                "WHERE model_key != '' GROUP BY model_key ORDER BY cnt DESC LIMIT 5"
            ).fetchall()

            # 最近会话
            recent = conn.execute(
                "SELECT title, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 3"
            ).fetchall()

            # 总 token
            total_tokens = conn.execute(
                "SELECT COALESCE(SUM(total_tokens), 0) FROM sessions"
            ).fetchone()[0]

            conn.close()

            # 格式化输出
            lines = [f"使用统计（{period_text}）\n"]
            lines.append(f"会话总数: {session_count} 个")
            lines.append(f"消息总数: {message_count} 条")
            lines.append(f"  用户消息: {user_msg_count} 条")
            lines.append(f"  AI 回复: {ai_msg_count} 条")
            lines.append(f"  工具调用: {tool_msg_count} 次")
            if total_tokens > 0:
                lines.append(f"消耗 Token: {total_tokens:,}")

            if model_rows:
                lines.append("\n模型使用分布:")
                for row in model_rows:
                    lines.append(f"  {row[0]}: {row[1]} 次")

            if recent:
                lines.append("\n最近会话:")
                for row in recent:
                    lines.append(f"  {row[0]} ({row[1][:10]})")

            output = "\n".join(lines)
            data = {
                "period": period,
                "session_count": session_count,
                "message_count": message_count,
                "user_message_count": user_msg_count,
                "ai_message_count": ai_msg_count,
                "tool_call_count": tool_msg_count,
                "total_tokens": total_tokens,
            }

            logger.info("获取使用统计: period=%s, sessions=%d", period, session_count)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=output,
                data=data,
            )
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"获取统计信息失败: {e}",
            )
