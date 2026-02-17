"""审计日志 — 记录所有工具调用的完整审计轨迹。

支持：
- 记录每次工具调用的时间、工具名、动作、参数、结果、耗时、风险等级
- 通过 EventBus 自动订阅 TOOL_CALL / TOOL_RESULT 事件
- JSON 格式导出
- 日志文件按日轮转
- 内存日志查询（最近 N 条）
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.event_bus import EventBus
from src.core.events import EventType, ToolCallEvent, ToolResultEvent

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    """单条审计记录。"""

    timestamp: str  # ISO 格式时间字符串
    tool_name: str
    action_name: str
    function_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    status: str = ""  # "success" | "error" | "timeout" | "denied"
    output_preview: str = ""  # 输出前200字符
    error: str = ""
    duration_ms: float = 0.0
    risk_level: str = "low"
    session_id: str = ""
    completed: bool = False  # 是否已有结果

    # Phase 6 增强字段
    intent: str = ""  # 识别到的意图
    confidence: float = 0.0  # 意图置信度
    tool_tier: str = ""  # 工具集层级 (recommended/extended/full)
    consecutive_failures: int = 0  # 当时的连续失败次数
    user_input: str = ""  # 原始用户输入

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLogger:
    """审计日志记录器。

    用法::

        audit = AuditLogger(log_dir=Path("~/.winclaw/audit"))
        audit.connect(event_bus)  # 自动订阅事件

        # 或手动记录
        audit.log_call("shell", "run", {"command": "dir"})
        audit.log_result("shell", "run", "success", output="...", duration_ms=150)

        # 查询
        recent = audit.get_recent(10)
        audit.export_json(Path("audit.json"))
    """

    def __init__(
        self,
        log_dir: Path | None = None,
        max_memory_entries: int = 1000,
        write_to_file: bool = True,
    ):
        """
        Args:
            log_dir: 日志文件目录
            max_memory_entries: 内存中保留的最大条目数
            write_to_file: 是否写入文件
        """
        self._log_dir = log_dir or Path.home() / ".winclaw" / "audit"
        self._max_memory = max_memory_entries
        self._write_to_file = write_to_file
        self._entries: deque[AuditEntry] = deque(maxlen=max_memory_entries)
        # 待完成的调用（tool_call 发出但 tool_result 尚未到达）
        self._pending: dict[str, AuditEntry] = {}  # function_name → entry
        # 统计
        self._total_calls = 0
        self._total_errors = 0
        self._total_denied = 0

    # ------------------------------------------------------------------
    # EventBus 集成
    # ------------------------------------------------------------------

    def connect(self, event_bus: EventBus) -> None:
        """连接到事件总线，自动订阅工具调用/结果事件。"""
        event_bus.on(EventType.TOOL_CALL, self._on_tool_call, priority=50)
        event_bus.on(EventType.TOOL_RESULT, self._on_tool_result, priority=50)
        logger.info("审计日志已连接到事件总线")

    def _on_tool_call(self, event_type: str, data: Any) -> None:
        """处理工具调用事件。"""
        if isinstance(data, ToolCallEvent):
            entry = AuditEntry(
                timestamp=datetime.now().isoformat(),
                tool_name=data.tool_name,
                action_name=data.action_name,
                function_name=data.function_name,
                arguments=data.arguments,
                session_id=data.session_id,
            )
        elif isinstance(data, dict):
            entry = AuditEntry(
                timestamp=datetime.now().isoformat(),
                tool_name=data.get("tool_name", ""),
                action_name=data.get("action_name", ""),
                function_name=data.get("function_name", ""),
                arguments=data.get("arguments", {}),
                session_id=data.get("session_id", ""),
            )
        else:
            return

        self._pending[entry.function_name or f"{entry.tool_name}_{entry.action_name}"] = entry
        self._total_calls += 1

    def _on_tool_result(self, event_type: str, data: Any) -> None:
        """处理工具结果事件。"""
        if isinstance(data, ToolResultEvent):
            key = f"{data.tool_name}_{data.action_name}"
            status = data.status
            output = data.output
            error = data.error
            duration_ms = data.duration_ms
            session_id = data.session_id
        elif isinstance(data, dict):
            key = f"{data.get('tool_name', '')}_{data.get('action_name', '')}"
            status = data.get("status", "")
            output = data.get("output", "")
            error = data.get("error", "")
            duration_ms = data.get("duration_ms", 0)
            session_id = data.get("session_id", "")
        else:
            return

        entry = self._pending.pop(key, None)
        if entry is None:
            # 没有匹配的 call，创建新记录
            entry = AuditEntry(
                timestamp=datetime.now().isoformat(),
                tool_name=data.tool_name if hasattr(data, "tool_name") else "",
                action_name=data.action_name if hasattr(data, "action_name") else "",
                session_id=session_id,
            )

        entry.status = status
        entry.output_preview = output[:200] if output else ""
        entry.error = error
        entry.duration_ms = duration_ms
        entry.completed = True

        if status == "error":
            self._total_errors += 1
        elif status == "denied":
            self._total_denied += 1

        self._entries.append(entry)

        if self._write_to_file:
            self._write_entry(entry)

    # ------------------------------------------------------------------
    # 手动记录
    # ------------------------------------------------------------------

    def log_call(
        self,
        tool_name: str,
        action_name: str,
        arguments: dict[str, Any] | None = None,
        risk_level: str = "low",
        session_id: str = "",
    ) -> AuditEntry:
        """手动记录一次工具调用（无结果）。"""
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            tool_name=tool_name,
            action_name=action_name,
            arguments=arguments or {},
            risk_level=risk_level,
            session_id=session_id,
        )
        self._pending[f"{tool_name}_{action_name}"] = entry
        self._total_calls += 1
        return entry

    def log_result(
        self,
        tool_name: str,
        action_name: str,
        status: str,
        output: str = "",
        error: str = "",
        duration_ms: float = 0.0,
        session_id: str = "",
    ) -> AuditEntry:
        """手动记录一次工具结果。"""
        key = f"{tool_name}_{action_name}"
        entry = self._pending.pop(key, None)
        if entry is None:
            entry = AuditEntry(
                timestamp=datetime.now().isoformat(),
                tool_name=tool_name,
                action_name=action_name,
                session_id=session_id,
            )

        entry.status = status
        entry.output_preview = output[:200] if output else ""
        entry.error = error
        entry.duration_ms = duration_ms
        entry.completed = True

        if status == "error":
            self._total_errors += 1
        elif status == "denied":
            self._total_denied += 1

        self._entries.append(entry)

        if self._write_to_file:
            self._write_entry(entry)

        return entry

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_recent(self, count: int = 20) -> list[AuditEntry]:
        """获取最近 N 条审计记录。"""
        entries = list(self._entries)
        return entries[-count:] if len(entries) > count else entries

    def get_by_tool(self, tool_name: str) -> list[AuditEntry]:
        """按工具名查询。"""
        return [e for e in self._entries if e.tool_name == tool_name]

    def get_by_session(self, session_id: str) -> list[AuditEntry]:
        """按会话查询。"""
        return [e for e in self._entries if e.session_id == session_id]

    def get_errors(self) -> list[AuditEntry]:
        """获取所有错误记录。"""
        return [e for e in self._entries if e.status in ("error", "denied")]

    @property
    def total_calls(self) -> int:
        return self._total_calls

    @property
    def total_errors(self) -> int:
        return self._total_errors

    @property
    def total_denied(self) -> int:
        return self._total_denied

    def get_stats(self) -> dict[str, Any]:
        """获取审计统计。"""
        return {
            "total_calls": self._total_calls,
            "total_errors": self._total_errors,
            "total_denied": self._total_denied,
            "entries_in_memory": len(self._entries),
            "pending_calls": len(self._pending),
        }

    # ------------------------------------------------------------------
    # 文件输出
    # ------------------------------------------------------------------

    def _write_entry(self, entry: AuditEntry) -> None:
        """将单条记录追加写入日志文件。"""
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = self._log_dir / f"audit-{today}.jsonl"

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("写入审计日志失败: %s", e)

    def export_json(self, output_path: Path) -> int:
        """导出所有内存中的审计记录为 JSON 文件。

        Returns:
            导出的记录数
        """
        entries = [e.to_dict() for e in self._entries]
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
            logger.info("导出 %d 条审计记录到 %s", len(entries), output_path)
        except Exception as e:
            logger.error("导出审计日志失败: %s", e)
            return 0
        return len(entries)

    def clear(self) -> None:
        """清空内存中的审计记录。"""
        self._entries.clear()
        self._pending.clear()
        self._total_calls = 0
        self._total_errors = 0
        self._total_denied = 0
