"""工具调用前置校验器 — 在工具执行前进行安全检查。

Phase 6 新增模块。

当前仅实现单次调用数量限制（硬约束），不做相关性校验（风险太高，容易过度拦截）。

设计原则："宁 Warn 不 Reject" — 除了数量限制这种无争议的硬约束外，
其他校验都应该是警告而非阻断。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """校验结果。"""

    status: str  # "PASS" | "WARN" | "REJECT"
    message: str = ""

    @property
    def is_passed(self) -> bool:
        return self.status == "PASS"

    @property
    def is_rejected(self) -> bool:
        return self.status == "REJECT"


class ToolCallValidator:
    """工具调用前置校验器。

    当前支持的校验规则：
    1. 单次工具调用数量限制（硬约束，REJECT）

    未来可扩展：
    - 参数格式校验（WARN）
    - 工具相关性软约束（WARN）
    """

    def __init__(self, max_per_call: int = 3) -> None:
        """初始化。

        Args:
            max_per_call: 单次允许的最大工具调用数量
        """
        self._max_per_call = max_per_call

    def validate(self, tool_calls: list[Any]) -> ValidationResult:
        """校验一组工具调用。

        Args:
            tool_calls: 模型返回的 tool_calls 列表

        Returns:
            ValidationResult
        """
        # 规则 1: 数量限制
        if len(tool_calls) > self._max_per_call:
            msg = (
                f"单次工具调用数量({len(tool_calls)})超过限制({self._max_per_call})，"
                f"请分步执行。"
            )
            logger.warning("前置校验拒绝: %s", msg)
            return ValidationResult(status="REJECT", message=msg)

        return ValidationResult(status="PASS")

    @property
    def max_per_call(self) -> int:
        return self._max_per_call
