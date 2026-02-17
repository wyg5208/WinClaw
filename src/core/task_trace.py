"""全链路对话追踪系统 — TaskTrace。

记录每次用户请求从意图识别到任务完成的完整轨迹：
- 用户输入 → 意图识别 → 工具暴露策略 → 工具调用序列 → 最终回复

用于：
- 分析意图识别准确率
- 评估工具选择相关性
- 发现失败模式
- 优化暴露策略参数
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认 trace 目录
DEFAULT_TRACE_DIR = Path.home() / ".winclaw" / "traces"

# 敏感参数名列表
SENSITIVE_PARAM_NAMES = {
    "api_key", "apikey", "api-key",
    "password", "passwd", "pwd",
    "token", "access_token", "refresh_token", "auth_token",
    "secret", "secret_key", "client_secret",
    "credential", "credentials",
    "private_key", "privatekey",
    "authorization", "auth",
}

# 敏感值模式（正则）
SENSITIVE_VALUE_PATTERNS = [
    # API Key 格式（超过 20 字符的字母数字混合，常见于各类 API Key）
    re.compile(r'\b[a-zA-Z0-9_-]{20,}\b'),
    # 明显的 key=xxx 模式
    re.compile(r'(api_key|apikey|api-key|token|secret|password)\s*[=:]\s*["\']?[\w-]{10,}["\']?', re.I),
]


# ------------------------------------------------------------------
# 数据结构
# ------------------------------------------------------------------

@dataclass
class ToolCallRecord:
    """单次工具调用记录。"""

    step: int                      # 第几步
    function_name: str             # 如 "browser_use_run_task"
    arguments: dict[str, Any]      # 调用参数
    status: str                    # success / error / timeout / denied
    duration_ms: float
    error: str = ""
    output_preview: str = ""       # 输出前 N 字符

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskTrace:
    """一次用户请求的完整追踪记录。"""

    trace_id: str                  # UUID
    session_id: str
    timestamp: str                 # ISO 时间
    user_input: str                # 原始用户输入

    # --- 意图识别阶段 ---
    intent_primary: str = ""       # 主要意图
    intent_all: list[str] = field(default_factory=list)  # 所有匹配意图
    intent_confidence: float = 0.0  # 置信度
    matched_keywords: dict[str, list[str]] = field(default_factory=dict)

    # --- 工具暴露阶段 ---
    tool_tier: str = ""            # recommended / extended / full
    tools_exposed: list[str] = field(default_factory=list)  # 暴露给模型的工具名
    tools_exposed_count: int = 0

    # --- 执行阶段 ---
    total_steps: int = 0
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    consecutive_failures_max: int = 0
    tier_upgrades: list[str] = field(default_factory=list)  # ["recommended->extended", ...]

    # --- 结果阶段 ---
    final_status: str = ""         # completed / max_steps / error / cancelled
    total_tokens: int = 0
    total_duration_ms: float = 0.0
    assistant_response_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        # 将 ToolCallRecord 转为 dict
        result["tool_calls"] = [tc.to_dict() if isinstance(tc, ToolCallRecord) else tc for tc in self.tool_calls]
        return result


# ------------------------------------------------------------------
# 敏感信息脱敏
# ------------------------------------------------------------------

def _sanitize_dict(d: dict[str, Any], max_preview: int = 200) -> dict[str, Any]:
    """对字典中的敏感参数值进行脱敏。"""
    result = {}
    for key, value in d.items():
        key_lower = key.lower().replace("-", "_")
        if key_lower in SENSITIVE_PARAM_NAMES:
            result[key] = "***"
        elif isinstance(value, dict):
            result[key] = _sanitize_dict(value, max_preview)
        elif isinstance(value, str):
            result[key] = _sanitize_string(value, max_preview)
        else:
            result[key] = value
    return result


def _sanitize_string(s: str, max_len: int = 200) -> str:
    """对字符串中的敏感信息进行脱敏。"""
    if not s:
        return s
    # 截断过长的字符串
    if len(s) > max_len:
        s = s[:max_len] + "..."
    # 替换敏感模式
    for pattern in SENSITIVE_VALUE_PATTERNS:
        s = pattern.sub("***", s)
    return s


# ------------------------------------------------------------------
# TaskTraceCollector
# ------------------------------------------------------------------

class TaskTraceCollector:
    """追踪采集器 — 绑定一次 chat/chat_stream 调用的完整生命周期。

    用法::
        collector = TaskTraceCollector(session_id, user_input)
        collector.set_intent(intent_result, tier, exposed_tools)

        # 每次工具调用
        collector.add_tool_call(step, func_name, args, result)

        # 层级升级（如有）
        collector.add_tier_upgrade("recommended", "extended")

        # 结束
        collector.finalize(status="completed", tokens=500, response_preview="...")
        collector.flush()  # 写入文件
    """

    def __init__(
        self,
        session_id: str,
        user_input: str,
        trace_dir: Path | None = None,
        max_output_preview: int = 200,
        max_trace_days: int = 30,
        enabled: bool = True,
    ):
        self._trace = TaskTrace(
            trace_id=str(uuid.uuid4())[:8],
            session_id=session_id,
            timestamp=datetime.now().isoformat(),
            user_input=user_input,
        )
        self._trace_dir = trace_dir or DEFAULT_TRACE_DIR
        self._max_output_preview = max_output_preview
        self._max_trace_days = max_trace_days
        self._enabled = enabled
        self._start_time = time.perf_counter()
        self._consecutive_failures = 0
        self._finalized = False

    # ------------------------------------------------------------------
    # 数据采集方法
    # ------------------------------------------------------------------

    def set_intent(
        self,
        intent_result: Any,  # IntentResult from prompts.py
        tier: str,
        exposed_tools: list[str],
    ) -> None:
        """设置意图识别结果。"""
        # 即使 disabled 也采集数据，只是不写文件
        self._trace.intent_primary = getattr(intent_result, "primary_intent", "")
        self._trace.intent_all = list(getattr(intent_result, "intents", set()))
        self._trace.intent_confidence = getattr(intent_result, "confidence", 0.0)
        self._trace.matched_keywords = {
            k: v for k, v in getattr(intent_result, "matched_keywords", {}).items()
        }
        self._trace.tool_tier = tier
        self._trace.tools_exposed = list(exposed_tools)
        self._trace.tools_exposed_count = len(exposed_tools)

    def add_tool_call(
        self,
        step: int,
        function_name: str,
        arguments: dict[str, Any],
        status: str,
        duration_ms: float,
        error: str = "",
        output: str = "",
    ) -> None:
        """添加一次工具调用记录。"""
        # 即使 disabled 也采集数据，只是不写文件

        # 更新连续失败计数
        if status in ("error", "timeout", "denied"):
            self._consecutive_failures += 1
            if self._consecutive_failures > self._trace.consecutive_failures_max:
                self._trace.consecutive_failures_max = self._consecutive_failures
        else:
            self._consecutive_failures = 0

        record = ToolCallRecord(
            step=step,
            function_name=function_name,
            arguments=arguments,
            status=status,
            duration_ms=duration_ms,
            error=error,
            output_preview=output[:self._max_output_preview] if output else "",
        )
        self._trace.tool_calls.append(record)
        self._trace.total_steps = step

    def add_tier_upgrade(self, from_tier: str, to_tier: str) -> None:
        """记录层级升级。"""
        # 即使 disabled 也采集数据
        self._trace.tier_upgrades.append(f"{from_tier}->{to_tier}")
        self._trace.tool_tier = to_tier

    def finalize(
        self,
        status: str,
        tokens: int = 0,
        response_preview: str = "",
    ) -> None:
        """完成追踪记录。"""
        if self._finalized:
            return

        self._trace.final_status = status
        self._trace.total_tokens = tokens
        self._trace.total_duration_ms = (time.perf_counter() - self._start_time) * 1000
        self._trace.assistant_response_preview = response_preview[:300] if response_preview else ""
        self._finalized = True

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def flush(self) -> bool:
        """将追踪记录写入 JSONL 文件。"""
        if not self._enabled or not self._finalized:
            return False

        try:
            # 确保目录存在
            self._trace_dir.mkdir(parents=True, exist_ok=True)

            # 清理过期文件
            self._cleanup_old_traces()

            # 脱敏处理
            sanitized = self._sanitize_trace()

            # 写入 JSONL
            today = datetime.now().strftime("%Y-%m-%d")
            trace_file = self._trace_dir / f"trace-{today}.jsonl"

            with open(trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(sanitized, ensure_ascii=False) + "\n")

            logger.debug("TaskTrace 已写入: %s (id=%s)", trace_file, self._trace.trace_id)
            return True

        except Exception as e:
            logger.error("写入 TaskTrace 失败: %s", e)
            return False

    def _sanitize_trace(self) -> dict[str, Any]:
        """对追踪记录进行脱敏处理。"""
        trace_dict = self._trace.to_dict()

        # 脱敏 user_input
        trace_dict["user_input"] = _sanitize_string(trace_dict.get("user_input", ""), max_len=1000)

        # 脱敏 tool_calls 中的 arguments 和 output_preview
        for tc in trace_dict.get("tool_calls", []):
            if isinstance(tc, dict):
                if tc.get("arguments"):
                    tc["arguments"] = _sanitize_dict(tc["arguments"])
                if tc.get("output_preview"):
                    tc["output_preview"] = _sanitize_string(tc["output_preview"])

        # 脱敏 assistant_response_preview
        if trace_dict.get("assistant_response_preview"):
            trace_dict["assistant_response_preview"] = _sanitize_string(
                trace_dict["assistant_response_preview"], max_len=300
            )

        return trace_dict

    def _cleanup_old_traces(self) -> None:
        """清理过期的 trace 文件。"""
        if self._max_trace_days <= 0:
            return

        try:
            cutoff = datetime.now() - timedelta(days=self._max_trace_days)
            for f in self._trace_dir.glob("trace-*.jsonl"):
                # 从文件名解析日期
                try:
                    date_str = f.stem.replace("trace-", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if file_date < cutoff:
                        f.unlink()
                        logger.debug("已清理过期 trace 文件: %s", f)
                except ValueError:
                    pass  # 文件名格式不匹配，跳过
        except Exception as e:
            logger.warning("清理过期 trace 文件失败: %s", e)

    @property
    def trace_id(self) -> str:
        return self._trace.trace_id

    @property
    def trace(self) -> TaskTrace:
        return self._trace


# ------------------------------------------------------------------
# 全局工厂函数
# ------------------------------------------------------------------

def create_trace_collector(
    session_id: str,
    user_input: str,
    config: dict[str, Any] | None = None,
) -> TaskTraceCollector:
    """根据配置创建 TraceCollector。"""
    cfg = config or {}
    return TaskTraceCollector(
        session_id=session_id,
        user_input=user_input,
        trace_dir=Path(cfg.get("trace_dir", "")) if cfg.get("trace_dir") else None,
        max_output_preview=cfg.get("max_output_preview", 200),
        max_trace_days=cfg.get("max_trace_days", 30),
        enabled=cfg.get("enabled", True),
    )
