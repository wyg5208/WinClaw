"""MCP 安全策略 — 管理 MCP Server 信任和确认。

Phase 4.1 实现：
- 首次调用确认机制
- Server 信任白名单
- 风险等级管理
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认信任配置文件路径
DEFAULT_TRUST_FILE = Path.home() / ".winclaw" / "mcp_trust.json"

# 默认风险等级
RISK_LEVELS = {
    "high": "高风险 - 外部进程，存在安全风险",
    "medium": "中风险 - 可能涉及敏感操作",
    "low": "低风险 - 只读操作",
}


@dataclass
class MCPServerTrust:
    """MCP Server 信任信息。"""
    server_name: str
    trusted: bool = False
    trusted_at: str = ""
    risk_level: str = "high"

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "trusted": self.trusted,
            "trusted_at": self.trusted_at,
            "risk_level": self.risk_level,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPServerTrust:
        return cls(
            server_name=data.get("server_name", ""),
            trusted=data.get("trusted", False),
            trusted_at=data.get("trusted_at", ""),
            risk_level=data.get("risk_level", "high"),
        )


class MCPSecurityManager:
    """MCP 安全管理器。"""

    def __init__(self, trust_file: Path | None = None):
        """初始化安全管理器。

        Args:
            trust_file: 信任配置文件路径
        """
        self._trust_file = trust_file or DEFAULT_TRUST_FILE
        self._trust_data: dict[str, MCPServerTrust] = {}
        self._load_trust_data()

    def _load_trust_data(self) -> None:
        """加载信任数据。"""
        if not self._trust_file.exists():
            self._trust_file.parent.mkdir(parents=True, exist_ok=True)
            return

        try:
            with open(self._trust_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for server_name, trust_info in data.get("servers", {}).items():
                self._trust_data[server_name] = MCPServerTrust.from_dict(trust_info)

            logger.debug("加载了 %d 个 MCP Server 信任记录", len(self._trust_data))

        except Exception as e:
            logger.warning("加载 MCP 信任数据失败: %s", e)

    def _save_trust_data(self) -> None:
        """保存信任数据。"""
        try:
            data = {
                "servers": {
                    name: trust.to_dict()
                    for name, trust in self._trust_data.items()
                }
            }

            self._trust_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._trust_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.warning("保存 MCP 信任数据失败: %s", e)

    def is_trusted(self, server_name: str) -> bool:
        """检查 Server 是否已被信任。"""
        trust = self._trust_data.get(server_name)
        return trust is not None and trust.trusted

    def trust_server(self, server_name: str, risk_level: str = "high") -> None:
        """信任指定 Server。

        Args:
            server_name: Server 名称
            risk_level: 风险等级
        """
        from datetime import datetime

        self._trust_data[server_name] = MCPServerTrust(
            server_name=server_name,
            trusted=True,
            trusted_at=datetime.now().isoformat(),
            risk_level=risk_level,
        )
        self._save_trust_data()
        logger.info("已信任 MCP Server: %s", server_name)

    def revoke_trust(self, server_name: str) -> bool:
        """撤销 Server 信任。

        Args:
            server_name: Server 名称

        Returns:
            是否成功撤销
        """
        if server_name in self._trust_data:
            del self._trust_data[server_name]
            self._save_trust_data()
            logger.info("已撤销 MCP Server 信任: %s", server_name)
            return True
        return False

    def get_risk_level(self, server_name: str) -> str:
        """获取 Server 的风险等级。

        Args:
            server_name: Server 名称

        Returns:
            风险等级
        """
        trust = self._trust_data.get(server_name)
        return trust.risk_level if trust else "high"

    def set_risk_level(self, server_name: str, risk_level: str) -> None:
        """设置 Server 的风险等级。

        Args:
            server_name: Server 名称
            risk_level: 风险等级
        """
        if server_name in self._trust_data:
            self._trust_data[server_name].risk_level = risk_level
            self._save_trust_data()

    def needs_confirmation(self, server_name: str) -> bool:
        """检查是否需要确认。

        Args:
            server_name: Server 名称

        Returns:
            是否需要确认
        """
        # 如果已被信任，不需要确认
        if self.is_trusted(server_name):
            return False

        # 高风险 Server 需要确认
        risk = self.get_risk_level(server_name)
        return risk == "high"

    def get_confirmation_message(
        self,
        server_name: str,
        tool_name: str,
        operation: str = "执行操作",
    ) -> str:
        """获取确认消息。

        Args:
            server_name: Server 名称
            tool_name: 工具名称
            operation: 操作描述

        Returns:
            确认消息
        """
        risk = self.get_risk_level(server_name)
        risk_desc = RISK_LEVELS.get(risk, "未知风险")

        return (
            f"即将通过 [{server_name}] MCP Server 执行 [{tool_name}] 操作。\n\n"
            f"该 Server 风险等级: {risk_desc}\n\n"
            f"MCP Server 由第三方提供，是否继续？"
        )

    def get_all_trusted_servers(self) -> list[str]:
        """获取所有已信任的 Server 列表。"""
        return [
            name for name, trust in self._trust_data.items()
            if trust.trusted
        ]

    def get_all_servers(self) -> dict[str, MCPServerTrust]:
        """获取所有 Server 信任信息。"""
        return dict(self._trust_data)


# 全局单例
_security_manager: MCPSecurityManager | None = None


def get_security_manager() -> MCPSecurityManager:
    """获取安全管理器单例。"""
    global _security_manager
    if _security_manager is None:
        _security_manager = MCPSecurityManager()
    return _security_manager
