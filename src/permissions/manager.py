"""权限管理器 — 工具调用的权限控制与确认流程。

定义权限等级：
- LOW: 低危操作（读取信息、截图等），自动通过
- MEDIUM: 中危操作（写文件、读敏感文件等），按策略决定
- HIGH: 高危操作（执行命令、删除文件等），需要确认

确认策略：
- AUTO_APPROVE: 自动通过（适用于低危操作）
- LOG_ONLY: 仅记录日志，自动通过
- REQUIRE_CONFIRM: 需要用户确认（预留，当前版本自动通过但记录告警）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from src.core.event_bus import EventBus
from src.core.events import EventType

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """操作风险等级。"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfirmPolicy(str, Enum):
    """确认策略。"""
    AUTO_APPROVE = "auto_approve"
    LOG_ONLY = "log_only"
    REQUIRE_CONFIRM = "require_confirm"


@dataclass
class PermissionRule:
    """单条权限规则。"""
    tool_name: str
    action_name: str = "*"  # "*" 表示该工具所有动作
    risk_level: RiskLevel = RiskLevel.LOW
    policy: ConfirmPolicy = ConfirmPolicy.AUTO_APPROVE
    description: str = ""


@dataclass
class PermissionRequest:
    """权限请求。"""
    tool_name: str
    action_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    session_id: str = ""


@dataclass
class PermissionResult:
    """权限检查结果。"""
    approved: bool = True
    risk_level: RiskLevel = RiskLevel.LOW
    reason: str = ""
    requires_confirmation: bool = False


# 默认权限规则
_DEFAULT_RULES: list[PermissionRule] = [
    # Shell 工具 — 高危
    PermissionRule(
        tool_name="shell",
        action_name="run",
        risk_level=RiskLevel.HIGH,
        policy=ConfirmPolicy.LOG_ONLY,
        description="执行系统命令",
    ),
    # File 写入/编辑 — 中危
    PermissionRule(
        tool_name="file",
        action_name="write",
        risk_level=RiskLevel.MEDIUM,
        policy=ConfirmPolicy.LOG_ONLY,
        description="写入文件",
    ),
    PermissionRule(
        tool_name="file",
        action_name="edit",
        risk_level=RiskLevel.MEDIUM,
        policy=ConfirmPolicy.LOG_ONLY,
        description="编辑文件",
    ),
    # File 读取/搜索/列表/树 — 低危
    PermissionRule(
        tool_name="file",
        action_name="read",
        risk_level=RiskLevel.LOW,
        policy=ConfirmPolicy.AUTO_APPROVE,
        description="读取文件",
    ),
    PermissionRule(
        tool_name="file",
        action_name="search",
        risk_level=RiskLevel.LOW,
        policy=ConfirmPolicy.AUTO_APPROVE,
        description="搜索文件内容",
    ),
    PermissionRule(
        tool_name="file",
        action_name="list",
        risk_level=RiskLevel.LOW,
        policy=ConfirmPolicy.AUTO_APPROVE,
        description="列出目录",
    ),
    PermissionRule(
        tool_name="file",
        action_name="tree",
        risk_level=RiskLevel.LOW,
        policy=ConfirmPolicy.AUTO_APPROVE,
        description="目录树",
    ),
    # Screen — 低危
    PermissionRule(
        tool_name="screen",
        action_name="*",
        risk_level=RiskLevel.LOW,
        policy=ConfirmPolicy.AUTO_APPROVE,
        description="屏幕截图",
    ),
]


