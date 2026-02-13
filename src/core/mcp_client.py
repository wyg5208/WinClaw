"""MCP 客户端 — Model Context Protocol 集成。

Phase 4.1 实现：
- MCP 客户端核心（基于 mcp Python SDK）
- 支持 stdio 和 SSE 传输
- 连接池管理
- 工具发现与调用

架构：
用户 / AI Agent
      |
  Skill 层 (= 现有 Workflow 系统，多工具编排)
      |
  Tool 层 (统一接口 BaseTool)
    /        \\
内置 Tool     MCP 桥接层
(shell/file   (连接外部 MCP Server,
 screen 等)    将 MCP tool 转为 BaseTool)
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# MCP SDK 可用性检查
_MCP_AVAILABLE: bool | None = None
_ClientSession = None
_StdioServerParameters = None
_stdio_client = None


def _check_mcp_available() -> bool:
    """检查 MCP SDK 是否可用。"""
    global _MCP_AVAILABLE, _ClientSession, _StdioServerParameters, _stdio_client
    if _MCP_AVAILABLE is not None:
        return _MCP_AVAILABLE

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        _ClientSession = ClientSession
        _StdioServerParameters = StdioServerParameters
        _stdio_client = stdio_client
        _MCP_AVAILABLE = True
        logger.debug("MCP SDK 加载成功")
    except ImportError:
        _MCP_AVAILABLE = False
        logger.debug("MCP SDK 不可用，请安装: pip install mcp")

    return _MCP_AVAILABLE


@dataclass
class MCPServerConfig:
    """MCP Server 配置。"""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    description: str = ""

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MCPServerConfig:
        """从字典创建配置。"""
        return cls(
            name=name,
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
        )


@dataclass
class MCPToolInfo:
    """MCP 工具信息。"""
    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str

    @property
    def full_name(self) -> str:
        """完整工具名（包含 server 前缀）。"""
        return f"{self.server_name}_{self.name}"


class MCPConnection:
    """单个 MCP Server 连接。"""

    def __init__(self, config: MCPServerConfig):
        """初始化连接。

        Args:
            config: Server 配置
        """
        self._config = config
        self._session: Any = None
        self._read_stream = None
        self._write_stream = None
        self._tools: list[MCPToolInfo] = []
        self._connected = False
        self._context_manager = None

    @property
    def server_name(self) -> str:
        return self._config.name

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def tools(self) -> list[MCPToolInfo]:
        return self._tools

    async def connect(self) -> bool:
        """连接到 MCP Server。"""
        if not _check_mcp_available():
            logger.warning("MCP SDK 不可用，无法连接 %s", self._config.name)
            return False

        try:
            # 检查命令是否存在
            if not shutil.which(self._config.command):
                # 对于 npx/uvx，检查 node/python
                if self._config.command in ("npx", "uvx"):
                    pass  # 这些是包管理器命令，后续会处理
                else:
                    logger.warning("MCP Server 命令不存在: %s", self._config.command)
                    return False

            # 创建 stdio 参数
            server_params = _StdioServerParameters(
                command=self._config.command,
                args=self._config.args,
                env=self._config.env or None,
            )

            # 启动客户端
            self._context_manager = _stdio_client(server_params)
            self._read_stream, self._write_stream = await self._context_manager.__aenter__()

            # 创建会话
            self._session = _ClientSession(self._read_stream, self._write_stream)
            await self._session.__aenter__()

            # 初始化
            await self._session.initialize()

            # 获取工具列表
            await self._fetch_tools()

            self._connected = True
            logger.info(
                "已连接 MCP Server: %s (%d 个工具)",
                self._config.name, len(self._tools)
            )
            return True

        except Exception as e:
            logger.error("连接 MCP Server %s 失败: %s", self._config.name, e)
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """断开连接。"""
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
                self._session = None
            if self._context_manager:
                await self._context_manager.__aexit__(None, None, None)
                self._context_manager = None
        except Exception as e:
            logger.warning("断开 MCP 连接时出错: %s", e)
        finally:
            self._read_stream = None
            self._write_stream = None
            self._connected = False
            self._tools = []
            logger.info("已断开 MCP Server: %s", self._config.name)

    async def _fetch_tools(self) -> None:
        """获取 Server 提供的工具列表。"""
        if not self._session:
            return

        try:
            result = await self._session.list_tools()
            self._tools = []

            for tool in result.tools:
                self._tools.append(MCPToolInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema or {},
                    server_name=self._config.name,
                ))

        except Exception as e:
            logger.error("获取 MCP 工具列表失败: %s", e)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """调用 MCP 工具。

        Args:
            tool_name: 工具名称
            arguments: 参数字典

        Returns:
            工具返回结果
        """
        if not self._session or not self._connected:
            raise RuntimeError(f"MCP Server {self._config.name} 未连接")

        try:
            result = await self._session.call_tool(tool_name, arguments)

            # 处理结果
            if result.content:
                # 合并所有内容
                text_parts = []
                for content in result.content:
                    if hasattr(content, "text"):
                        text_parts.append(content.text)
                    elif hasattr(content, "data"):
                        text_parts.append(str(content.data))

                return "\n".join(text_parts) if text_parts else str(result)

            return str(result)

        except Exception as e:
            logger.error("调用 MCP 工具 %s.%s 失败: %s", self._config.name, tool_name, e)
            raise


class MCPClientManager:
    """MCP 客户端管理器，管理多个 MCP Server 连接。"""

    def __init__(self):
        """初始化管理器。"""
        self._connections: dict[str, MCPConnection] = {}
        self._tool_to_server: dict[str, str] = {}  # tool_full_name -> server_name

    @property
    def connections(self) -> dict[str, MCPConnection]:
        return self._connections

    async def connect_server(self, config: MCPServerConfig) -> bool:
        """连接到 MCP Server。

        Args:
            config: Server 配置

        Returns:
            是否成功
        """
        if config.name in self._connections:
            logger.warning("MCP Server %s 已连接", config.name)
            return True

        connection = MCPConnection(config)
        success = await connection.connect()

        if success:
            self._connections[config.name] = connection
            # 注册工具映射
            for tool in connection.tools:
                self._tool_to_server[tool.full_name] = config.name

        return success

    async def disconnect_server(self, server_name: str) -> bool:
        """断开指定 Server。

        Args:
            server_name: Server 名称

        Returns:
            是否成功
        """
        if server_name not in self._connections:
            return False

        connection = self._connections.pop(server_name)
        await connection.disconnect()

        # 清理工具映射
        self._tool_to_server = {
            k: v for k, v in self._tool_to_server.items()
            if v != server_name
        }

        return True

    async def disconnect_all(self) -> None:
        """断开所有连接。"""
        for name in list(self._connections.keys()):
            await self.disconnect_server(name)

    def get_all_tools(self) -> list[MCPToolInfo]:
        """获取所有已连接 Server 的工具列表。"""
        tools = []
        for conn in self._connections.values():
            tools.extend(conn.tools)
        return tools

    def get_tool(self, tool_full_name: str) -> MCPToolInfo | None:
        """根据完整名称获取工具信息。"""
        server_name = self._tool_to_server.get(tool_full_name)
        if not server_name:
            return None

        conn = self._connections.get(server_name)
        if not conn:
            return None

        # 工具名格式: server_toolname
        tool_name = tool_full_name.split("_", 1)[1] if "_" in tool_full_name else tool_full_name
        for tool in conn.tools:
            if tool.name == tool_name:
                return tool

        return None

    async def call_tool(self, tool_full_name: str, arguments: dict[str, Any]) -> Any:
        """调用工具。

        Args:
            tool_full_name: 完整工具名（server_toolname）
            arguments: 参数

        Returns:
            工具返回结果
        """
        server_name = self._tool_to_server.get(tool_full_name)
        if not server_name:
            raise ValueError(f"未知的工具: {tool_full_name}")

        conn = self._connections.get(server_name)
        if not conn:
            raise RuntimeError(f"MCP Server {server_name} 未连接")

        # 提取实际工具名
        tool_name = tool_full_name.split("_", 1)[1] if "_" in tool_full_name else tool_full_name

        return await conn.call_tool(tool_name, arguments)

    def is_connected(self, server_name: str) -> bool:
        """检查指定 Server 是否已连接。"""
        conn = self._connections.get(server_name)
        return conn is not None and conn.is_connected
