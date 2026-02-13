"""ChatHistory 工具 — 搜索和浏览聊天历史记录。

支持动作：
- search_history: 按关键词搜索历史对话消息
- get_recent_sessions: 获取最近的会话列表

借鉴来源：参考项目_changoai/backend/tool_functions.py search_chat_history()
复用底层：core/storage.py ChatStorage（不新建数据库）
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


class ChatHistoryTool(BaseTool):
    """搜索聊天历史工具。

    直接复用 core/storage.py 的 ChatStorage 类，
    将其异步查询能力包装为 BaseTool 接口。
    不新建数据库，只读访问 ~/.winclaw/history.db。
    """

    name = "chat_history"
    emoji = "💬"
    title = "聊天历史"
    description = "搜索和浏览历史对话记录，支持关键词搜索和最近会话列表"

    def __init__(self, db_path: str = ""):
        """初始化聊天历史工具。

        Args:
            db_path: history.db 路径，为空时使用默认路径 ~/.winclaw/history.db
        """
        super().__init__()
        self._db_path = db_path or ""
        self._storage = None  # 延迟初始化

    def _get_storage(self):
        """延迟获取 ChatStorage 实例。"""
        if self._storage is None:
            from src.core.storage import ChatStorage
            if self._db_path:
                self._storage = ChatStorage(db_path=self._db_path)
            else:
                self._storage = ChatStorage()
        return self._storage

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="search_history",
                description=(
                    "按关键词搜索历史聊天记录。返回包含关键词的消息列表，"
                    "包括所属会话标题和时间。为空时返回最近的消息。"
                ),
                parameters={
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词（可选，为空时返回最近的对话记录）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量，默认 10，最大 50",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="get_recent_sessions",
                description=(
                    "获取最近的会话列表，按最后更新时间降序排列。"
                    "返回会话标题、模型、创建时间等信息。"
                ),
                parameters={
                    "limit": {
                        "type": "integer",
                        "description": "返回会话数量，默认 10，最大 50",
                    },
                },
                required_params=[],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "search_history": self._search_history,
            "get_recent_sessions": self._get_recent_sessions,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return await handler(params)

    async def _search_history(self, params: dict[str, Any]) -> ToolResult:
        """搜索聊天历史记录。"""
        keyword = params.get("keyword", "").strip()
        limit = min(params.get("limit", 10), 50)

        try:
            storage = self._get_storage()

            if not keyword or keyword in ("最近", "所有", "all", "recent"):
                # 无关键词 → 返回最近会话的消息概览
                sessions = await storage.list_sessions(limit=limit)
                if not sessions:
                    return ToolResult(
                        status=ToolResultStatus.SUCCESS,
                        output="暂无聊天记录。",
                        data={"results": [], "count": 0},
                    )

                lines = [f"最近 {len(sessions)} 个对话："]
                results = []
                for i, s in enumerate(sessions, 1):
                    updated = s.updated_at.strftime("%Y-%m-%d %H:%M")
                    lines.append(f"  {i}. 💬 {s.title}  ({updated})")
                    results.append({
                        "session_id": s.id,
                        "title": s.title,
                        "updated_at": updated,
                    })

                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output="\n".join(lines),
                    data={"results": results, "count": len(results)},
                )

            # 有关键词 → 搜索消息内容
            messages = await storage.search_messages(query=keyword, limit=limit)
            if not messages:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=f"未找到包含 '{keyword}' 的聊天记录。",
                    data={"results": [], "count": 0, "keyword": keyword},
                )

            lines = [f"找到 {len(messages)} 条包含 '{keyword}' 的记录："]
            for i, msg in enumerate(messages, 1):
                role_label = {"user": "👤", "assistant": "🤖", "tool": "🔧"}.get(
                    msg["role"], msg["role"]
                )
                content_preview = msg["content"][:120]
                if len(msg["content"]) > 120:
                    content_preview += "..."
                lines.append(
                    f"  {i}. {role_label} [{msg['session_title']}] {content_preview}"
                )

            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="\n".join(lines),
                data={"results": messages, "count": len(messages), "keyword": keyword},
            )

        except Exception as e:
            logger.error("搜索聊天历史失败: %s", e)
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"搜索聊天历史失败: {e}",
            )

    async def _get_recent_sessions(self, params: dict[str, Any]) -> ToolResult:
        """获取最近的会话列表。"""
        limit = min(params.get("limit", 10), 50)

        try:
            storage = self._get_storage()
            sessions = await storage.list_sessions(limit=limit)

            if not sessions:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output="暂无会话记录。",
                    data={"sessions": [], "count": 0},
                )

            lines = [f"最近 {len(sessions)} 个会话："]
            session_list = []
            for i, s in enumerate(sessions, 1):
                created = s.created_at.strftime("%Y-%m-%d %H:%M")
                updated = s.updated_at.strftime("%Y-%m-%d %H:%M")
                model = s.model_key or "未指定"
                lines.append(
                    f"  {i}. 💬 {s.title}\n"
                    f"      模型: {model} | 创建: {created} | 更新: {updated}"
                )
                session_list.append({
                    "session_id": s.id,
                    "title": s.title,
                    "model_key": model,
                    "created_at": created,
                    "updated_at": updated,
                    "total_tokens": s.total_tokens,
                })

            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="\n".join(lines),
                data={"sessions": session_list, "count": len(session_list)},
            )

        except Exception as e:
            logger.error("获取会话列表失败: %s", e)
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"获取会话列表失败: {e}",
            )
