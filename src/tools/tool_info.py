"""ToolInfo 工具 — 工具信息查询。

支持动作：
- list_tools: 列出所有已注册工具，支持按分类过滤
- get_tool_info: 获取指定工具的详细信息
- list_categories: 列出所有工具分类

这样用户可以通过自然语言查询系统有哪些工具可用。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

# 默认配置文件路径
_DEFAULT_TOOLS_JSON = Path(__file__).resolve().parent.parent.parent / "config" / "tools.json"


class ToolInfoTool(BaseTool):
    """工具信息查询工具。

    从 config/tools.json 读取工具配置信息，
    提供工具清单查询、详情查看、分类浏览等功能。
    纯只读操作，不修改任何数据。
    """

    name = "tool_info"
    emoji = "🛠️"
    title = "工具信息"
    description = "查询系统可用工具清单、工具详情和分类信息"

    def __init__(self, config_path: str = ""):
        self._config_path = Path(config_path) if config_path else _DEFAULT_TOOLS_JSON
        self._tools_config: dict[str, Any] = {}
        self._categories_config: dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """从 JSON 配置文件加载工具定义。"""
        if not self._config_path.exists():
            logger.warning("工具配置文件不存在: %s", self._config_path)
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._tools_config = data.get("tools", {})
            self._categories_config = data.get("categories", {})
            logger.info("已加载 %d 个工具配置", len(self._tools_config))
        except Exception as e:
            logger.error("加载工具配置失败: %s", e)

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="list_tools",
                description="列出系统所有可用工具，支持按分类筛选。返回工具名称、emoji、描述和分类。",
                parameters={
                    "category": {
                        "type": "string",
                        "description": "可选，按分类筛选。如: system, filesystem, web, utility, life, knowledge 等",
                    },
                    "enabled_only": {
                        "type": "string",
                        "description": "是否只显示已启用的工具，默认为 'true'",
                        "enum": ["true", "false"],
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="get_tool_info",
                description="获取指定工具的详细信息，包括工具描述、动作列表、风险等级等。",
                parameters={
                    "tool_name": {
                        "type": "string",
                        "description": "工具名称，如: shell, file, browser, search 等",
                    },
                },
                required_params=["tool_name"],
            ),
            ActionDef(
                name="list_categories",
                description="列出系统所有工具分类，包括分类名称、emoji 和描述。",
                parameters={},
                required_params=[],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        if action == "list_tools":
            return self._list_tools(params)
        elif action == "get_tool_info":
            return self._get_tool_info(params)
        elif action == "list_categories":
            return self._list_categories(params)
        else:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )

    def _list_tools(self, params: dict[str, Any]) -> ToolResult:
        """列出工具列表。"""
        category = params.get("category", "").strip()
        enabled_only = params.get("enabled_only", "true").lower() == "true"

        if not self._tools_config:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="暂无工具配置信息。",
                data={"tools": []},
            )

        # 筛选工具
        tools = []
        for tool_name, tool_cfg in self._tools_config.items():
            # 过滤未启用的工具
            if enabled_only and not tool_cfg.get("enabled", True):
                continue

            # 按分类筛选
            if category:
                display = tool_cfg.get("display", {})
                if display.get("category") != category:
                    continue

            display = tool_cfg.get("display", {})
            security = tool_cfg.get("security", {})

            tools.append({
                "name": tool_name,
                "emoji": display.get("emoji", "🔧"),
                "title": display.get("name", tool_name),
                "description": display.get("description", ""),
                "category": display.get("category", "unknown"),
                "risk_level": security.get("risk_level", "unknown"),
                "enabled": tool_cfg.get("enabled", True),
            })

        # 按分类和名称排序
        tools.sort(key=lambda x: (x["category"], x["title"]))

        # 格式化输出
        if not tools:
            if category:
                output = f"分类 '{category}' 下没有找到工具。"
            else:
                output = "没有找到工具。"
        else:
            lines = [f"📋 可用工具列表（共 {len(tools)} 个）\n"]

            # 按分类分组显示
            current_category = None
            for tool in tools:
                if tool["category"] != current_category:
                    current_category = tool["category"]
                    cat_info = self._categories_config.get(current_category, {})
                    cat_emoji = cat_info.get("emoji", "📂")
                    cat_name = cat_info.get("name", current_category)
                    lines.append(f"\n{cat_emoji} {cat_name}")

                risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴", "unknown": "⚪"}.get(
                    tool["risk_level"], "⚪"
                )
                status_icon = "✅" if tool["enabled"] else "❌"
                lines.append(
                    f"  {tool['emoji']} {tool['title']} ({tool['name']}) - {tool['description'][:40]}... {risk_icon} {status_icon}"
                )

            output = "\n".join(lines)

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={"tools": tools, "count": len(tools)},
        )

    def _get_tool_info(self, params: dict[str, Any]) -> ToolResult:
        """获取工具详细信息。"""
        tool_name = params.get("tool_name", "").strip()

        if not tool_name:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="请提供工具名称 (tool_name)",
            )

        if tool_name not in self._tools_config:
            # 尝试模糊匹配
            matches = [name for name in self._tools_config.keys() if tool_name.lower() in name.lower()]
            if matches:
                suggestion = f"未找到 '{tool_name}'，是否指: {', '.join(matches)}"
            else:
                suggestion = f"未找到工具 '{tool_name}'"
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=suggestion,
            )

        tool_cfg = self._tools_config[tool_name]
        display = tool_cfg.get("display", {})
        security = tool_cfg.get("security", {})
        config = tool_cfg.get("config", {})
        actions = tool_cfg.get("actions", [])

        # 获取分类信息
        category = display.get("category", "unknown")
        cat_info = self._categories_config.get(category, {})

        lines = [
            f"🛠️ 工具详情: {display.get('emoji', '🔧')} {display.get('name', tool_name)}",
            f"标识符: {tool_name}",
            f"状态: {'✅ 已启用' if tool_cfg.get('enabled', True) else '❌ 已禁用'}",
            f"",
            f"📝 描述: {display.get('description', '无')}",
            f"",
            f"📂 分类: {cat_info.get('emoji', '📂')} {cat_info.get('name', category)}",
            f"",
            f"⚠️ 风险等级: {security.get('risk_level', 'unknown').upper()}",
        ]

        # 安全信息
        if security.get("require_confirmation"):
            lines.append("🔐 需要确认: 是")

        # 动作列表
        if actions:
            lines.append(f"\n🎯 支持的动作 ({len(actions)} 个):")
            for action in actions:
                lines.append(f"  • {action}")

        # 配置信息（非敏感）
        if config:
            safe_config = {k: v for k, v in config.items() if k not in ("api_key", "password", "token")}
            if safe_config:
                lines.append(f"\n⚙️ 主要配置:")
                for k, v in safe_config.items():
                    lines.append(f"  • {k}: {v}")

        output = "\n".join(lines)

        data = {
            "name": tool_name,
            "title": display.get("name", tool_name),
            "emoji": display.get("emoji", "🔧"),
            "description": display.get("description", ""),
            "category": category,
            "category_name": cat_info.get("name", category),
            "risk_level": security.get("risk_level", "unknown"),
            "enabled": tool_cfg.get("enabled", True),
            "actions": actions,
            "require_confirmation": security.get("require_confirmation", False),
        }

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data=data,
        )

    def _list_categories(self, params: dict[str, Any]) -> ToolResult:
        """列出所有分类。"""
        if not self._categories_config:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="暂无分类配置信息。",
                data={"categories": []},
            )

        # 统计每个分类的工具数量
        category_counts = {}
        for tool_name, tool_cfg in self._tools_config.items():
            if tool_cfg.get("enabled", True):
                cat = tool_cfg.get("display", {}).get("category", "unknown")
                category_counts[cat] = category_counts.get(cat, 0) + 1

        lines = [f"📂 工具分类列表（共 {len(self._categories_config)} 个分类）\n"]

        for cat_id, cat_cfg in sorted(self._categories_config.items()):
            emoji = cat_cfg.get("emoji", "📂")
            name = cat_cfg.get("name", cat_id)
            desc = cat_cfg.get("description", "无描述")
            count = category_counts.get(cat_id, 0)

            lines.append(f"{emoji} {name}")
            lines.append(f"   标识符: {cat_id}")
            lines.append(f"   描述: {desc}")
            lines.append(f"   工具数: {count} 个")
            lines.append("")

        output = "\n".join(lines).strip()

        categories = [
            {
                "id": cat_id,
                "emoji": cat_cfg.get("emoji", "📂"),
                "name": cat_cfg.get("name", cat_id),
                "description": cat_cfg.get("description", ""),
                "tool_count": category_counts.get(cat_id, 0),
            }
            for cat_id, cat_cfg in self._categories_config.items()
        ]

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={"categories": categories},
        )
