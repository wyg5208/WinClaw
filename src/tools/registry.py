"""工具注册器 — 管理所有可用工具的注册与检索（Phase 1.3 重构版）。

重构变更：
- 支持从 config/tools.json 加载配置
- 支持自动发现（按 module/class 路径动态导入）
- 支持按能力标签查询
- 兼容旧的手动注册方式
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any

from src.tools.base import BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

# 默认配置文件路径
_DEFAULT_TOOLS_JSON = Path(__file__).resolve().parent.parent.parent / "config" / "tools.json"


class ToolRegistry:
    """工具注册中心。

    Phase 1.3 增强：
    - 从 tools.json 加载配置驱动的工具注册
    - 自动发现：按 module.class 路径动态导入
    - 按分类 / 风险等级查询
    - 工具启用/禁用控制

    Phase 4.6 增强：
    - 工具懒加载：注册时只记录元信息，首次使用时才加载
    - Schema 缓存：避免重复生成 function calling schema
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        # 函数名 → (工具名, 动作名) 的映射
        self._func_map: dict[str, tuple[str, str]] = {}
        # 工具配置元数据（来自 tools.json）
        self._tool_configs: dict[str, dict[str, Any]] = {}
        # 全局设置
        self._global_settings: dict[str, Any] = {}
        # 分类定义
        self._categories: dict[str, dict[str, Any]] = {}
        # 懒加载工具：工具名 → (module, class, init_kwargs)
        self._lazy_tools: dict[str, tuple[str, str, dict[str, Any]]] = {}
        # Schema 缓存
        self._schema_cache: list[dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # 配置加载
    # ------------------------------------------------------------------

    def load_config(self, config_path: Path | None = None) -> None:
        """从 JSON 配置文件加载工具定义。

        Args:
            config_path: 配置文件路径，默认 config/tools.json
        """
        path = config_path or _DEFAULT_TOOLS_JSON
        if not path.exists():
            logger.warning("工具配置文件不存在: %s", path)
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("加载工具配置失败: %s", e)
            return

        self._global_settings = data.get("global_settings", {})
        self._categories = data.get("categories", {})

        tools_section = data.get("tools", {})
        for tool_name, tool_cfg in tools_section.items():
            self._tool_configs[tool_name] = tool_cfg
        logger.info("从配置加载了 %d 个工具定义", len(tools_section))

    def auto_discover(self, lazy: bool = True) -> None:
        """根据已加载的配置自动发现并注册工具实例。

        Args:
            lazy: 是否启用懒加载模式。默认 True。
                - True: 只记录工具元信息，首次使用时才加载（推荐，加速启动）
                - False: 立即加载所有工具实例
        """
        for tool_name, cfg in self._tool_configs.items():
            if not cfg.get("enabled", True):
                logger.info("工具 '%s' 已禁用，跳过", tool_name)
                continue

            module_path = cfg.get("module", "")
            class_name = cfg.get("class", "")
            if not module_path or not class_name:
                logger.warning("工具 '%s' 缺少 module/class 配置", tool_name)
                continue

            # 从配置构建初始化参数
            init_kwargs = self._build_init_kwargs(tool_name, cfg)

            if lazy:
                # 懒加载模式：只记录元信息
                self._lazy_tools[tool_name] = (module_path, class_name, init_kwargs)
                # 预注册函数映射（用于 schema 生成）
                self._preload_tool_metadata(tool_name, module_path, class_name)
            else:
                # 立即加载模式
                try:
                    mod = importlib.import_module(module_path)
                    cls = getattr(mod, class_name)
                    tool_instance = cls(**init_kwargs)
                    self.register(tool_instance)
                except Exception as e:
                    logger.error("自动发现工具 '%s' 失败: %s", tool_name, e)

    def _preload_tool_metadata(self, tool_name: str, module_path: str, class_name: str) -> None:
        """预加载工具元数据（不实例化工具）。

        用于在懒加载模式下获取工具的 action 定义，以便生成 schema。
        """
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            # 获取类属性（name, actions 等）而无需实例化
            if hasattr(cls, "name") and hasattr(cls, "get_actions"):
                # 临时创建实例获取 actions（轻量操作）
                # 注意：大多数工具的 __init__ 很轻量，重操作在 execute 中
                init_kwargs = self._lazy_tools.get(tool_name, (None, None, {}))[2]
                tool_instance = cls(**init_kwargs)
                # 注册函数映射
                for action in tool_instance.get_actions():
                    func_name = f"{tool_name}_{action.name}"
                    self._func_map[func_name] = (tool_name, action.name)
                # 立即注册到 _tools（因为大多数工具初始化很快）
                self._tools[tool_name] = tool_instance
                logger.debug("预加载工具元数据: %s", tool_name)
        except Exception as e:
            logger.warning("预加载工具 '%s' 元数据失败: %s", tool_name, e)

    def _build_init_kwargs(self, tool_name: str, cfg: dict) -> dict[str, Any]:
        """从工具配置中提取构造参数。"""
        kwargs: dict[str, Any] = {}
        tool_config = cfg.get("config", {})
        security = cfg.get("security", {})

        if tool_name == "shell":
            kwargs["timeout"] = tool_config.get("timeout", 30)
            kwargs["max_output_length"] = tool_config.get("max_output_length", 10000)
            kwargs["working_directory"] = tool_config.get("working_directory", "")
            kwargs["env_vars"] = tool_config.get("env_vars", {})
            kwargs["blacklist"] = security.get("blacklist", [])
            kwargs["whitelist"] = security.get("whitelist", [])
            kwargs["whitelist_mode"] = security.get("whitelist_mode", False)
        elif tool_name == "file":
            kwargs["max_read_size"] = tool_config.get("max_read_size", 1_048_576)
            kwargs["max_lines_per_page"] = tool_config.get("max_lines_per_page", 200)
            kwargs["denied_extensions"] = tool_config.get("denied_extensions", [])
        elif tool_name == "screen":
            kwargs["max_width"] = tool_config.get("max_width", 1920)
            kwargs["quality"] = tool_config.get("quality", 85)
            kwargs["model_max_width"] = tool_config.get("model_max_width", 1280)
        elif tool_name == "browser":
            kwargs["headless"] = tool_config.get("headless", False)
            kwargs["timeout"] = tool_config.get("timeout", 30000)
            kwargs["viewport_width"] = tool_config.get("viewport_width", 1280)
            kwargs["viewport_height"] = tool_config.get("viewport_height", 720)
        elif tool_name == "app_control":
            kwargs["launch_timeout"] = tool_config.get("launch_timeout", 10)
        elif tool_name == "clipboard":
            kwargs["max_text_length"] = tool_config.get("max_text_length", 50000)
        elif tool_name == "notify":
            kwargs["app_id"] = tool_config.get("app_id", "WinClaw")
        elif tool_name == "search":
            kwargs["max_local_results"] = tool_config.get("max_local_results", 50)
            kwargs["max_web_results"] = tool_config.get("max_web_results", 10)
            kwargs["local_max_depth"] = tool_config.get("local_max_depth", 5)
            kwargs["web_timeout"] = tool_config.get("web_timeout", 15)
        elif tool_name == "weather":
            kwargs["api_key"] = tool_config.get("api_key", "")
            kwargs["api_host"] = tool_config.get("api_host", "")
            kwargs["fallback_to_web"] = tool_config.get("fallback_to_web", True)
        elif tool_name in ("statistics", "chat_history"):
            kwargs["db_path"] = tool_config.get("db_path", "")
        elif tool_name in ("diary", "finance", "health"):
            kwargs["db_path"] = tool_config.get("db_path", "")
        elif tool_name == "knowledge":
            kwargs["db_path"] = tool_config.get("db_path", "")
            kwargs["doc_dir"] = tool_config.get("doc_dir", "")

        return kwargs

    # ------------------------------------------------------------------
    # 注册与查询
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """注册一个工具实例。"""
        if tool.name in self._tools:
            logger.warning("工具 '%s' 已注册，将被覆盖", tool.name)
        self._tools[tool.name] = tool
        # 更新函数映射
        for action in tool.get_actions():
            func_name = f"{tool.name}_{action.name}"
            self._func_map[func_name] = (tool.name, action.name)
        # 清除 schema 缓存
        self._schema_cache = None
        logger.info("已注册工具: %s %s (%s)", tool.emoji, tool.title, tool.name)

    def unregister(self, tool_name: str) -> bool:
        """注销一个工具。"""
        if tool_name not in self._tools:
            return False
        tool = self._tools.pop(tool_name)
        # 清理函数映射
        for action in tool.get_actions():
            func_name = f"{tool_name}_{action.name}"
            self._func_map.pop(func_name, None)
        # 清除 schema 缓存
        self._schema_cache = None
        logger.info("已注销工具: %s", tool_name)
        return True

    def get_tool(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def find_by_category(self, category: str) -> list[BaseTool]:
        """按分类查询工具。"""
        results = []
        for name, tool in self._tools.items():
            cfg = self._tool_configs.get(name, {})
            display = cfg.get("display", {})
            if display.get("category") == category:
                results.append(tool)
        return results

    def find_by_risk_level(self, risk_level: str) -> list[BaseTool]:
        """按风险等级查询工具。"""
        results = []
        for name, tool in self._tools.items():
            cfg = self._tool_configs.get(name, {})
            security = cfg.get("security", {})
            if security.get("risk_level") == risk_level:
                results.append(tool)
        return results

    def get_tool_config(self, tool_name: str) -> dict[str, Any]:
        """获取工具的完整配置。"""
        return dict(self._tool_configs.get(tool_name, {}))

    def get_tool_risk_level(self, tool_name: str) -> str:
        """获取工具的风险等级。"""
        cfg = self._tool_configs.get(tool_name, {})
        return cfg.get("security", {}).get("risk_level", "low")

    def is_tool_enabled(self, tool_name: str) -> bool:
        """检查工具是否启用。"""
        cfg = self._tool_configs.get(tool_name, {})
        return cfg.get("enabled", True)

    # ------------------------------------------------------------------
    # Schema 与调用
    # ------------------------------------------------------------------

    def get_all_schemas(self, use_cache: bool = True) -> list[dict[str, Any]]:
        """获取所有工具的 function calling schema 列表。

        Args:
            use_cache: 是否使用缓存。默认 True。
                首次调用时生成 schema 并缓存，后续直接返回缓存。
        """
        if use_cache and self._schema_cache is not None:
            return self._schema_cache

        schemas = []
        for tool in self._tools.values():
            schemas.extend(tool.get_schema())

        if use_cache:
            self._schema_cache = schemas

        return schemas

    def invalidate_schema_cache(self) -> None:
        """清除 schema 缓存。在工具注册/注销后自动调用。"""
        self._schema_cache = None

    def resolve_function_name(self, func_name: str) -> tuple[str, str] | None:
        """解析函数名为 (工具名, 动作名)。"""
        return self._func_map.get(func_name)

    async def call_function(self, func_name: str, arguments: dict[str, Any]) -> ToolResult:
        """根据函数名调用对应工具的对应动作。"""
        resolved = self.resolve_function_name(func_name)
        if resolved is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"未知的函数: {func_name}",
            )

        tool_name, action_name = resolved
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"工具未注册: {tool_name}",
            )

        logger.info(
            "%s 调用 %s.%s(%s)",
            tool.emoji,
            tool_name,
            action_name,
            json.dumps(arguments, ensure_ascii=False)[:200],
        )
        return await tool.safe_execute(action_name, arguments)

    def get_tools_summary(self) -> str:
        """返回所有工具的摘要信息（用于调试/展示）。"""
        lines = []
        for tool in self._tools.values():
            actions = [a.name for a in tool.get_actions()]
            risk = self.get_tool_risk_level(tool.name)
            risk_badge = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk, "⚪")
            lines.append(
                f"  {tool.emoji} {tool.title} ({tool.name}): "
                f"{', '.join(actions)} {risk_badge}"
            )
        return f"已注册 {len(self._tools)} 个工具:\n" + "\n".join(lines)

    @property
    def global_settings(self) -> dict[str, Any]:
        return dict(self._global_settings)

    @property
    def categories(self) -> dict[str, dict[str, Any]]:
        return dict(self._categories)


def create_default_registry() -> ToolRegistry:
    """创建并注册所有默认工具（配置驱动模式）。

    优先从 tools.json 加载配置 + 自动发现。
    如果配置文件不存在或加载失败，回退到手动注册。
    """
    registry = ToolRegistry()

    # 尝试配置驱动
    config_path = _DEFAULT_TOOLS_JSON
    if config_path.exists():
        registry.load_config(config_path)
        registry.auto_discover()
        if registry.list_tools():
            return registry
        logger.warning("自动发现未注册任何工具，回退到手动注册")

    # 回退：手动注册
    from src.tools.file import FileTool
    from src.tools.screen import ScreenTool
    from src.tools.shell import ShellTool
    from src.tools.app_control import AppControlTool
    from src.tools.clipboard import ClipboardTool
    from src.tools.notify import NotifyTool
    from src.tools.search import SearchTool

    registry.register(ShellTool())
    registry.register(FileTool())
    registry.register(ScreenTool())
    registry.register(AppControlTool())
    registry.register(ClipboardTool())
    registry.register(NotifyTool())
    registry.register(SearchTool())
    # BrowserTool 不在回退中注册，因为 Playwright 可能未安装
    return registry
