"""公共命令处理器 - CLI/GUI 共享的命令执行模块。

提供注册式命令管理，支持命令别名，自动补全提示。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """命令执行结果。"""
    success: bool
    output: str
    is_quit: bool = False


class CommandHandler:
    """公共命令处理器。

    设计原则：
    - 注册式命令管理，便于扩展
    - 支持命令别名
    - UI无关，返回纯文本结果
    """

    def __init__(
        self,
        tool_registry: Any = None,
        model_registry: Any = None,
        attachment_manager: Any = None,
        agent: Any = None,
    ):
        self._tool_registry = tool_registry
        self._model_registry = model_registry
        self._attachment_manager = attachment_manager
        self._agent = agent
        self._commands: dict[str, dict[str, Any]] = {}
        self._generated_files_mgr = None  # 需外部注入
        self._model_switched_callback: Callable[[str, str], None] | None = None

        self._register_default_commands()

    def set_generated_files_manager(self, mgr: Any) -> None:
        """设置生成文件管理器。"""
        self._generated_files_mgr = mgr

    def set_agent(self, agent: Any) -> None:
        """设置 Agent 实例。"""
        self._agent = agent

    def set_model_switched_callback(self, callback: Callable[[str, str], None] | None) -> None:
        """设置模型切换回调函数。

        Args:
            callback: 回调函数，接收 (model_key, model_name) 参数
        """
        self._model_switched_callback = callback

    def _register_default_commands(self) -> None:
        """注册默认命令集。"""

        # 系统命令
        self.register("/help", self._cmd_help, "显示帮助信息")
        self.register("/model", self._cmd_model, "查看/切换模型（支持序号/名称/key）")
        self.register("/tools", self._cmd_tools, "查看工具列表")
        self.register("/usage", self._cmd_usage, "查看Token用量")
        self.register("/clear", self._cmd_clear, "清空对话历史")
        self.register("/quit", self._cmd_quit, "退出程序")
        self.register("/exit", self._cmd_quit, "退出程序")
        self.register("/q", self._cmd_quit, "退出程序")

        # 生成空间
        self.register("/generated", self._cmd_generated, "查看生成空间")
        self.register("/gen", self._cmd_generated, "查看生成空间")
        self.register("/space", self._cmd_generated, "查看生成空间")

        # 附件管理
        self.register("/attach", self._cmd_attach, "添加附件")
        self.register("/attachments", self._cmd_attachments, "查看附件列表")
        self.register("/clear_attach", self._cmd_clear_attach, "清空附件")
        self.register("/clear_attachments", self._cmd_clear_attach, "清空附件")

        # 快捷工具命令
        self.register("/stats", self._cmd_stats, "查看使用统计")
        self.register("/history", self._cmd_history, "搜索聊天历史")
        self.register("/hist", self._cmd_history, "搜索聊天历史")
        self.register("/diary", self._cmd_diary, "查看日记")
        self.register("/finance", self._cmd_finance, "查看记账汇总")
        self.register("/记账", self._cmd_finance, "查看记账汇总")
        self.register("/health", self._cmd_health, "查看健康数据")
        self.register("/cron", self._cmd_cron, "查看定时任务")
        self.register("/定时", self._cmd_cron, "查看定时任务")
        self.register("/med", self._cmd_med, "查看服药计划")
        self.register("/medication", self._cmd_med, "查看服药计划")
        self.register("/药", self._cmd_med, "查看服药计划")
        self.register("/weather", self._cmd_weather, "查询天气")
        self.register("/time", self._cmd_time, "获取当前时间")
        self.register("/date", self._cmd_time, "获取当前时间")
        self.register("/now", self._cmd_time, "获取当前时间")

        # 批量论文分析命令
        self.register("/analysis_journals", self._cmd_analysis_journals, "批量分析论文文件夹")
        self.register("/论文分析", self._cmd_analysis_journals, "批量分析论文文件夹")

    def register(self, name: str, handler: Callable, help_text: str) -> None:
        """注册命令。"""
        self._commands[name] = {"handler": handler, "help": help_text}

    async def execute(self, user_input: str) -> CommandResult:
        """执行命令。

        Args:
            user_input: 用户输入的完整命令

        Returns:
            CommandResult: 包含 success, output, is_quit 字段
        """
        parts = user_input.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd not in self._commands:
            return CommandResult(
                success=False,
                output=f"未知命令: {cmd}，输入 /help 查看可用命令",
                is_quit=False
            )

        # 执行命令处理器
        handler = self._commands[cmd]["handler"]
        try:
            result = await handler(user_input, args)
            is_quit = cmd in ("/quit", "/exit", "/q")
            return CommandResult(success=True, output=result, is_quit=is_quit)
        except Exception as e:
            logger.exception("命令执行失败: %s", cmd)
            return CommandResult(success=False, output=f"执行错误: {e}", is_quit=False)

    def get_command_suggestions(self, partial: str) -> list[str]:
        """获取命令补全建议。"""
        if not partial.startswith("/"):
            partial = "/" + partial
        return [cmd for cmd in self._commands if cmd.startswith(partial)]

    def get_all_commands(self) -> dict[str, str]:
        """获取所有命令及帮助文本。"""
        return {cmd: info["help"] for cmd, info in self._commands.items()}

    # ================== 命令实现 ==================

    async def _cmd_help(self, user_input: str, args: str) -> str:
        """显示帮助信息。"""
        commands = self.get_all_commands()
        lines = ["可用命令:", ""]
        for cmd, help_text in sorted(commands.items()):
            lines.append(f"  {cmd:<20} - {help_text}")
        return "\n".join(lines)

    async def _cmd_model(self, user_input: str, args: str) -> str:
        """查看/切换模型。支持序号、名称模糊匹配、精确key三种方式。"""
        if not self._model_registry:
            return "❌ 模型注册器未初始化"

        models = self._model_registry.list_models()
        if not models:
            return "❌ 未找到任何模型配置"

        current = self._agent.model_key if self._agent else "unknown"

        if args:
            # 切换模型 - 支持三种方式
            args = args.strip()
            target_model = None

            # 方式1: 序号选择（如 /model 1）
            if args.isdigit():
                idx = int(args) - 1
                if 0 <= idx < len(models):
                    target_model = models[idx]

            # 方式2: 精确 key 匹配
            if target_model is None:
                target_model = self._model_registry.get(args)

            # 方式3: 名称模糊匹配（不区分大小写）
            if target_model is None:
                args_lower = args.lower()
                for m in models:
                    if args_lower in m.key.lower() or args_lower in m.name.lower():
                        target_model = m
                        break

            # 执行切换
            if target_model:
                if self._agent:
                    self._agent.model_key = target_model.key
                # 调用模型切换回调（供GUI同步更新下拉框）
                if self._model_switched_callback:
                    self._model_switched_callback(target_model.key, target_model.name)
                return f"✓ 已切换到模型: {target_model.name} ({target_model.key})"
            else:
                return f"❌ 未找到模型: {args}\n💡 提示: 可使用序号(1-{len(models)})、模型名称或key切换"

        else:
            # 显示模型列表（带序号）
            lines = [f"当前模型: {current}", "", f"可用模型 (共 {len(models)} 个):", ""]
            lines.append("  序号  Key               名称")
            lines.append("  " + "-" * 50)
            for i, m in enumerate(models, 1):
                marker = " ← 当前" if m.key == current else ""
                fc = "✓" if m.supports_function_calling else "✗"
                available = "🟢" if m.is_available else "🔴"
                lines.append(
                    f"  [{i:>2}]  {m.key:<17} {m.name}"
                )
            lines.append("")
            lines.append("💡 切换模型: /model <序号|名称|key>")
            lines.append("   示例: /model 1  或  /model deepseek  或  /model deepseek-chat")
            return "\n".join(lines)

    async def _cmd_tools(self, user_input: str, args: str) -> str:
        """查看工具列表。"""
        if not self._tool_registry:
            return "❌ 工具注册器未初始化"
        return self._tool_registry.get_tools_summary()

    async def _cmd_usage(self, user_input: str, args: str) -> str:
        """查看Token用量。"""
        if not self._model_registry:
            return "❌ 模型注册器未初始化"
        summary = self._model_registry.get_usage_summary()
        return (
            f"总调用: {summary['total_calls']} 次 | "
            f"总 Token: {summary['total_tokens']:,} | "
            f"总费用: ${summary['total_cost_usd']:.6f}"
        )

    async def _cmd_clear(self, user_input: str, args: str) -> str:
        """清空对话历史。"""
        if self._agent:
            self._agent.reset()
        return "✓ 对话历史已清空"
        # return "[dim]对话历史已清空[/dim]"

    async def _cmd_quit(self, user_input: str, args: str) -> str:
        """退出程序。"""
        return "再见！"

    async def _cmd_generated(self, user_input: str, args: str) -> str:
        """查看生成空间。"""
        if not self._generated_files_mgr:
            return "❌ 生成文件管理器未初始化"

        if self._generated_files_mgr.count == 0:
            return "📂 暂无生成文件"

        lines = [f"📂 生成空间 ({self._generated_files_mgr.count} 个文件)", ""]
        for i, f in enumerate(self._generated_files_mgr.files, 1):
            tool_src = f.source_tool
            if f.source_action:
                tool_src += f".{f.source_action}"
            time_part = f.created_at.split("T")[-1] if "T" in f.created_at else f.created_at
            lines.append(f"  {i}. {f.get_icon()} {f.name} ({f.size_display()}) - {tool_src} - {time_part}")
        lines.append(f"\n生成空间目录: {self._generated_files_mgr.space_dir}")
        return "\n".join(lines)

    async def _cmd_attach(self, user_input: str, args: str) -> str:
        """添加附件。"""
        if not self._attachment_manager:
            return "❌ 附件管理器未初始化"

        if not args:
            return "用法: /attach <文件路径>\n示例: /attach D:\\test\\image.png"

        file_path = args.strip().strip('"').strip("'")
        ok, msg = self._attachment_manager.add_file(file_path)
        if ok:
            return f"✓ {msg}"
        else:
            return f"❌ {msg}"

    async def _cmd_attachments(self, user_input: str, args: str) -> str:
        """查看附件列表。"""
        if not self._attachment_manager:
            return "❌ 附件管理器未初始化"

        if self._attachment_manager.count == 0:
            return "📎 当前没有附件"

        lines = [f"📎 附件列表 ({self._attachment_manager.count})", ""]
        for att in self._attachment_manager.attachments:
            lines.append(f"  {att.get_icon()} {att.name} ({att.size_display()})")
        return "\n".join(lines)

    async def _cmd_clear_attach(self, user_input: str, args: str) -> str:
        """清空附件。"""
        if not self._attachment_manager:
            return "❌ 附件管理器未初始化"

        count = self._attachment_manager.count
        self._attachment_manager.clear()
        return f"✓ 已清空 {count} 个附件"

    # ================== 工具命令 ==================

    async def _run_tool_action(self, tool_name: str, action: str, params: dict) -> str:
        """执行工具动作并返回结果。"""
        if not self._tool_registry:
            return f"❌ 错误: 工具注册器未初始化"

        try:
            tool = self._tool_registry.get_tool(tool_name)
            if tool is None:
                return f"❌ 错误: 未找到工具 '{tool_name}'"

            result = await tool.execute(action, params)
            if result.status.value == "success":
                return result.output or "✓ 操作成功"
            else:
                return f"❌ 错误: {result.error}"
        except Exception as e:
            return f"❌ 执行失败: {e}"

    async def _cmd_stats(self, user_input: str, args: str) -> str:
        """使用统计。"""
        period = args.strip() if args else "all"
        return await self._run_tool_action("statistics", "get_usage_stats", {"period": period})

    async def _cmd_history(self, user_input: str, args: str) -> str:
        """聊天历史。"""
        keyword = args.strip() if args else ""
        return await self._run_tool_action(
            "chat_history", "search_history",
            {"keyword": keyword, "limit": 15}
        )

    async def _cmd_diary(self, user_input: str, args: str) -> str:
        """日记。"""
        date_range = args.strip() if args else "all"
        return await self._run_tool_action(
            "diary", "query_diary",
            {"date_range": date_range, "limit": 10}
        )

    async def _cmd_finance(self, user_input: str, args: str) -> str:
        """记账。"""
        period = args.strip() if args else "month"
        return await self._run_tool_action(
            "finance", "get_financial_summary",
            {"period": period}
        )

    async def _cmd_health(self, user_input: str, args: str) -> str:
        """健康数据。"""
        date_range = args.strip() if args else "today"
        return await self._run_tool_action(
            "health", "query_health_data",
            {"date_range": date_range, "limit": 10}
        )

    async def _cmd_cron(self, user_input: str, args: str) -> str:
        """定时任务。"""
        return await self._run_tool_action("cron", "list_jobs", {})

    async def _cmd_med(self, user_input: str, args: str) -> str:
        """服药计划。"""
        return await self._run_tool_action(
            "medication", "query_medications",
            {"status": "active", "date": "today"}
        )

    async def _cmd_weather(self, user_input: str, args: str) -> str:
        """天气查询。"""
        city = args.strip()
        if not city:
            return "用法: /weather <城市名>\n示例: /weather 北京, /weather 上海"
        return await self._run_tool_action("weather", "get_weather", {"city": city})

    async def _cmd_time(self, user_input: str, args: str) -> str:
        """当前时间。"""
        return await self._run_tool_action("datetime_tool", "get_datetime", {"format": "full"})

    async def _cmd_analysis_journals(self, user_input: str, args: str) -> str:
        """批量分析论文文件夹。"""
        folder_path = args.strip() if args else ""
        if not folder_path:
            return "用法: /analysis_journals <文件夹路径>\n示例: /analysis_journals D:\\papers\\research"

        # 调用批量论文分析工具的完整工作流
        return await self._run_tool_action(
            "batch_paper_analyzer", "full_pipeline",
            {"folder_path": folder_path, "report_title": "论文分析报告"}
        )
