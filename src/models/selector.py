"""模型选择策略 — 根据不同策略自动选择最佳模型。

支持三种选择策略：
1. SPECIFIED   — 用户指定模型键名，直接使用
2. CAPABILITY  — 按能力匹配，选择满足要求中成本最低的模型
3. COST_FIRST  — 成本优先，在所有可用模型中选成本最低的
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.models.registry import ModelConfig, ModelRegistry

logger = logging.getLogger(__name__)


class SelectionStrategy(str, Enum):
    """模型选择策略枚举。"""

    SPECIFIED = "specified"  # 用户指定
    CAPABILITY = "capability"  # 能力匹配（满足需求 + 成本最低）
    COST_FIRST = "cost_first"  # 成本优先


@dataclass
class SelectionCriteria:
    """模型选择条件。"""

    needs_function_calling: bool = False
    needs_image: bool = False
    preferred_provider: str = ""  # 优先选择的提供商
    preferred_tag: str = ""  # 优先匹配的标签
    exclude_local: bool = False  # 排除本地模型
    max_cost_input: float = 0.0  # 最大输入成本（0=不限）
    min_context_window: int = 0  # 最小上下文窗口（0=不限）


class ModelSelector:
    """模型选择器。根据策略和条件从注册中心选择模型。"""

    def __init__(self, registry: ModelRegistry, default_model: str = "deepseek-chat"):
        self._registry = registry
        self._default_model = default_model

    @property
    def default_model(self) -> str:
        return self._default_model

    @default_model.setter
    def default_model(self, value: str) -> None:
        if self._registry.get(value) is None:
            raise ValueError(f"模型不存在: {value}")
        self._default_model = value

    def select(
        self,
        strategy: SelectionStrategy = SelectionStrategy.SPECIFIED,
        model_key: str = "",
        criteria: SelectionCriteria | None = None,
    ) -> ModelConfig:
        """选择模型。

        Args:
            strategy: 选择策略
            model_key: 当策略为 SPECIFIED 时使用的模型键名
            criteria: 当策略为 CAPABILITY/COST_FIRST 时的筛选条件

        Returns:
            ModelConfig

        Raises:
            ValueError: 找不到满足条件的模型
        """
        if strategy == SelectionStrategy.SPECIFIED:
            return self._select_specified(model_key)
        elif strategy == SelectionStrategy.CAPABILITY:
            return self._select_by_capability(criteria or SelectionCriteria())
        elif strategy == SelectionStrategy.COST_FIRST:
            return self._select_cost_first(criteria or SelectionCriteria())
        else:
            raise ValueError(f"未知策略: {strategy}")

    def select_for_task(
        self,
        *,
        needs_function_calling: bool = True,
        needs_image: bool = False,
        model_key: str = "",
    ) -> ModelConfig:
        """便捷方法：为任务选择模型。

        如果指定了 model_key 且有效，直接使用。
        否则按能力匹配 + 成本最低选择。

        Args:
            needs_function_calling: 是否需要 function calling 能力
            needs_image: 是否需要图片输入
            model_key: 优先使用的模型键名

        Returns:
            ModelConfig
        """
        # 优先用指定模型
        if model_key:
            cfg = self._registry.get(model_key)
            if cfg is not None:
                return cfg

        # 尝试默认模型
        default_cfg = self._registry.get(self._default_model)
        if default_cfg is not None:
            # 检查默认模型是否满足条件
            if needs_function_calling and not default_cfg.supports_function_calling:
                pass  # 不满足，继续找
            elif needs_image and not default_cfg.supports_image:
                pass  # 不满足，继续找
            else:
                return default_cfg

        # 按能力+成本选择
        criteria = SelectionCriteria(
            needs_function_calling=needs_function_calling,
            needs_image=needs_image,
        )
        return self._select_by_capability(criteria)

    # ------------------------------------------------------------------
    # 私有策略实现
    # ------------------------------------------------------------------

    def _select_specified(self, model_key: str) -> ModelConfig:
        """策略1: 直接指定。"""
        key = model_key or self._default_model
        cfg = self._registry.get(key)
        if cfg is None:
            raise ValueError(
                f"模型 '{key}' 不存在。可用模型: "
                + ", ".join(m.key for m in self._registry.list_models())
            )
        return cfg

    def _select_by_capability(self, criteria: SelectionCriteria) -> ModelConfig:
        """策略2: 能力匹配 + 成本最低。"""
        candidates = self._filter_candidates(criteria)
        if not candidates:
            raise ValueError(
                f"没有找到满足条件的模型: "
                f"FC={criteria.needs_function_calling}, "
                f"image={criteria.needs_image}"
            )

        # 优先选择匹配 provider 的
        if criteria.preferred_provider:
            preferred = [
                c for c in candidates if c.provider == criteria.preferred_provider
            ]
            if preferred:
                candidates = preferred

        # 优先选择匹配 tag 的
        if criteria.preferred_tag:
            tagged = [c for c in candidates if criteria.preferred_tag in c.tags]
            if tagged:
                candidates = tagged

        # 按成本排序（输入+输出的加权平均）
        candidates.sort(key=lambda m: m.cost_input + m.cost_output)

        selected = candidates[0]
        logger.info(
            "能力匹配选择模型: %s (%s) — 成本 $%.2f/$%.2f per M tokens",
            selected.key,
            selected.name,
            selected.cost_input,
            selected.cost_output,
        )
        return selected

    def _select_cost_first(self, criteria: SelectionCriteria) -> ModelConfig:
        """策略3: 成本优先（不考虑能力限制）。"""
        all_models = self._registry.list_models()
        if not all_models:
            raise ValueError("没有任何可用模型")

        candidates = list(all_models)

        # 如果排除本地模型
        if criteria.exclude_local:
            candidates = [m for m in candidates if not m.is_local]

        if not candidates:
            raise ValueError("排除本地模型后没有可用模型")

        # 按总成本排序
        candidates.sort(key=lambda m: m.cost_input + m.cost_output)

        selected = candidates[0]
        logger.info(
            "成本优先选择模型: %s (%s) — 成本 $%.2f/$%.2f per M tokens",
            selected.key,
            selected.name,
            selected.cost_input,
            selected.cost_output,
        )
        return selected

    def _filter_candidates(self, criteria: SelectionCriteria) -> list[ModelConfig]:
        """根据条件筛选候选模型。"""
        candidates = []
        for m in self._registry.list_models():
            if criteria.needs_function_calling and not m.supports_function_calling:
                continue
            if criteria.needs_image and not m.supports_image:
                continue
            if criteria.exclude_local and m.is_local:
                continue
            if criteria.max_cost_input > 0 and m.cost_input > criteria.max_cost_input:
                continue
            if criteria.min_context_window > 0 and m.context_window < criteria.min_context_window:
                continue
            candidates.append(m)
        return candidates
