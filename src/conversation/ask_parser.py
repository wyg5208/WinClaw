"""AI追问标记解析器。

解析AI输出中的特殊标记，识别追问意图。
支持：选项选择、确认询问、自由输入询问。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AskType(Enum):
    """追问类型枚举。"""
    NONE = "none"       # 非追问
    CHOICE = "choice"   # 选项选择
    CONFIRM = "confirm" # 确认询问
    INPUT = "input"     # 自由输入


class TimeoutStrategy(Enum):
    """超时处理策略枚举。"""
    AUTO_SELECT = "auto_select"   # 自动选择推荐答案
    WAIT_FOREVER = "wait_forever" # 永远等待
    RETRY = "retry"               # 重试一次后放弃
    DEFAULT = "default"           # 使用默认值
    SKIP = "skip"                # 跳过该步骤


@dataclass
class AskIntent:
    """追问意图数据结构。"""
    type: AskType                      # 追问类型
    question: str                      # 问题文本
    options: list[str]                 # 选项列表（仅CHOICE类型）
    recommended: str | None            # 推荐答案（仅CHOICE类型）
    timeout_strategy: TimeoutStrategy  # 超时策略
    timeout_seconds: int               # 超时秒数
    raw_markup: str                    # 原始标记文本


class AskParser:
    """AI输出追问标记解析器。

    解析AI输出中的特殊标记：
    - <|ASK_CHOICE|>选项列表<|/ASK_CHOICE|>
    - <|ASK_CONFIRM|>问题文本<|/ASK_CONFIRM|>
    - <|ASK_INPUT|>提示文本<|/ASK_INPUT|>
    - <|TIMEOUT|>策略<|/TIMEOUT|>
    """

    # 标记模式
    PATTERNS = {
        AskType.CHOICE: re.compile(
            r'<\|ASK_CHOICE\|>(.*?)<\|/ASK_CHOICE\|>',
            re.DOTALL | re.IGNORECASE
        ),
        AskType.CONFIRM: re.compile(
            r'<\|ASK_CONFIRM\|>(.*?)<\|/ASK_CONFIRM\|>',
            re.DOTALL | re.IGNORECASE
        ),
        AskType.INPUT: re.compile(
            r'<\|ASK_INPUT\|>(.*?)<\|/ASK_INPUT\|>',
            re.DOTALL | re.IGNORECASE
        ),
        TimeoutStrategy.AUTO_SELECT: re.compile(
            r'<\|TIMEOUT\|>\s*auto_select\s*(.*?)\s*<\|/TIMEOUT\|>',
            re.DOTALL | re.IGNORECASE
        ),
        TimeoutStrategy.WAIT_FOREVER: re.compile(
            r'<\|TIMEOUT\|>\s*wait_forever\s*<\|/TIMEOUT\|>',
            re.IGNORECASE
        ),
        TimeoutStrategy.RETRY: re.compile(
            r'<\|TIMEOUT\|>\s*retry\s*<\|/TIMEOUT\|>',
            re.IGNORECASE
        ),
        TimeoutStrategy.DEFAULT: re.compile(
            r'<\|TIMEOUT\|>\s*default\s*(.*?)\s*<\|/TIMEOUT\|>',
            re.DOTALL | re.IGNORECASE
        ),
        TimeoutStrategy.SKIP: re.compile(
            r'<\|TIMEOUT\|>\s*skip\s*<\|/TIMEOUT\|>',
            re.IGNORECASE
        ),
    }

    # 选项列表模式（支持多种格式）
    OPTIONS_PATTERN = re.compile(
        r'["\[\]]([^"\]]+)["\]]|'
        r'(?:^|[\s,，])([^[\s,，]+?)(?=[\s,，]|$)',
        re.MULTILINE
    )

    def __init__(self, default_timeout: int = 30):
        """初始化解析器。

        Args:
            default_timeout: 默认超时秒数
        """
        self._default_timeout = default_timeout

    def parse(self, text: str) -> Optional[AskIntent]:
        """解析AI输出文本，提取追问意图。

        Args:
            text: AI输出的文本

        Returns:
            AskIntent对象，如果没有追问标记则返回None
        """
        if not text:
            return None

        # 尝试解析各种类型
        intent = self._try_parse_choice(text)
        if intent:
            return intent

        intent = self._try_parse_confirm(text)
        if intent:
            return intent

        intent = self._try_parse_input(text)
        if intent:
            return intent

        return None

    def parse_without_markup(self, text: str) -> tuple[str, Optional[AskIntent]]:
        """解析文本并移除追问标记。

        Args:
            text: AI输出的文本

        Returns:
            (清理后的文本, 追问意图)
        """
        intent = self.parse(text)

        if intent is None:
            return text, None

        # 移除追问标记，保留纯文本
        cleaned = text
        for ask_type in AskType:
            if ask_type != AskType.NONE:
                pattern = self.PATTERNS.get(ask_type)
                if pattern:
                    cleaned = pattern.sub('', cleaned)

        # 移除超时标记
        for strategy in TimeoutStrategy:
            pattern = self.PATTERNS.get(strategy)
            if pattern:
                cleaned = pattern.sub('', cleaned)

        # 清理多余空白
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = cleaned.strip()

        return cleaned, intent

    def _try_parse_choice(self, text: str) -> Optional[AskIntent]:
        """尝试解析选项追问。"""
        match = self.PATTERNS[AskType.CHOICE].search(text)
        if not match:
            return None

        content = match.group(1).strip()
        raw_markup = match.group(0)

        # 提取推荐答案
        recommended = self._extract_recommended(content)

        # 提取选项列表
        options = self._extract_options(content)

        # 提取超时策略
        timeout_strategy, timeout_seconds = self._extract_timeout(text)

        # 获取问题文本（追问标记前的内容）
        question = text[:match.start()].strip()
        if not question:
            question = "请选择一个选项："

        logger.info(f"解析到选项追问: {options}, 推荐: {recommended}")

        return AskIntent(
            type=AskType.CHOICE,
            question=question,
            options=options,
            recommended=recommended,
            timeout_strategy=timeout_strategy,
            timeout_seconds=timeout_seconds,
            raw_markup=raw_markup,
        )

    def _try_parse_confirm(self, text: str) -> Optional[AskIntent]:
        """尝试解析确认追问。"""
        match = self.PATTERNS[AskType.CONFIRM].search(text)
        if not match:
            return None

        content = match.group(1).strip()
        raw_markup = match.group(0)

        # 确认追问没有选项
        options = []

        # 提取超时策略
        timeout_strategy, timeout_seconds = self._extract_timeout(text)

        # 问题文本
        question = text[:match.start()].strip()
        if not question:
            question = content

        logger.info(f"解析到确认追问: {question}")

        return AskIntent(
            type=AskType.CONFIRM,
            question=question,
            options=options,
            recommended=None,
            timeout_strategy=timeout_strategy,
            timeout_seconds=timeout_seconds,
            raw_markup=raw_markup,
        )

    def _try_parse_input(self, text: str) -> Optional[AskIntent]:
        """尝试解析输入追问。"""
        match = self.PATTERNS[AskType.INPUT].search(text)
        if not match:
            return None

        content = match.group(1).strip()
        raw_markup = match.group(0)

        # 输入追问没有预定义选项
        options = []

        # 提取超时策略
        timeout_strategy, timeout_seconds = self._extract_timeout(text)

        # 问题文本
        question = text[:match.start()].strip()
        if not question:
            question = content

        logger.info(f"解析到输入追问: {question}")

        return AskIntent(
            type=AskType.INPUT,
            question=question,
            options=options,
            recommended=None,
            timeout_strategy=timeout_strategy,
            timeout_seconds=timeout_seconds,
            raw_markup=raw_markup,
        )

    def _extract_options(self, content: str) -> list[str]:
        """从内容中提取选项列表。"""
        options = []

        # 尝试JSON数组格式
        if '[' in content and ']' in content:
            json_match = re.search(r'\[(.*?)\]', content, re.DOTALL)
            if json_match:
                array_content = json_match.group(1)
                # 提取引号内的字符串
                quoted = re.findall(r'"([^"]+)"', array_content)
                if quoted:
                    return [opt.strip() for opt in quoted]

        # 尝试 A) B) C) 格式
        letter_options = re.findall(r'([A-Za-z])\)\s*([^[\n]+)', content)
        if letter_options:
            return [opt.strip() for _, opt in letter_options]

        # 尝试 1. 2. 3. 格式
        numbered_options = re.findall(r'\d+[\.、]\s*([^\n]+)', content)
        if numbered_options:
            return [opt.strip() for opt in numbered_options]

        # 尝试逗号分隔
        if ',' in content or '，' in content:
            parts = re.split(r'[,，]', content)
            return [opt.strip() for opt in parts if opt.strip()]

        return options

    def _extract_recommended(self, content: str) -> Optional[str]:
        """从内容中提取推荐答案。"""
        # 查找 "推荐" 关键词后的内容
        recommend_patterns = [
            r'推荐[：:]\s*([^[\n]+)',
            r'建议[：:]\s*([^[\n]+)',
            r'默认[：:]\s*([^[\n]+)',
        ]

        for pattern in recommend_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # 如果没有明确推荐，取第一个选项
        options = self._extract_options(content)
        if options:
            return options[0]

        return None

    def _extract_timeout(self, text: str) -> tuple[TimeoutStrategy, int]:
        """提取超时策略和秒数。"""
        # 尝试每种策略
        for strategy in [
            TimeoutStrategy.AUTO_SELECT,
            TimeoutStrategy.WAIT_FOREVER,
            TimeoutStrategy.RETRY,
            TimeoutStrategy.DEFAULT,
            TimeoutStrategy.SKIP,
        ]:
            pattern = self.PATTERNS.get(strategy)
            if pattern and pattern.search(text):
                # 提取秒数（如果有）
                seconds_match = re.search(r'(\d+)\s*秒', text)
                seconds = int(seconds_match.group(1)) if seconds_match else self._default_timeout
                return strategy, seconds

        return TimeoutStrategy.AUTO_SELECT, self._default_timeout
