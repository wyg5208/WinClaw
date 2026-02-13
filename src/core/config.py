"""配置系统 — 加载、合并、覆盖应用配置。

支持三层配置来源（优先级由低到高）：
1. 默认配置文件 config/default.toml
2. 用户配置文件 ~/.winclaw/config.toml（可选）
3. 环境变量 WINCLAW_* 覆盖

环境变量映射规则：
    WINCLAW_AGENT_DEFAULT_MODEL  →  config["agent"]["default_model"]
    WINCLAW_SHELL_TIMEOUT        →  config["shell"]["timeout"]
    即：WINCLAW_{SECTION}_{KEY}  →  config[section][key]
"""

from __future__ import annotations

import logging
import os
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认配置文件路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "default.toml"
_USER_CONFIG_DIR = Path.home() / ".winclaw"
_USER_CONFIG_PATH = _USER_CONFIG_DIR / "config.toml"

# 环境变量前缀
_ENV_PREFIX = "WINCLAW_"


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 覆盖 base。"""
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _coerce_value(value: str, existing: Any = None) -> Any:
    """将环境变量字符串转为合适的 Python 类型。

    如果有已存在的值作参考，则尽量匹配其类型。
    """
    # 布尔值
    if value.lower() in ("true", "1", "yes", "on"):
        return True
    if value.lower() in ("false", "0", "no", "off"):
        return False

    # 如果已有值是 int，尝试转换
    if isinstance(existing, int):
        try:
            return int(value)
        except ValueError:
            pass

    # 如果已有值是 float，尝试转换
    if isinstance(existing, float):
        try:
            return float(value)
        except ValueError:
            pass

    # 尝试 int / float
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass

    return value


class AppConfig:
    """应用配置管理器。

    使用方法::

        config = AppConfig.load()
        model = config.get("agent.default_model")
        config.set("agent.max_steps", 20)
    """

    def __init__(self, data: dict[str, Any] | None = None):
        self._data: dict[str, Any] = data or {}

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        default_path: Path | None = None,
        user_path: Path | None = None,
        apply_env: bool = True,
    ) -> "AppConfig":
        """加载并合并配置。

        Args:
            default_path: 默认配置文件路径
            user_path: 用户配置文件路径
            apply_env: 是否应用环境变量覆盖

        Returns:
            合并后的 AppConfig 实例
        """
        data: dict[str, Any] = {}

        # 1. 加载默认配置
        dp = default_path or _DEFAULT_CONFIG_PATH
        if dp.exists():
            data = cls._load_toml(dp)
            logger.info("已加载默认配置: %s", dp)
        else:
            logger.warning("默认配置文件不存在: %s", dp)

        # 2. 合并用户配置
        up = user_path or _USER_CONFIG_PATH
        if up.exists():
            user_data = cls._load_toml(up)
            data = _deep_merge(data, user_data)
            logger.info("已合并用户配置: %s", up)

        # 3. 应用环境变量覆盖
        if apply_env:
            env_overrides = cls._collect_env_overrides(data)
            if env_overrides:
                data = _deep_merge(data, env_overrides)
                logger.info("已应用 %d 个环境变量覆盖", len(env_overrides))

        return cls(data)

    @staticmethod
    def _load_toml(path: Path) -> dict[str, Any]:
        """加载 TOML 文件。"""
        with open(path, "rb") as f:
            return tomllib.load(f)

    @staticmethod
    def _collect_env_overrides(current_data: dict[str, Any]) -> dict[str, Any]:
        """收集 WINCLAW_* 环境变量并转为嵌套字典。

        规则: WINCLAW_SECTION_KEY → {"section": {"key": value}}
        """
        overrides: dict[str, Any] = {}
        for env_key, env_value in os.environ.items():
            if not env_key.startswith(_ENV_PREFIX):
                continue
            # 去掉前缀，拆分为 section + key
            remainder = env_key[len(_ENV_PREFIX):].lower()
            parts = remainder.split("_", 1)
            if len(parts) != 2:
                logger.debug("忽略环境变量 %s（格式不匹配 WINCLAW_SECTION_KEY）", env_key)
                continue

            section, key = parts

            # 根据已有配置中的类型进行类型推断
            existing_value = current_data.get(section, {}).get(key)
            typed_value = _coerce_value(env_value, existing_value)

            if section not in overrides:
                overrides[section] = {}
            overrides[section][key] = typed_value
            logger.debug("环境变量覆盖: %s.%s = %r", section, key, typed_value)

        return overrides

    # ------------------------------------------------------------------
    # 访问
    # ------------------------------------------------------------------

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """通过点号分隔的路径获取配置值。

        示例::

            config.get("agent.default_model")       → "deepseek-chat"
            config.get("shell.timeout")              → 30
            config.get("app.nonexistent", "fallback") → "fallback"
        """
        keys = dotted_key.split(".")
        node: Any = self._data
        for k in keys:
            if isinstance(node, dict):
                node = node.get(k)
            else:
                return default
            if node is None:
                return default
        return node

    def get_section(self, section: str) -> dict[str, Any]:
        """获取整个配置节。"""
        val = self._data.get(section)
        if isinstance(val, dict):
            return deepcopy(val)
        return {}

    def set(self, dotted_key: str, value: Any) -> None:
        """运行时设置配置值。

        示例::

            config.set("agent.max_steps", 20)
        """
        keys = dotted_key.split(".")
        node = self._data
        for k in keys[:-1]:
            if k not in node or not isinstance(node[k], dict):
                node[k] = {}
            node = node[k]
        node[keys[-1]] = value

    @property
    def data(self) -> dict[str, Any]:
        """返回完整配置字典的只读副本。"""
        return deepcopy(self._data)

    # ------------------------------------------------------------------
    # 便捷属性
    # ------------------------------------------------------------------

    @property
    def app_name(self) -> str:
        return self.get("app.name", "WinClaw")

    @property
    def app_version(self) -> str:
        return self.get("app.version", "0.1.0")

    @property
    def log_level(self) -> str:
        return self.get("app.log_level", "INFO")

    @property
    def data_dir(self) -> Path:
        raw = self.get("app.data_dir", "~/.winclaw")
        return Path(raw).expanduser()

    @property
    def default_model(self) -> str:
        return self.get("agent.default_model", "deepseek-chat")

    @property
    def max_steps(self) -> int:
        return self.get("agent.max_steps", 15)

    @property
    def max_tokens_per_task(self) -> int:
        return self.get("agent.max_tokens_per_task", 50000)

    @property
    def system_prompt(self) -> str:
        return self.get("agent.system_prompt", "")

    @property
    def shell_timeout(self) -> int:
        return self.get("shell.timeout", 30)

    @property
    def shell_max_output(self) -> int:
        return self.get("shell.max_output_length", 10000)

    @property
    def file_max_read_size(self) -> int:
        return self.get("file.max_read_size", 1_048_576)

    @property
    def screen_quality(self) -> int:
        return self.get("screen.quality", 85)

    @property
    def screen_max_width(self) -> int:
        return self.get("screen.max_width", 1920)

    @property
    def whisper_model(self) -> str:
        return self.get("voice.whisper_model", "base")

    @property
    def voice_language(self) -> str:
        return self.get("voice.default_language", "zh")

    @property
    def voice_record_duration(self) -> int:
        return self.get("voice.record_duration", 5)

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        sections = list(self._data.keys())
        return f"AppConfig(sections={sections})"
