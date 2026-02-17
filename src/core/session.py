"""会话管理器 — 管理对话历史、多会话切换、上下文窗口截断。

支持：
- 多会话管理（创建/切换/删除）
- 对话历史 messages 列表管理
- 上下文窗口自动截断（保留 system prompt + 最近消息）
- 会话元数据（标题、创建时间等）

Phase 4.4 增强：
- 持久化存储集成（可选）
- 自动保存消息到 SQLite
- 自动标题生成

Phase 4.7 增强：
- 智能截断：保留完整对话轮次（user+assistant 为一轮）
- tool_calls 完整性：不截断 tool_calls 和对应 tool 结果
- 消息数量硬上限：防止内存无限增长
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.storage import ChatStorage

logger = logging.getLogger(__name__)

# 默认最大消息数量硬上限
DEFAULT_MAX_MESSAGE_COUNT = 100


@dataclass
class Session:
    """单个对话会话。"""

    id: str
    title: str = "新对话"
    created_at: datetime = field(default_factory=datetime.now)
    messages: list[dict[str, Any]] = field(default_factory=list)
    model_key: str = ""  # 此会话使用的模型
    total_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def has_system_prompt(self) -> bool:
        return bool(self.messages) and self.messages[0].get("role") == "system"


class SessionManager:
    """会话管理器。

    用法::

        mgr = SessionManager(context_window=64000)
        session = mgr.create_session(title="测试对话")
        mgr.add_message(role="user", content="你好")
        messages = mgr.get_messages()  # 自动截断
    """

    def __init__(
        self,
        context_window: int = 64000,
        max_sessions: int = 50,
        system_prompt: str = "",
        max_message_count: int = DEFAULT_MAX_MESSAGE_COUNT,
        storage: ChatStorage | None = None,
    ):
        """
        Args:
            context_window: 上下文窗口大小（token 数估算用字符数/3近似）
            max_sessions: 最大会话数量
            system_prompt: 默认 system prompt
            max_message_count: 最大消息数量硬上限（防止内存无限增长）
            storage: 可选的持久化存储实例
        """
        self._sessions: dict[str, Session] = {}
        self._current_id: str = ""
        self._context_window = context_window
        self._max_sessions = max_sessions
        self._system_prompt = system_prompt
        self._max_message_count = max_message_count
        self._storage = storage

        # 自动创建第一个会话
        self.create_session(title="默认对话")

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------

    def create_session(self, title: str = "新对话", model_key: str = "") -> Session:
        """创建新会话并切换到它。"""
        session_id = str(uuid.uuid4())[:8]
        session = Session(id=session_id, title=title, model_key=model_key)

        # 自动添加 system prompt
        if self._system_prompt:
            session.messages.append({
                "role": "system",
                "content": self._system_prompt,
            })

        self._sessions[session_id] = session
        self._current_id = session_id

        # 清理过多的旧会话
        if len(self._sessions) > self._max_sessions:
            self._cleanup_oldest()

        logger.info("创建会话: %s (%s)", session_id, title)

        # 异步保存到存储（fire-and-forget）
        if self._storage:
            import asyncio
            from src.core.storage import StoredSession
            stored = StoredSession(
                id=session_id,
                title=title,
                model_key=model_key,
                created_at=session.created_at,
                updated_at=session.created_at,
            )
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._storage.save_session(stored))
                else:
                    loop.run_until_complete(self._storage.save_session(stored))
            except Exception as e:
                logger.warning("保存会话到存储失败: %s", e)

        return session

    def switch_session(self, session_id: str) -> Session:
        """切换到指定会话。"""
        if session_id not in self._sessions:
            raise ValueError(f"会话不存在: {session_id}")
        self._current_id = session_id
        logger.info("切换到会话: %s", session_id)
        return self._sessions[session_id]

    def delete_session(self, session_id: str) -> bool:
        """删除指定会话。"""
        if session_id not in self._sessions:
            return False

        del self._sessions[session_id]

        # 如果删除的是当前会话，切换到最近的
        if self._current_id == session_id:
            if self._sessions:
                self._current_id = list(self._sessions.keys())[-1]
            else:
                # 没有会话了，创建一个新的
                self.create_session()

        logger.info("删除会话: %s", session_id)
        return True

    def update_system_prompt(self, new_prompt: str) -> None:
        """更新当前会话的 System Prompt。

        用于动态构建 System Prompt，根据用户意图注入不同的扩展模块。

        Args:
            new_prompt: 新的 System Prompt 内容
        """
        session = self.current_session
        # 更新内部存储
        self._system_prompt = new_prompt
        # 更新会话中的 system 消息
        if session.messages and session.messages[0].get("role") == "system":
            session.messages[0]["content"] = new_prompt
        else:
            # 如果没有 system 消息，在开头插入
            session.messages.insert(0, {"role": "system", "content": new_prompt})
        logger.debug("已更新 System Prompt (长度: %d)", len(new_prompt))

    @property
    def current_session(self) -> Session:
        """获取当前会话。"""
        return self._sessions[self._current_id]

    @property
    def current_session_id(self) -> str:
        return self._current_id

    def list_sessions(self) -> list[Session]:
        """列出所有会话，按创建时间降序。"""
        return sorted(
            self._sessions.values(),
            key=lambda s: s.created_at,
            reverse=True,
        )

    # ------------------------------------------------------------------
    # 消息管理
    # ------------------------------------------------------------------

    def add_message(
        self,
        role: str,
        content: str,
        session_id: str = "",
        **extra: Any,
    ) -> None:
        """向当前（或指定）会话添加消息。

        Args:
            role: "user" | "assistant" | "system" | "tool"
            content: 消息内容
            session_id: 指定会话ID（默认用当前会话）
            **extra: 额外字段（如 tool_calls, tool_call_id）
        """
        session = self._get_session(session_id)
        msg: dict[str, Any] = {"role": role, "content": content}
        msg.update(extra)
        session.messages.append(msg)

        # 检查消息数量硬上限
        if len(session.messages) > self._max_message_count:
            self._enforce_message_limit(session)

        # 异步保存到存储（fire-and-forget）
        if self._storage:
            import asyncio
            from src.core.storage import StoredMessage
            extra_dict = extra or {}
            stored_msg = StoredMessage(
                id=None,
                session_id=session.id,
                role=role,
                content=content,
                tool_calls=extra_dict.get("tool_calls"),
                tool_call_id=extra_dict.get("tool_call_id"),
            )
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._storage.save_message(stored_msg))
                else:
                    loop.run_until_complete(self._storage.save_message(stored_msg))
            except Exception as e:
                logger.warning("保存消息到存储失败: %s", e)

    def add_tool_message(
        self,
        tool_call_id: str,
        content: str,
        session_id: str = "",
    ) -> None:
        """添加工具结果消息。"""
        self.add_message(
            role="tool",
            content=content,
            session_id=session_id,
            tool_call_id=tool_call_id,
        )

    def add_assistant_message(
        self,
        content: str,
        tool_calls: list[dict] | None = None,
        session_id: str = "",
    ) -> None:
        """添加助手消息（可能包含 tool_calls）。"""
        extra: dict[str, Any] = {}
        if tool_calls:
            extra["tool_calls"] = tool_calls
        self.add_message(
            role="assistant",
            content=content,
            session_id=session_id,
            **extra,
        )

    def get_messages(
        self,
        session_id: str = "",
        max_tokens: int = 0,
    ) -> list[dict[str, Any]]:
        """获取当前会话的消息列表（自动截断以适应上下文窗口）。

        Args:
            session_id: 指定会话ID
            max_tokens: 最大 token 数（0=使用默认 context_window）

        Returns:
            截断后的消息列表
        """
        session = self._get_session(session_id)
        # 预留 5% 安全余量（放宽限制以充分利用上下文窗口）
        limit = int((max_tokens or self._context_window) * 0.95)

        # 计算 token 估算（使用更保守的系数：中文字符约 1.5 字/token）
        messages = session.messages
        estimated_tokens = self._estimate_tokens(messages)

        if estimated_tokens <= limit:
            return list(messages)

        # 需要截断：保留 system prompt + 最近的消息
        logger.warning(
            "消息超限，触发截断: 估算 %d tokens > 限制 %d tokens",
            estimated_tokens, limit
        )
        return self._truncate_messages(messages, limit)

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """估算消息列表的 token 数量。

        使用合理的估算方式：
        - 中文字符：约 1 字/token（放宽估算）
        - 英文字符：约 4 字符/token
        - tool_calls 参数也要计算
        - 基础开销：每条消息约 4 tokens
        """
        total = 0
        for msg in messages:
            # content 字段
            content = str(msg.get("content", "") or "")
            # 使用更合理的系数：字符数 / 3（平衡中英文）
            total += len(content) // 3

            # tool_calls 字段
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                func = tc.get("function", {})
                args = str(func.get("arguments", ""))
                total += len(args) // 2
                total += len(func.get("name", ""))

            # 消息基础开销
            total += 4

        return total

    def clear_messages(self, session_id: str = "") -> None:
        """清空当前会话的消息（保留 system prompt）。"""
        session = self._get_session(session_id)
        system_msg = None
        if session.has_system_prompt:
            system_msg = session.messages[0]

        session.messages.clear()
        session.total_tokens = 0

        if system_msg:
            session.messages.append(system_msg)

        logger.info("清空会话消息: %s", session.id)

    def update_title(self, title: str, session_id: str = "") -> None:
        """更新会话标题。"""
        session = self._get_session(session_id)
        session.title = title

    def update_tokens(self, tokens: int, session_id: str = "") -> None:
        """更新会话累计 token 数。"""
        session = self._get_session(session_id)
        session.total_tokens += tokens

    # ------------------------------------------------------------------
    # 截断策略
    # ------------------------------------------------------------------

    def _truncate_messages(
        self,
        messages: list[dict[str, Any]],
        token_limit: int,
    ) -> list[dict[str, Any]]:
        """截断消息列表以适应 token 限制。

        Phase 4.7 增强策略：
        1. 保留第一条 system prompt
        2. 保留完整对话轮次（user + assistant + tool 消息组）
        3. 不截断 tool_calls 和对应的 tool 结果
        """
        if not messages:
            return []

        result = []
        system_msg = None

        # 抽出 system prompt
        if messages[0].get("role") == "system":
            system_msg = messages[0]
            messages = messages[1:]

        # 计算可用字符数（使用保守估算：字符数 / 2）
        remaining_chars = token_limit * 2  # 反向估算字符限制
        if system_msg:
            remaining_chars -= len(str(system_msg.get("content", "")))

        # 按对话轮次分组（user + assistant + tools 为一轮）
        rounds = self._group_message_rounds(messages)

        # 从后向前保留完整的对话轮次
        for round_msgs in reversed(rounds):
            round_chars = sum(len(str(m.get("content", ""))) for m in round_msgs)
            if remaining_chars - round_chars < 0:
                break
            result = round_msgs + result
            remaining_chars -= round_chars

        # 插入 system prompt
        if system_msg:
            result.insert(0, system_msg)

        truncated_count = len(messages) - (len(result) - (1 if system_msg else 0))
        if truncated_count > 0:
            logger.info("截断了 %d 条旧消息以适应上下文窗口", truncated_count)

        # 验证消息结构完整性
        result = self._validate_message_structure(result)

        return result

    def _validate_message_structure(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """验证并修复消息结构完整性。

        确保消息列表满足 OpenAI API 的要求：
        1. 以 system 或 user 消息开始
        2. tool 消息前面必须有带 tool_calls 的 assistant 消息
        """
        if not messages:
            return messages

        result = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            role = msg.get("role", "")

            # 跳过开头不是 system/user 的消息
            if not result and role not in ("system", "user"):
                i += 1
                continue

            # 处理 assistant 消息
            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    # 收集所有对应的 tool 消息
                    result.append(msg)
                    tool_call_ids = {tc.get("id") for tc in tool_calls}
                    i += 1
                    # 添加对应的 tool 消息
                    while i < len(messages):
                        next_msg = messages[i]
                        if next_msg.get("role") == "tool":
                            # 检查 tool_call_id 是否匹配
                            if next_msg.get("tool_call_id") in tool_call_ids:
                                result.append(next_msg)
                                i += 1
                            else:
                                # 不匹配的 tool 消息，跳过
                                i += 1
                        else:
                            break
                else:
                    result.append(msg)
                    i += 1
            else:
                result.append(msg)
                i += 1

        return result

    def _group_message_rounds(self, messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """将消息按对话轮次分组。

        一轮对话 = user消息 + (assistant消息 + tool_calls + tool结果)
        """
        rounds = []
        current_round = []

        for msg in messages:
            role = msg.get("role", "")

            if role == "user":
                # 新的一轮开始
                if current_round:
                    rounds.append(current_round)
                current_round = [msg]
            elif role == "assistant":
                current_round.append(msg)
                # 如果有 tool_calls，后续会有 tool 消息
            elif role == "tool":
                current_round.append(msg)
            else:
                # 其他消息加入当前轮
                current_round.append(msg)

        # 最后一轮
        if current_round:
            rounds.append(current_round)

        return rounds

    def _enforce_message_limit(self, session: Session) -> None:
        """强制执行消息数量限制，保留完整的对话轮次。"""
        if len(session.messages) <= self._max_message_count:
            return

        # 保留 system prompt
        system_msg = None
        messages = session.messages
        if messages and messages[0].get("role") == "system":
            system_msg = messages[0]
            messages = messages[1:]

        # 按轮次分组
        rounds = self._group_message_rounds(messages)

        # 计算需要保留的轮次数
        target_count = self._max_message_count - (1 if system_msg else 0)
        kept_rounds = []
        current_count = 0

        # 从后向前保留轮次
        for round_msgs in reversed(rounds):
            if current_count + len(round_msgs) > target_count:
                break
            kept_rounds.insert(0, round_msgs)
            current_count += len(round_msgs)

        # 重建消息列表
        new_messages = []
        if system_msg:
            new_messages.append(system_msg)
        for round_msgs in kept_rounds:
            new_messages.extend(round_msgs)

        session.messages = new_messages
        logger.info("会话 %s 消息数量超限，已截断至 %d 条", session.id, len(new_messages))

    # ------------------------------------------------------------------
    # 持久化相关（Phase 4.4）
    # ------------------------------------------------------------------

    async def load_history(self, limit: int = 10) -> list[Session]:
        """从存储加载最近的会话历史。

        只加载元数据，不加载消息内容。

        Args:
            limit: 加载的会话数量

        Returns:
            加载的会话列表
        """
        if not self._storage:
            return []

        from src.core.storage import StoredSession

        stored_sessions = await self._storage.list_sessions(limit=limit)
        loaded = []

        for stored in stored_sessions:
            # 如果已经在内存中，跳过
            if stored.id in self._sessions:
                continue

            # 创建 Session 对象（不加载消息）
            session = Session(
                id=stored.id,
                title=stored.title,
                model_key=stored.model_key,
                created_at=stored.created_at,
                messages=[],  # 消息在需要时按需加载
                total_tokens=stored.total_tokens,
                metadata=stored.metadata,
            )
            self._sessions[stored.id] = session
            loaded.append(session)

        if loaded:
            logger.info("从存储加载了 %d 个历史会话", len(loaded))

        return loaded

    async def load_session_messages(self, session_id: str) -> None:
        """从存储加载指定会话的消息。"""
        if not self._storage:
            return

        session = self._get_session(session_id)
        if session.messages:  # 已经加载过
            return

        stored_msgs = await self._storage.load_messages(session_id)
        for stored in stored_msgs:
            msg = stored.to_dict()
            # 跳过 system prompt（已有）
            if msg.get("role") == "system" and session.has_system_prompt:
                continue
            session.messages.append(msg)

        logger.info("加载会话 %s 的 %d 条消息", session_id, len(stored_msgs))

    def generate_title(self, session_id: str = "") -> str:
        """根据首条用户消息生成会话标题。

        规则：取用户首条消息前 20 字符 + "..."
        """
        session = self._get_session(session_id)

        # 查找第一条用户消息
        for msg in session.messages:
            if msg.get("role") == "user":
                content = str(msg.get("content", ""))
                if len(content) <= 20:
                    title = content
                else:
                    title = content[:20] + "..."
                # 更新标题
                session.title = title
                # 异步更新存储
                if self._storage:
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(
                                self._storage.update_session_title(session.id, title)
                            )
                        else:
                            loop.run_until_complete(
                                self._storage.update_session_title(session.id, title)
                            )
                    except Exception as e:
                        logger.warning("更新会话标题失败: %s", e)
                return title

        return session.title

    async def export_session(self, session_id: str = "", format: str = "markdown") -> str:
        """导出会话内容。"""
        if not self._storage:
            # 从内存导出
            session = self._get_session(session_id)
            lines = [
                f"# {session.title}",
                "",
                f"> 创建时间: {session.created_at.strftime('%Y-%m-%d %H:%M')}",
                "",
                "---",
                "",
            ]
            for msg in session.messages:
                role_label = {
                    "system": "⚙️ System",
                    "user": "👤 User",
                    "assistant": "🤖 Assistant",
                    "tool": "🔧 Tool",
                }.get(msg.get("role", ""), msg.get("role", ""))
                lines.append(f"### {role_label}")
                lines.append("")
                lines.append(str(msg.get("content", "")))
                lines.append("")
            return "\n".join(lines)

        sid = session_id or self._current_id
        return await self._storage.export_session(sid, format)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_session(self, session_id: str = "") -> Session:
        """获取指定会话或当前会话。"""
        sid = session_id or self._current_id
        if sid not in self._sessions:
            raise ValueError(f"会话不存在: {sid}")
        return self._sessions[sid]

    def _cleanup_oldest(self) -> None:
        """清理最旧的会话以保持在限制内。"""
        sessions = sorted(self._sessions.values(), key=lambda s: s.created_at)
        while len(self._sessions) > self._max_sessions:
            oldest = sessions.pop(0)
            if oldest.id != self._current_id:
                del self._sessions[oldest.id]
                logger.info("自动清理旧会话: %s", oldest.id)
