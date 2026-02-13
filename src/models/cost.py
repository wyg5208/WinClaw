"""成本追踪器 — 记录和统计模型调用的 token 用量与费用。

支持：
- 按会话统计（session_id 标识）
- 按日统计
- 按模型统计
- 总量统计
- 预算限制告警
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from src.models.registry import ModelConfig, UsageRecord

logger = logging.getLogger(__name__)


@dataclass
class SessionCost:
    """单个会话的累计费用。"""

    session_id: str
    total_tokens: int = 0
    total_cost: float = 0.0
    call_count: int = 0
    records: list[UsageRecord] = field(default_factory=list)


@dataclass
class DailyCost:
    """单日累计费用。"""

    date: date
    total_tokens: int = 0
    total_cost: float = 0.0
    call_count: int = 0


@dataclass
class ModelCost:
    """单个模型的累计费用。"""

    model_key: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0
    call_count: int = 0


class CostTracker:
    """成本追踪器。

    用法::

        tracker = CostTracker(budget_limit=1.0)
        tracker.record(usage_record, session_id="session-1")
        print(tracker.get_session_cost("session-1"))
        print(tracker.get_today_cost())
    """

    def __init__(self, budget_limit: float = 0.0):
        """
        Args:
            budget_limit: 每日预算上限（USD），0=不限制
        """
        self._budget_limit = budget_limit
        self._records: list[tuple[UsageRecord, str, datetime]] = []  # (record, session_id, time)
        self._session_costs: dict[str, SessionCost] = {}
        self._daily_costs: dict[date, DailyCost] = {}
        self._model_costs: dict[str, ModelCost] = {}

    # ------------------------------------------------------------------
    # 记录
    # ------------------------------------------------------------------

    def record(
        self,
        usage: UsageRecord,
        session_id: str = "default",
        timestamp: datetime | None = None,
    ) -> None:
        """记录一次模型调用的用量。

        Args:
            usage: 用量记录
            session_id: 会话标识
            timestamp: 调用时间（默认当前时间）
        """
        ts = timestamp or datetime.now()
        self._records.append((usage, session_id, ts))

        # 更新会话统计
        if session_id not in self._session_costs:
            self._session_costs[session_id] = SessionCost(session_id=session_id)
        sc = self._session_costs[session_id]
        sc.total_tokens += usage.total_tokens
        sc.total_cost += usage.cost
        sc.call_count += 1
        sc.records.append(usage)

        # 更新日统计
        day = ts.date()
        if day not in self._daily_costs:
            self._daily_costs[day] = DailyCost(date=day)
        dc = self._daily_costs[day]
        dc.total_tokens += usage.total_tokens
        dc.total_cost += usage.cost
        dc.call_count += 1

        # 更新模型统计
        mk = usage.model_key
        if mk not in self._model_costs:
            self._model_costs[mk] = ModelCost(model_key=mk)
        mc = self._model_costs[mk]
        mc.total_tokens += usage.total_tokens
        mc.prompt_tokens += usage.prompt_tokens
        mc.completion_tokens += usage.completion_tokens
        mc.total_cost += usage.cost
        mc.call_count += 1

        # 预算告警
        if self._budget_limit > 0:
            today_cost = self._daily_costs.get(date.today())
            if today_cost and today_cost.total_cost >= self._budget_limit:
                logger.warning(
                    "⚠️ 今日费用 $%.4f 已达到预算上限 $%.2f",
                    today_cost.total_cost,
                    self._budget_limit,
                )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_session_cost(self, session_id: str) -> SessionCost | None:
        """获取指定会话的费用统计。"""
        return self._session_costs.get(session_id)

    def get_today_cost(self) -> DailyCost:
        """获取今日费用统计。"""
        today = date.today()
        return self._daily_costs.get(today, DailyCost(date=today))

    def get_daily_cost(self, target_date: date) -> DailyCost:
        """获取指定日期的费用统计。"""
        return self._daily_costs.get(target_date, DailyCost(date=target_date))

    def get_model_cost(self, model_key: str) -> ModelCost | None:
        """获取指定模型的累计费用。"""
        return self._model_costs.get(model_key)

    def get_all_model_costs(self) -> list[ModelCost]:
        """获取所有模型的费用统计，按费用降序。"""
        return sorted(self._model_costs.values(), key=lambda m: m.total_cost, reverse=True)

    def get_daily_history(self, days: int = 7) -> list[DailyCost]:
        """获取最近 N 天的费用历史。"""
        sorted_days = sorted(self._daily_costs.values(), key=lambda d: d.date, reverse=True)
        return sorted_days[:days]

    # ------------------------------------------------------------------
    # 总量
    # ------------------------------------------------------------------

    @property
    def total_cost(self) -> float:
        """总费用。"""
        return sum(r[0].cost for r in self._records)

    @property
    def total_tokens(self) -> int:
        """总 token 数。"""
        return sum(r[0].total_tokens for r in self._records)

    @property
    def total_calls(self) -> int:
        """总调用次数。"""
        return len(self._records)

    @property
    def budget_limit(self) -> float:
        return self._budget_limit

    @budget_limit.setter
    def budget_limit(self, value: float) -> None:
        self._budget_limit = max(0.0, value)

    def is_over_budget(self) -> bool:
        """今日是否超出预算。"""
        if self._budget_limit <= 0:
            return False
        today_cost = self.get_today_cost()
        return today_cost.total_cost >= self._budget_limit

    # ------------------------------------------------------------------
    # 格式化输出
    # ------------------------------------------------------------------

    def get_summary(self) -> dict[str, Any]:
        """返回综合统计摘要。"""
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost, 6),
            "today": {
                "calls": self.get_today_cost().call_count,
                "tokens": self.get_today_cost().total_tokens,
                "cost_usd": round(self.get_today_cost().total_cost, 6),
            },
            "budget_limit_usd": self._budget_limit,
            "over_budget": self.is_over_budget(),
            "sessions": len(self._session_costs),
            "models_used": len(self._model_costs),
        }

    def format_report(self) -> str:
        """格式化费用报告字符串。"""
        lines = ["=== WinClaw 费用报告 ==="]
        lines.append(f"总调用: {self.total_calls} 次")
        lines.append(f"总 Token: {self.total_tokens:,}")
        lines.append(f"总费用: ${self.total_cost:.6f}")
        lines.append("")

        # 今日
        today = self.get_today_cost()
        lines.append(f"今日: {today.call_count} 次 | {today.total_tokens:,} tokens | ${today.total_cost:.6f}")

        if self._budget_limit > 0:
            pct = (today.total_cost / self._budget_limit * 100) if self._budget_limit else 0
            lines.append(f"预算: ${self._budget_limit:.2f} | 已用 {pct:.1f}%")

        # 按模型
        if self._model_costs:
            lines.append("")
            lines.append("按模型统计:")
            for mc in self.get_all_model_costs():
                lines.append(
                    f"  {mc.model_key}: {mc.call_count}次 | "
                    f"{mc.total_tokens:,} tokens | ${mc.total_cost:.6f}"
                )

        return "\n".join(lines)

    def clear(self) -> None:
        """清空所有统计数据。"""
        self._records.clear()
        self._session_costs.clear()
        self._daily_costs.clear()
        self._model_costs.clear()