class PermissionManager:
    """权限管理器。

    用法::

        pm = PermissionManager(event_bus=bus)
        result = pm.check(PermissionRequest(
            tool_name="shell",
            action_name="run",
            arguments={"command": "dir"},
        ))
        if result.approved:
            # 执行工具
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        rules: list[PermissionRule] | None = None,
        high_risk_auto_approve: bool = True,
        confirm_callback: Callable[[PermissionRequest], bool] | None = None,
    ):
        """
        Args:
            event_bus: 事件总线（用于发布权限事件）
            rules: 权限规则列表（不传则用默认规则）
            high_risk_auto_approve: 高危操作是否自动通过（Phase 1 默认 True，后续版本切为 False）
            confirm_callback: 确认回调函数（预留给 GUI 使用）
        """
        self._event_bus = event_bus
        self._rules = rules or list(_DEFAULT_RULES)
        self._rule_map: dict[str, PermissionRule] = {}
        self._high_risk_auto_approve = high_risk_auto_approve
        self._confirm_callback = confirm_callback

        # 构建快速查找映射
        self._build_rule_map()

        # 统计
        self._check_count = 0
        self._denied_count = 0
        self._high_risk_count = 0

    def _build_rule_map(self) -> None:
        """构建 tool_name:action_name → rule 映射。"""
        for rule in self._rules:
            key = f"{rule.tool_name}:{rule.action_name}"
            self._rule_map[key] = rule

    def check(self, request: PermissionRequest) -> PermissionResult:
        """检查工具调用的权限。

        Args:
            request: 权限请求

        Returns:
            PermissionResult
        """
        self._check_count += 1

        # 查找匹配规则
        rule = self._find_rule(request.tool_name, request.action_name)

        if rule is None:
            # 没有规则，默认通过
            return PermissionResult(approved=True, risk_level=RiskLevel.LOW)

        request.risk_level = rule.risk_level
        result = PermissionResult(risk_level=rule.risk_level)

        # 根据策略决定
        if rule.policy == ConfirmPolicy.AUTO_APPROVE:
            result.approved = True
            result.reason = "自动通过"

        elif rule.policy == ConfirmPolicy.LOG_ONLY:
            result.approved = True
            result.reason = f"记录并通过 ({rule.description})"
            if rule.risk_level == RiskLevel.HIGH:
                self._high_risk_count += 1
                logger.warning(
                    "⚠️ 高危操作: %s.%s — %s",
                    request.tool_name,
                    request.action_name,
                    rule.description,
                )

        elif rule.policy == ConfirmPolicy.REQUIRE_CONFIRM:
            if self._confirm_callback:
                result.approved = self._confirm_callback(request)
                result.reason = "用户确认" if result.approved else "用户拒绝"
            elif self._high_risk_auto_approve:
                result.approved = True
                result.requires_confirmation = True
                result.reason = "需要确认（当前自动通过）"
                logger.warning(
                    "⚠️ 需确认操作自动通过: %s.%s",
                    request.tool_name,
                    request.action_name,
                )
            else:
                result.approved = False
                result.requires_confirmation = True
                result.reason = "操作需要用户确认"
                self._denied_count += 1

        if not result.approved:
            self._denied_count += 1

        return result

    def _find_rule(self, tool_name: str, action_name: str) -> PermissionRule | None:
        """查找匹配的权限规则。精确匹配优先，通配符次之。"""
        # 精确匹配
        exact_key = f"{tool_name}:{action_name}"
        rule = self._rule_map.get(exact_key)
        if rule:
            return rule
        # 通配符匹配
        wildcard_key = f"{tool_name}:*"
        return self._rule_map.get(wildcard_key)

    # ------------------------------------------------------------------
    # 规则管理
    # ------------------------------------------------------------------

    def add_rule(self, rule: PermissionRule) -> None:
        """添加权限规则。"""
        self._rules.append(rule)
        key = f"{rule.tool_name}:{rule.action_name}"
        self._rule_map[key] = rule

    def remove_rule(self, tool_name: str, action_name: str = "*") -> bool:
        """移除权限规则。"""
        key = f"{tool_name}:{action_name}"
        if key in self._rule_map:
            del self._rule_map[key]
            self._rules = [
                r for r in self._rules
                if not (r.tool_name == tool_name and r.action_name == action_name)
            ]
            return True
        return False

    def list_rules(self) -> list[PermissionRule]:
        """列出所有权限规则。"""
        return list(self._rules)

    def get_rule(self, tool_name: str, action_name: str = "*") -> PermissionRule | None:
        """获取指定规则。"""
        return self._find_rule(tool_name, action_name)

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    @property
    def check_count(self) -> int:
        return self._check_count

    @property
    def denied_count(self) -> int:
        return self._denied_count

    @property
    def high_risk_count(self) -> int:
        return self._high_risk_count

    def get_stats(self) -> dict[str, Any]:
        """获取权限检查统计。"""
        return {
            "total_checks": self._check_count,
            "denied": self._denied_count,
            "high_risk": self._high_risk_count,
            "rules_count": len(self._rules),
        }

    def reset_stats(self) -> None:
        """重置统计。"""
        self._check_count = 0
        self._denied_count = 0
        self._high_risk_count = 0
