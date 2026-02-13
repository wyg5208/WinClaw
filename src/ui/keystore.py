"""API Key 安全存储模块。

使用 keyring 库（Windows DPAPI 后端）实现密钥的加密存储与读取。
API Key 不以明文形式存储在磁盘任何位置。

功能：
- 保存 / 读取 / 删除 API Key
- 列出所有已存储的服务名
- 首次启动检测与引导
- 环境变量自动注入
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# keyring 服务命名空间
_SERVICE_PREFIX = "WinClaw"

# 支持的 API Key 条目
API_KEY_ENTRIES: list[dict[str, str]] = [
    {"env": "DEEPSEEK_API_KEY", "label": "DeepSeek API Key", "hint": "sk-..."},
    {"env": "OPENAI_API_KEY", "label": "OpenAI API Key", "hint": "sk-..."},
    {"env": "ANTHROPIC_API_KEY", "label": "Anthropic API Key", "hint": "sk-ant-..."},
    {"env": "GEMINI_API_KEY", "label": "Google Gemini API Key", "hint": "AI..."},
]


def _service_name(env_var: str) -> str:
    """构造 keyring 服务名。"""
    return f"{_SERVICE_PREFIX}/{env_var}"


def save_key(env_var: str, value: str) -> bool:
    """保存 API Key 到安全存储。"""
    try:
        import keyring

        keyring.set_password(_service_name(env_var), env_var, value)
        logger.info("已保存密钥: %s", env_var)
        return True
    except Exception as e:
        logger.error("保存密钥失败 %s: %s", env_var, e)
        return False


def load_key(env_var: str) -> str | None:
    """从安全存储读取 API Key。"""
    try:
        import keyring

        value = keyring.get_password(_service_name(env_var), env_var)
        return value
    except Exception as e:
        logger.error("读取密钥失败 %s: %s", env_var, e)
        return None


def delete_key(env_var: str) -> bool:
    """从安全存储删除 API Key。"""
    try:
        import keyring

        keyring.delete_password(_service_name(env_var), env_var)
        logger.info("已删除密钥: %s", env_var)
        return True
    except Exception as e:
        logger.error("删除密钥失败 %s: %s", env_var, e)
        return False


def has_key(env_var: str) -> bool:
    """检查是否已存储指定密钥。"""
    return load_key(env_var) is not None


def list_stored_keys() -> list[str]:
    """列出所有已存储密钥的环境变量名。"""
    return [e["env"] for e in API_KEY_ENTRIES if has_key(e["env"])]


def inject_keys_to_env() -> int:
    """将所有已存储的密钥注入到当前进程环境变量。

    仅在环境变量尚未设置时注入（不覆盖已有值）。

    Returns:
        成功注入的密钥数量
    """
    injected = 0
    for entry in API_KEY_ENTRIES:
        env_var = entry["env"]
        # 已有环境变量则跳过
        if os.environ.get(env_var):
            continue
        value = load_key(env_var)
        if value:
            os.environ[env_var] = value
            injected += 1
            logger.info("已注入密钥到环境变量: %s", env_var)
    return injected


def mask_key(value: str) -> str:
    """遮蔽 API Key 用于展示（只显示前 4 位和后 4 位）。"""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def needs_setup() -> bool:
    """检查是否需要首次配置（没有任何密钥存储）。"""
    for entry in API_KEY_ENTRIES:
        env_var = entry["env"]
        if os.environ.get(env_var) or has_key(env_var):
            return False
    return True
