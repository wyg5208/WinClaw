"""WinClaw CLI 入口 — MVP 阶段的命令行交互界面。"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from src import __app_name__, __version__
from src.core.agent import Agent
from src.core.generated_files import GeneratedFilesManager
from src.models.registry import ModelRegistry
from src.tools.registry import create_default_registry
from src.ui.attachment_manager import AttachmentManager, AttachmentInfo, detect_file_type, get_mime_type

console = Console()


class CliAttachmentManager:
    """CLI 模式的附件管理器（不依赖 Qt）。"""
    
    def __init__(self):
        self._attachments: list[AttachmentInfo] = []
        self._max_attachments = 10
        self._max_file_size = 50 * 1024 * 1024  # 50MB
    
    @property
    def attachments(self) -> list[AttachmentInfo]:
        return self._attachments.copy()
    
    @property
    def count(self) -> int:
        return len(self._attachments)
    
    def has_attachments(self) -> bool:
        return len(self._attachments) > 0
    
    def add_file(self, file_path: str) -> tuple[bool, str]:
        """Add a file attachment."""
        path = Path(file_path).expanduser().resolve()
        
        if not path.exists():
            return False, f"文件不存在: {file_path}"
        
        if not path.is_file():
            return False, f"不是有效文件: {file_path}"
        
        file_size = path.stat().st_size
        if file_size > self._max_file_size:
            size_mb = file_size / (1024 * 1024)
            return False, f"文件过大: {size_mb:.1f}MB (限制 50MB)"
        
        if len(self._attachments) >= self._max_attachments:
            return False, f"附件数量已达上限 ({self._max_attachments})"
        
        str_path = str(path)
        for att in self._attachments:
            if att.path == str_path:
                return False, "文件已添加"
        
        attachment = AttachmentInfo(
            path=str_path,
            name=path.name,
            file_type=detect_file_type(str_path),
            size=file_size,
            mime_type=get_mime_type(str_path),
        )
        
        self._attachments.append(attachment)
        return True, f"已添加: {attachment.name} ({attachment.size_display()})"
    
    def remove_file(self, file_path: str) -> bool:
        for i, att in enumerate(self._attachments):
            if att.path == file_path:
                self._attachments.pop(i)
                return True
        return False
    
    def clear(self) -> None:
        self._attachments.clear()
    
    def get_context_prompt(self) -> str:
        """Generate attachment context for Agent."""
        if not self._attachments:
            return ""
        
        lines = ["[附件信息]"]
        for att in self._attachments:
            type_desc = {
                "image": "图片",
                "text": "文本",
                "code": "代码",
                "document": "文档",
                "other": "文件",
            }.get(att.file_type, "文件")
            
            lines.append(f"- {att.name} ({type_desc}, {att.size_display()}, 路径: {att.path})")
        
        lines.append("")
        return "\n".join(lines)


def _load_dotenv() -> None:
    """加载 .env 文件到环境变量（不覆盖已有值）。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"

    if not env_path.exists():
        env_path = Path.cwd() / ".env"

    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)


def setup_logging(level: str = "WARNING") -> None:
    """配置日志。"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.WARNING),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


def print_banner() -> None:
    """打印启动横幅。"""
    banner = Text()
    banner.append("🐾 ", style="bold")
    banner.append(f"{__app_name__}", style="bold cyan")
    banner.append(f" v{__version__}", style="dim")
    banner.append(" — Windows AI 桌面智能体", style="")

    console.print(Panel(banner, border_style="cyan", padding=(0, 2)))
    console.print()


def print_help() -> None:
    """打印帮助信息。"""
    help_text = """[dim]命令：
  /help       显示此帮助
  /model      查看/切换当前模型
  /tools      查看已注册的工具
  /usage      查看 token 用量和费用
  /generated  查看生成空间（已生成的文件）
  /clear      清空对话历史
  /quit       退出程序

附件命令：
  /attach <路径>     添加文件附件
  /attachments       查看当前附件列表
  /clear_attach      清空所有附件

