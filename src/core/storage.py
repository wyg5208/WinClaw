"""对话历史持久化存储 — 基于 SQLite 的异步存储。

Phase 4.4 实现：
- 异步 SQLite 存储（aiosqlite）
- 会话元数据管理
- 消息历史存储
- 搜索与导出功能
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认数据库路径
DEFAULT_DB_PATH = Path.home() / ".winclaw" / "history.db"


@dataclass
class StoredSession:
    """存储的会话元数据。"""
    id: str
    title: str = "新对话"
    model_key: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    total_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "model_key": self.model_key,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "total_tokens": self.total_tokens,
            "metadata": self.metadata,
        }


@dataclass
class StoredMessage:
    """存储的消息。"""
    id: int | None
    session_id: str
    role: str
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result


class ChatStorage:
    """异步对话存储。"""

    def __init__(self, db_path: Path | str | None = None):
        """初始化存储。

        Args:
            db_path: 数据库文件路径，默认 ~/.winclaw/history.db
        """
        self._db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def _ensure_tables(self) -> None:
        """确保数据库表已创建。"""
        if self._initialized:
            return

        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            # 会话表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '新对话',
                    model_key TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    total_tokens INTEGER DEFAULT 0,
                    metadata_json TEXT DEFAULT '{}'
                )
            """)
            # 消息表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls_json TEXT,
                    tool_call_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)
            # 索引
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session_id
                ON messages(session_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
                ON sessions(updated_at DESC)
            """)
            await db.commit()

        self._initialized = True
        logger.info("数据库初始化完成: %s", self._db_path)

    async def save_session(self, session: StoredSession) -> None:
        """保存会话元数据。"""
        await self._ensure_tables()
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO sessions
                (id, title, model_key, created_at, updated_at, total_tokens, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session.id,
                session.title,
                session.model_key,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
                session.total_tokens,
                json.dumps(session.metadata, ensure_ascii=False),
            ))
            await db.commit()
        logger.debug("保存会话: %s", session.id)

    async def load_session(self, session_id: str) -> StoredSession | None:
        """加载会话元数据。"""
        await self._ensure_tables()
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("""
                SELECT id, title, model_key, created_at, updated_at, total_tokens, metadata_json
                FROM sessions WHERE id = ?
            """, (session_id,)) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return StoredSession(
                    id=row[0],
                    title=row[1],
                    model_key=row[2],
                    created_at=datetime.fromisoformat(row[3]),
                    updated_at=datetime.fromisoformat(row[4]),
                    total_tokens=row[5],
                    metadata=json.loads(row[6]),
                )

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> list[StoredSession]:
        """列出会话（按更新时间降序）。"""
        await self._ensure_tables()
        import aiosqlite

        sessions = []
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("""
                SELECT id, title, model_key, created_at, updated_at, total_tokens, metadata_json
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset)) as cursor:
                async for row in cursor:
                    sessions.append(StoredSession(
                        id=row[0],
                        title=row[1],
                        model_key=row[2],
                        created_at=datetime.fromisoformat(row[3]),
                        updated_at=datetime.fromisoformat(row[4]),
                        total_tokens=row[5],
                        metadata=json.loads(row[6]),
                    ))
        return sessions

    async def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有消息。"""
        await self._ensure_tables()
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            # 开启外键约束
            await db.execute("PRAGMA foreign_keys = ON")
            cursor = await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await db.commit()
            deleted = cursor.rowcount > 0
        if deleted:
            logger.info("删除会话: %s", session_id)
        return deleted

    async def save_message(self, message: StoredMessage) -> int:
        """保存消息，返回消息ID。"""
        await self._ensure_tables()
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("""
                INSERT INTO messages
                (session_id, role, content, tool_calls_json, tool_call_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                message.session_id,
                message.role,
                message.content,
                json.dumps(message.tool_calls, ensure_ascii=False) if message.tool_calls else None,
                message.tool_call_id,
                message.created_at.isoformat(),
            ))
            await db.commit()
            message.id = cursor.lastrowid

            # 更新会话的 updated_at
            await db.execute("""
                UPDATE sessions SET updated_at = ? WHERE id = ?
            """, (datetime.now().isoformat(), message.session_id))
            await db.commit()

        return message.id or 0

    async def load_messages(self, session_id: str) -> list[StoredMessage]:
        """加载会话的所有消息。"""
        await self._ensure_tables()
        import aiosqlite

        messages = []
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("""
                SELECT id, session_id, role, content, tool_calls_json, tool_call_id, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
            """, (session_id,)) as cursor:
                async for row in cursor:
                    messages.append(StoredMessage(
                        id=row[0],
                        session_id=row[1],
                        role=row[2],
                        content=row[3],
                        tool_calls=json.loads(row[4]) if row[4] else None,
                        tool_call_id=row[5],
                        created_at=datetime.fromisoformat(row[6]),
                    ))
        return messages

    async def search_messages(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """搜索消息内容。"""
        await self._ensure_tables()
        import aiosqlite

        results = []
        search_pattern = f"%{query}%"
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("""
                SELECT m.session_id, m.role, m.content, s.title, s.updated_at
                FROM messages m
                JOIN sessions s ON m.session_id = s.id
                WHERE m.content LIKE ?
                ORDER BY s.updated_at DESC
                LIMIT ?
            """, (search_pattern, limit)) as cursor:
                async for row in cursor:
                    results.append({
                        "session_id": row[0],
                        "role": row[1],
                        "content": row[2][:200] + "..." if len(row[2]) > 200 else row[2],
                        "session_title": row[3],
                        "updated_at": row[4],
                    })
        return results

    async def export_session(self, session_id: str, format: str = "markdown") -> str:
        """导出会话为指定格式。"""
        session = await self.load_session(session_id)
        if session is None:
            return ""

        messages = await self.load_messages(session_id)

        if format == "json":
            export_data = {
                "session": session.to_dict(),
                "messages": [m.to_dict() for m in messages],
            }
            return json.dumps(export_data, ensure_ascii=False, indent=2)

        # Markdown 格式
        lines = [
            f"# {session.title}",
            f"",
            f"> 创建时间: {session.created_at.strftime('%Y-%m-%d %H:%M')}",
            f"> 模型: {session.model_key or '未指定'}",
            f"",
            "---",
            "",
        ]

        for msg in messages:
            role_label = {
                "system": "⚙️ System",
                "user": "👤 User",
                "assistant": "🤖 Assistant",
                "tool": "🔧 Tool",
            }.get(msg.role, msg.role)

            lines.append(f"### {role_label}")
            lines.append("")
            lines.append(msg.content)
            lines.append("")

        return "\n".join(lines)

    async def update_session_title(self, session_id: str, title: str) -> None:
        """更新会话标题。"""
        await self._ensure_tables()
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?
            """, (title, datetime.now().isoformat(), session_id))
            await db.commit()

    async def get_session_count(self) -> int:
        """获取会话总数。"""
        await self._ensure_tables()
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM sessions") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    # ------------------------------------------------------------------
    # 同步读取方法（供 Qt 主线程直接调用，避免 asyncio 死锁）
    # ------------------------------------------------------------------

    def _ensure_tables_sync(self) -> None:
        """同步确保数据库表已创建。"""
        if self._initialized:
            return
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '新对话',
                    model_key TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    total_tokens INTEGER DEFAULT 0,
                    metadata_json TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls_json TEXT,
                    tool_call_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session_id
                ON messages(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
                ON sessions(updated_at DESC)
            """)
            conn.commit()
        finally:
            conn.close()
        self._initialized = True

    def list_sessions_sync(self, limit: int = 50, offset: int = 0) -> list[StoredSession]:
        """同步列出会话（按更新时间降序）。

        使用标准 sqlite3，安全地在 Qt 主线程中调用。
        """
        self._ensure_tables_sync()
        sessions = []
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute("""
                SELECT id, title, model_key, created_at, updated_at, total_tokens, metadata_json
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            for row in cursor:
                sessions.append(StoredSession(
                    id=row[0],
                    title=row[1],
                    model_key=row[2],
                    created_at=datetime.fromisoformat(row[3]),
                    updated_at=datetime.fromisoformat(row[4]),
                    total_tokens=row[5],
                    metadata=json.loads(row[6]),
                ))
        finally:
            conn.close()
        return sessions

    def load_session_sync(self, session_id: str) -> StoredSession | None:
        """同步加载会话元数据。"""
        self._ensure_tables_sync()
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute("""
                SELECT id, title, model_key, created_at, updated_at, total_tokens, metadata_json
                FROM sessions WHERE id = ?
            """, (session_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return StoredSession(
                id=row[0],
                title=row[1],
                model_key=row[2],
                created_at=datetime.fromisoformat(row[3]),
                updated_at=datetime.fromisoformat(row[4]),
                total_tokens=row[5],
                metadata=json.loads(row[6]),
            )
        finally:
            conn.close()

    def load_messages_sync(self, session_id: str) -> list[StoredMessage]:
        """同步加载会话的所有消息。"""
        self._ensure_tables_sync()
        messages = []
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute("""
                SELECT id, session_id, role, content, tool_calls_json, tool_call_id, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
            """, (session_id,))
            for row in cursor:
                messages.append(StoredMessage(
                    id=row[0],
                    session_id=row[1],
                    role=row[2],
                    content=row[3],
                    tool_calls=json.loads(row[4]) if row[4] else None,
                    tool_call_id=row[5],
                    created_at=datetime.fromisoformat(row[6]),
                ))
        finally:
            conn.close()
        return messages

    def get_message_count_sync(self, session_id: str) -> int:
        """同步获取会话的消息数量。"""
        self._ensure_tables_sync()
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM messages
                WHERE session_id = ? AND role IN ('user', 'assistant')
            """, (session_id,))
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()
