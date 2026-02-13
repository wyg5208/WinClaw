"""MCP 工具桥接 — 将 MCP Server 工具包装为 BaseTool。

Phase 4.1 实现：
- 将 MCP tool 转换为 WinClaw BaseTool
- Schema 自动转换
- 调用结果转换
"""

from __future__ import annotations

import logging
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


class MCPBridgeTool(BaseTool):
    """MCP 工具桥接类。

    将单个 MCP Server 的所有工具包装为一个 BaseTool。
    每个 MCP Server 对应一个 MCPBridgeTool 实例。
    """

    def __init__(
        self,
        server_name: str,
        mcp_manager: Any,  # MCPClientManager
        tools: list[Any],  # list[MCPToolInfo]
    ):
        """初始化桥接工具。

        Args:
            server_name: MCP Server 名称
            mcp_manager: MCP 客户端管理器
            tools: 该 Server 提供的工具列表
        """
        self._server_name = server_name
        self._mcp_manager = mcp_manager
        self._mcp_tools = {t.name: t for t in tools}

        # 动态设置工具属性
        self.name = f"mcp_{server_name}"
        self.emoji = "🔌"
        self.title = f"MCP: {server_name}"
        self.description = f"MCP Server '{server_name}' 提供的工具集"

        # 缓存 actions
        self._actions: list[ActionDef] | None = None

    def get_actions(self) -> list[ActionDef]:
        """将 MCP 工具转换为 ActionDef 列表。"""
        if self._actions is not None:
            return self._actions

        self._actions = []
        for tool in self._mcp_tools.values():
            action = self._convert_to_action(tool)
            self._actions.append(action)

        return self._actions

    def _convert_to_action(self, mcp_tool: Any) -> ActionDef:
        """将 MCP 工具信息转换为 ActionDef。"""
        # 转换 input_schema 为 parameters 格式
        parameters = self._convert_schema(mcp_tool.input_schema)

        # 提取必填参数
        required = mcp_tool.input_schema.get("required", [])

        return ActionDef(
            name=mcp_tool.name,
            description=mcp_tool.description or f"MCP 工具: {mcp_tool.name}",
            parameters=parameters,
            required_params=required,
        )

    def _convert_schema(self, input_schema: dict[str, Any]) -> dict[str, Any]:
        """转换 MCP input_schema 为 ActionDef parameters 格式。

        MCP schema 格式（JSON Schema）:
        {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "..."}
            },
            "required": ["param1"]
        }

        ActionDef parameters 格式:
        {
            "param1": {"type": "string", "description": "..."}
        }
        """
        properties = input_schema.get("properties", {})
        return properties

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        """执行 MCP 工具调用。"""
        if action not in self._mcp_tools:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"未知的 MCP 工具: {action}",
            )

        # 检查是否已连接
        if not self._mcp_manager.is_connected(self._server_name):
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"MCP Server {self._server_name} 未连接",
            )

        try:
            # 调用 MCP 工具
            tool_full_name = f"{self._server_name}_{action}"
            result = await self._mcp_manager.call_tool(tool_full_name, params)

            logger.info(
                "🔌 MCP 工具调用: %s.%s(%s)",
                self._server_name, action, str(params)[:100]
            )

            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=str(result),
                data={"mcp_result": result} if not isinstance(result, str) else None,
            )

        except Exception as e:
            logger.error("MCP 工具调用失败: %s", e)
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"MCP 工具调用失败: {e}",
            )

    def get_tool_info(self, tool_name: str) -> Any | None:
        """获取指定工具的信息。"""
        return self._mcp_tools.get(tool_name)


def create_mcp_bridge_tools(
    mcp_manager: Any,
    tool_registry: Any,
    trusted_servers: set[str] | None = None,
) -> list[MCPBridgeTool]:
    """创建并注册所有 MCP 桥接工具。

    Args:
        mcp_manager: MCP 客户端管理器
        tool_registry: 工具注册表
        trusted_servers: 已信任的 Server 名称集合

    Returns:
        创建的 MCPBridgeTool 列表
    """
    bridge_tools = []

    for server_name, connection in mcp_manager.connections.items():
        if not connection.is_connected:
            continue

        # 创建桥接工具
        bridge = MCPBridgeTool(
            server_name=server_name,
            mcp_manager=mcp_manager,
            tools=connection.tools,
        )

        # 注册到工具注册表
        tool_registry.register(bridge)
        bridge_tools.append(bridge)

        logger.info(
            "注册 MCP 桥接工具: %s (%d 个动作)",
            server_name, len(connection.tools)
        )

    return bridge_tools