直接输入文字即可与 AI 对话。[/dim]"""
    console.print(help_text)
    console.print()


async def run_cli() -> None:
    """运行 CLI 交互循环。"""
    _load_dotenv()
    setup_logging("WARNING")
    print_banner()

    # 初始化组件
    console.print("[dim]正在初始化...[/dim]")

    model_registry = ModelRegistry()
    tool_registry = create_default_registry()

    # 初始化附件管理器 (CLI 模式不需要 QApplication)
    attachment_manager = CliAttachmentManager()

    # 初始化生成文件管理器
    generated_files_mgr = GeneratedFilesManager()

    # 检查可用模型
    models = model_registry.list_models()
    if not models:
        console.print("[red]错误：未找到任何模型配置[/red]")
        return

    # 选择默认模型（优先 deepseek-chat，性价比高）
    default_key = "deepseek-chat"
    if model_registry.get(default_key) is None:
        default_key = models[0].key

    agent = Agent(
        model_registry=model_registry,
        tool_registry=tool_registry,
        model_key=default_key,
    )

    model_cfg = model_registry.get(default_key)
    console.print(f"[green]✓[/green] 模型: [cyan]{model_cfg.name}[/cyan]")
    console.print(f"[green]✓[/green] {tool_registry.get_tools_summary()}")
    console.print(f"[green]✓[/green] 生成空间: {generated_files_mgr.space_dir}")
    console.print()
    print_help()

    # 订阅文件生成事件（CLI 模式下自动记录）
    async def _on_file_generated(event_type, data):
        file_path = data.file_path if hasattr(data, "file_path") else data.get("file_path", "")
        source_tool = data.source_tool if hasattr(data, "source_tool") else data.get("source_tool", "")
        source_action = data.source_action if hasattr(data, "source_action") else data.get("source_action", "")
        if file_path:
            info = generated_files_mgr.register_file(
                file_path=file_path,
                source_tool=source_tool,
                source_action=source_action,
            )
            if info:
                console.print(f"  [dim]📂 已记录: {info.name} ({info.size_display()})[/dim]")

    agent.event_bus.on("file_generated", _on_file_generated)

    # 主循环
    while True:
        try:
            user_input = console.input("[bold green]你> [/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见！[/dim]")
            break

        if not user_input:
            continue

        # 处理命令
        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]

            if cmd in ("/quit", "/exit", "/q"):
                console.print("[dim]再见！[/dim]")
                break

            elif cmd == "/help":
                print_help()
                continue

            elif cmd == "/model":
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    new_key = parts[1].strip()
                    if model_registry.get(new_key):
                        agent.model_key = new_key
                        cfg = model_registry.get(new_key)
                        console.print(f"[green]已切换到模型: {cfg.name}[/green]")
                    else:
                        console.print(f"[red]未知模型: {new_key}[/red]")
                        console.print("可用模型:")
                        for m in model_registry.list_models():
                            marker = " ← 当前" if m.key == agent.model_key else ""
                            console.print(f"  {m.key}: {m.name}{marker}")
                else:
                    console.print(f"当前模型: [cyan]{agent.model_key}[/cyan]")
                    console.print("可用模型:")
                    for m in model_registry.list_models():
                        marker = " [green]← 当前[/green]" if m.key == agent.model_key else ""
                        fc = "✓" if m.supports_function_calling else "✗"
                        console.print(
                            f"  [bold]{m.key}[/bold]: {m.name} "
                            f"(FC:{fc}, ctx:{m.context_window // 1000}k, "
                            f"${m.cost_input}/{m.cost_output}){marker}"
                        )
                continue

            elif cmd == "/tools":
                console.print(tool_registry.get_tools_summary())
                continue

            elif cmd == "/usage":
                summary = model_registry.get_usage_summary()
                console.print(
                    f"总调用: {summary['total_calls']} 次 | "
                    f"总 Token: {summary['total_tokens']:,} | "
                    f"总费用: ${summary['total_cost_usd']:.6f}"
                )
                continue

            elif cmd == "/clear":
                agent.reset()
                console.print("[dim]对话历史已清空[/dim]")
                continue

            elif cmd in ("/generated", "/gen", "/space"):
                # 查看生成空间
                if generated_files_mgr.count == 0:
                    console.print("[dim]暂无生成文件[/dim]")
                else:
                    gen_table = Table(title=f"📂 生成空间 ({generated_files_mgr.count} 个文件)")
                    gen_table.add_column("#", style="dim", width=4)
                    gen_table.add_column("类型", width=4)
                    gen_table.add_column("文件名", style="white")
                    gen_table.add_column("大小", style="dim", width=10)
                    gen_table.add_column("来源", style="cyan", width=16)
                    gen_table.add_column("时间", style="dim", width=10)

                    for i, f in enumerate(generated_files_mgr.files, 1):
                        tool_src = f.source_tool
                        if f.source_action:
                            tool_src += f".{f.source_action}"
                        time_part = f.created_at.split("T")[-1] if "T" in f.created_at else f.created_at
                        gen_table.add_row(
                            str(i), f.get_icon(), f.name,
                            f.size_display(), tool_src, time_part,
                        )
                    console.print(gen_table)
                    console.print(f"[dim]生成空间目录: {generated_files_mgr.space_dir}[/dim]")
                continue

            elif cmd == "/attach":
                # 添加附件
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    file_path = parts[1].strip().strip('"').strip("'")
                    ok, msg = attachment_manager.add_file(file_path)
                    if ok:
                        console.print(f"[green]✓[/green] {msg}")
                    else:
                        console.print(f"[red]✗[/red] {msg}")
                else:
                    console.print("[yellow]用法: /attach <文件路径>[/yellow]")
                    console.print("示例: /attach D:\\test\\image.png")
                continue

            elif cmd == "/attachments":
                # 查看附件列表
                if attachment_manager.count == 0:
                    console.print("[dim]当前没有附件[/dim]")
                else:
                    table = Table(title=f"📎 附件列表 ({attachment_manager.count})")
                    table.add_column("类型", style="cyan", width=6)
                    table.add_column("文件名", style="white")
                    table.add_column("大小", style="dim", width=10)
                    table.add_column("路径", style="dim")
                    
                    for att in attachment_manager.attachments:
                        table.add_row(
                            att.get_icon(),
                            att.name,
                            att.size_display(),
                            att.path
                        )
                    console.print(table)
                continue

            elif cmd in ("/clear_attach", "/clear_attachments"):
                # 清空附件
                count = attachment_manager.count
                attachment_manager.clear()
                console.print(f"[dim]已清空 {count} 个附件[/dim]")
                continue

            else:
                console.print(f"[red]未知命令: {cmd}[/red]，输入 /help 查看帮助")
                continue

        # 发送给 Agent（流式输出）
        # 构建带附件的消息
        full_message = user_input
        if attachment_manager.has_attachments():
            context = attachment_manager.get_context_prompt()
            full_message = f"{context}\n用户请求: {user_input}"
            console.print(f"[dim]📎 已附加 {attachment_manager.count} 个文件[/dim]")
            # 发送后清空附件
            attachment_manager.clear()

        console.print()
        console.print("[cyan]🐾 WinClaw:[/cyan]")

        full_content = ""
        tool_steps: list = []
        stream_error = False

        # 订阅工具调用事件，用于在流式输出后显示
        _tool_events: list[tuple[str, str, str]] = []

        async def _on_tool_call(event_type, data):
            _tool_events.append(("call", data.tool_name, data.action_name))

        async def _on_tool_result(event_type, data):
            status_icon = "[green]✓[/green]" if data.status == "success" else "[red]✗[/red]"
            _tool_events.append(("result", f"{status_icon} {data.tool_name}.{data.action_name}", data.output[:200]))

        sub_tc = agent.event_bus.on("tool_call", _on_tool_call)
        sub_tr = agent.event_bus.on("tool_result", _on_tool_result)

        try:
            # 显示工具调用过程中的状态
            async for chunk in agent.chat_stream(full_message):
                # 如果有新的工具事件，先输出工具信息
                while _tool_events:
                    evt_type, name_info, detail = _tool_events.pop(0)
                    if evt_type == "call":
                        if full_content:
                            # 工具调用前有部分文本，先换行
                            sys.stdout.write("\n")
                            full_content = ""
                        console.print(f"  [dim]▶ {name_info}.{detail}[/dim]")
                    elif evt_type == "result":
                        console.print(f"  {name_info}")
                        if detail and len(detail) <= 200:
                            for line in detail.split("\n")[:3]:
                                console.print(f"    [dim]{line}[/dim]")

                # 流式输出文本
                sys.stdout.write(chunk)
                sys.stdout.flush()
                full_content += chunk

        except Exception as e:
            console.print(f"\n[red]错误: {e}[/red]")
            stream_error = True
        finally:
            # 取消事件订阅
            agent.event_bus.off("tool_call", sub_tc)
            agent.event_bus.off("tool_result", sub_tr)

        if full_content and not stream_error:
            sys.stdout.write("\n")
            sys.stdout.flush()

        # 显示 token 用量
        cost = model_registry.total_cost
        total_tokens = model_registry.total_tokens
        if total_tokens > 0:
            console.print(
                f"[dim]  ↳ {total_tokens} tokens"
                f" | 累计 ${cost:.6f}[/dim]"
            )
        console.print()


def _json_dumps_short(obj: dict, max_len: int = 80) -> str:
    """简短的 JSON 字符串化。"""
    import json
    s = json.dumps(obj, ensure_ascii=False)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def main() -> None:
    """主入口。"""
    try:
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
