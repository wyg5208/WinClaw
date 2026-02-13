"""WinClaw GUI 应用程序。

整合 Qt UI、异步桥接、Agent 核心，提供完整的桌面应用体验。
支持：
- Agent 推理结果流式推送到 UI
- 工具调用状态实时显示
- 模型切换、会话管理
- 系统托盘 + 全局快捷键 + 设置 + 主题 (Sprint 2.2)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

from src.core.agent import Agent
from src.core.error_handler import install_error_handler, ErrorInfo
from src.core.workflow import WorkflowEngine
from src.core.workflow_loader import WorkflowLoader
from src.core.generated_files import GeneratedFilesManager
from src.models.registry import ModelRegistry
from src.tools.base import ToolResultStatus
from src.tools.registry import create_default_registry

from .async_bridge import AsyncBridge, TaskRunner, create_application, setup_async_bridge
from .hotkey import GlobalHotkey
from .keystore import inject_keys_to_env, needs_setup
from .main_window import MainWindow
from .settings_dialog import SettingsDialog
from .theme import Theme, apply_theme, get_stylesheet, get_theme_colors
from .tray import SystemTray

logger = logging.getLogger(__name__)


class GuiAgent(QObject):
    """GUI 封装的 Agent，处理流式输出和状态更新。

    将 Agent 的异步 chat 调用包装为 Qt 信号，
    使 UI 可以实时响应推理过程。
    """

    # 信号
    message_started = Signal()  # 开始生成
    message_chunk = Signal(str)  # 流式文本块
    message_finished = Signal(str)  # 完整消息
    tool_call_started = Signal(str, str)  # (tool_name, action)
    tool_call_finished = Signal(str, str, str)  # (tool_name, action, result_preview)
    error_occurred = Signal(str)  # 错误信息
    usage_updated = Signal(int, int, float)  # (input_tokens, output_tokens, cost)
    tts_requested = Signal(str)  # 请求 TTS 朗读

    def __init__(self, agent: Agent, model_registry: ModelRegistry) -> None:
        super().__init__()
        self._agent = agent
        self._model_registry = model_registry
        self._tts_enabled = False  # TTS 开关状态

    def set_tts_enabled(self, enabled: bool) -> None:
        """设置 TTS 开关。"""
        self._tts_enabled = enabled

    async def chat(self, message: str) -> None:
        """发送消息并流式接收回复。

        流程：
        1. 发出 message_started 信号
        2. 调用 Agent.chat_stream() 流式获取回复
        3. 实时发出 message_chunk 信号（真正的流式）
        4. 工具调用通过 EventBus 事件自动传递
        5. 发出 message_finished 信号
        6. 更新用量信息
        """
        self.message_started.emit()

        try:
            full_content = ""

            # 订阅工具调用事件，实时通知 UI
            _tool_sub_ids: list[tuple[str, int]] = []

            async def _on_tool_call(event_type, data):
                self.tool_call_started.emit(data.tool_name, data.action_name)

            async def _on_tool_result(event_type, data):
                result_preview = (data.output or "")[:200]
                self.tool_call_finished.emit(
                    data.tool_name, data.action_name, result_preview
                )

            sub_tc = self._agent.event_bus.on("tool_call", _on_tool_call)
            sub_tr = self._agent.event_bus.on("tool_result", _on_tool_result)
            _tool_sub_ids.append(("tool_call", sub_tc))
            _tool_sub_ids.append(("tool_result", sub_tr))

            try:
                async for chunk in self._agent.chat_stream(message):
                    full_content += chunk
                    self.message_chunk.emit(chunk)
            finally:
                # 取消工具事件订阅
                for evt_name, sub_id in _tool_sub_ids:
                    self._agent.event_bus.off(evt_name, sub_id)

            if full_content:
                self.message_finished.emit(full_content)

                # 如果 TTS 开启,请求朗读
                if self._tts_enabled:
                    self.tts_requested.emit(full_content)

            # 更新用量
            cost = self._model_registry.total_cost
            self.usage_updated.emit(0, 0, cost)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Agent chat 失败: %s", e, exc_info=True)
            self.error_occurred.emit(str(e))


class WinClawGuiApp:
    """WinClaw GUI 应用程序主类。"""

    def __init__(self) -> None:
        self._app: QApplication | None = None
        self._bridge: AsyncBridge | None = None
        self._window: MainWindow | None = None
        self._agent: Agent | None = None
        self._gui_agent: GuiAgent | None = None
        self._task_runner: TaskRunner | None = None
        self._model_registry: ModelRegistry | None = None
        self._tool_registry: object | None = None
        self._model_key_map: dict[str, str] = {}
        self._tray: SystemTray | None = None
        self._hotkey: GlobalHotkey | None = None
        self._current_theme = Theme.LIGHT
        
        # 当前运行的聊天任务（用于取消）
        self._current_chat_task: asyncio.Task | None = None
        
        # 语音功能状态
        self._recording_task = None  # 当前录音任务
        self._tts_enabled = False  # TTS 开关
        self._whisper_model = "base"  # Whisper 模型
        
        # 工作流组件
        self._workflow_engine: WorkflowEngine | None = None
        self._workflow_loader: WorkflowLoader | None = None

        # 生成文件管理器
        self._generated_files_manager = GeneratedFilesManager()
        
        # MCP 客户端管理器
        self._mcp_manager: object | None = None  # MCPClientManager

        # 历史会话缓存
        self._cached_history: list = []

    @staticmethod
    def _load_dotenv() -> None:
        """加载 .env 文件到环境变量（不覆盖已有值）。

        查找顺序：
        1. winclaw/.env（项目根目录）
        2. 当前工作目录/.env
        """
        try:
            from dotenv import load_dotenv
        except ImportError:
            logger.debug("python-dotenv 未安装，跳过 .env 加载")
            return

        # winclaw 项目根目录 = src/../ = gui_app.py 所在的 src/ui 的上两级
        project_root = Path(__file__).resolve().parent.parent.parent
        env_path = project_root / ".env"

        if not env_path.exists():
            # 回退到当前工作目录
            env_path = Path.cwd() / ".env"

        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
            logger.info("已加载 .env 配置: %s", env_path)
        else:
            logger.debug("未找到 .env 文件")

    def run(self) -> int:
        """运行应用程序。返回退出码。"""
        # 创建 Qt 应用
        self._app = create_application()

        # 加载 .env 文件（不覆盖已有环境变量）
        self._load_dotenv()

        # 从 keyring 注入密钥到环境变量
        injected = inject_keys_to_env()
        if injected:
            logger.info("从安全存储注入了 %d 个 API Key", injected)

        # 安装全局异常处理器
        self._setup_global_error_handler()

        # 设置异步桥接
        self._bridge = setup_async_bridge(self._app)

        # 初始化核心组件
        try:
            self._initialize_components()
        except Exception as e:
            QMessageBox.critical(
                None,
                "初始化错误",
                f"应用程序初始化失败:\n{e}\n\n请检查配置文件和 API Key 设置。",
            )
            return 1

        # 应用主题
        self._current_theme = Theme.LIGHT
        apply_theme(self._app, self._current_theme)

        # 创建主窗口
        self._window = MainWindow(self._bridge, minimize_to_tray=True)

        # 同步聊天区域主题
        self._apply_chat_theme(self._current_theme)
        self._setup_signals()

        # 系统托盘
        self._tray = SystemTray(self._window, self._app)
        self._tray.new_session_requested.connect(self._window._on_new_session)
        self._tray.settings_requested.connect(self._open_settings)
        self._tray.show()

        # 全局快捷键
        self._hotkey = GlobalHotkey()
        self._hotkey.triggered.connect(self._toggle_window)
        self._hotkey.start()

        self._window.show()
        self._window.set_connection_status(True)

        # 预加载历史会话列表（同步快速读取，不阻塞 UI）
        self._preload_history_sessions()

        # 首次启动引导
        if needs_setup():
            self._open_settings()

        # 启动事件循环
        try:
            loop = self._bridge._loop
            if loop is not None:
                with loop:
                    loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

        return 0

    def _initialize_components(self) -> None:
        """初始化核心组件（模型注册表、工具注册表、Agent）。"""
        # 模型注册表
        self._model_registry = ModelRegistry()
        models = self._model_registry.list_models()

        if not models:
            raise RuntimeError("未找到任何模型配置，请检查 config/models.toml")

        # 工具注册表
        self._tool_registry = create_default_registry()

        # 选择默认模型
        default_key = "deepseek-chat"
        if self._model_registry.get(default_key) is None:
            default_key = models[0].key

        # 创建 Agent
        self._agent = Agent(
            model_registry=self._model_registry,
            tool_registry=self._tool_registry,
            model_key=default_key,
        )

        # 创建 GUI Agent 包装器
        self._gui_agent = GuiAgent(self._agent, self._model_registry)

        # 任务运行器
        if self._bridge is not None:
            self._task_runner = TaskRunner(self._bridge)
        
        # 初始化工作流引擎和加载器
        self._workflow_engine = WorkflowEngine(
            tool_registry=self._tool_registry,
            event_bus=self._agent.event_bus,
        )
        self._workflow_loader = WorkflowLoader(self._workflow_engine)
        loaded_count = self._workflow_loader.load_all_templates()
        logger.info(f"已加载 {loaded_count} 个工作流模板")

        # 构建 name -> key 映射
        for m in models:
            self._model_key_map[m.name] = m.key
        
        # 初始化 MCP 客户端管理器（异步初始化）
        self._initialize_mcp()

    def _initialize_mcp(self) -> None:
        """初始化 MCP 客户端管理器并连接已启用的 Server。"""
        import json
        from pathlib import Path
        from src.core.mcp_client import MCPClientManager, MCPServerConfig
        
        # 创建管理器
        self._mcp_manager = MCPClientManager()
        
        # 加载配置
        config_path = Path(__file__).parent.parent.parent / "config" / "mcp_servers.json"
        if not config_path.exists():
            logger.debug("MCP 配置文件不存在")
            return
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            servers = data.get("mcpServers", {})
            enabled_servers = [
                MCPServerConfig.from_dict(name, cfg)
                for name, cfg in servers.items()
                if cfg.get("enabled", False)
            ]
            
            if not enabled_servers:
                logger.debug("没有启用的 MCP Server")
                return
            
            # 异步连接 MCP Server
            async def _connect_mcp_servers():
                for config in enabled_servers:
                    try:
                        success = await self._mcp_manager.connect_server(config)
                        if success:
                            # 注册到工具注册表
                            from src.tools.mcp_bridge import create_mcp_bridge_tools
                            create_mcp_bridge_tools(
                                self._mcp_manager,
                                self._tool_registry
                            )
                    except Exception as e:
                        logger.warning("连接 MCP Server %s 失败: %s", config.name, e)
            
            # 使用异步桥接执行
            if self._bridge and self._bridge._loop:
                import asyncio
                future = asyncio.run_coroutine_threadsafe(
                    _connect_mcp_servers(),
                    self._bridge._loop
                )
                # 不等待完成，让它在后台连接
                logger.info("MCP Server 连接任务已启动")
                
        except Exception as e:
            logger.warning("加载 MCP 配置失败: %s", e)

    def _setup_signals(self) -> None:
        """设置 UI 信号与 Agent 的连接。"""
        if not self._window or not self._gui_agent:
            return

        # 用户发送消息 → 触发 Agent chat
        self._window.message_sent.connect(self._on_user_message)
        self._window.message_with_attachments.connect(self._on_user_message_with_attachments)

        # 停止按钮
        self._window.stop_requested.connect(self._on_stop)

        # 模型切换
        self._window.model_changed.connect(self._on_model_changed)

        # Agent → UI 信号连接
        self._gui_agent.message_started.connect(
            lambda: (
                self._window.set_tool_status("生成中..."),
                self._window.clear_tool_log(),
            )
        )
        self._gui_agent.message_chunk.connect(
            self._window.append_ai_message  # type: ignore
        )
        self._gui_agent.message_finished.connect(
            lambda _: (
                self._window.set_tool_status("完成"),
                self._window._set_thinking_state(False),
            )
        )
        self._gui_agent.tool_call_started.connect(
            lambda name, action: (
                self._window.set_tool_status(f"执行: {name}.{action}"),
                self._window.add_tool_log(f"▶ {name}.{action}"),
            )
        )
        self._gui_agent.tool_call_finished.connect(
            lambda name, action, result: self._window.add_tool_log(
                f"✔ {name}.{action} → {result[:60]}"
            )
        )
        self._gui_agent.error_occurred.connect(
            lambda msg: (
                self._window.add_ai_message(f"抱歉，AI 模型调用失败: {msg}"),
                self._window._set_thinking_state(False),
            )
        )
        self._gui_agent.usage_updated.connect(
            self._window.update_usage  # type: ignore
        )
        
        # TTS 朗读
        self._gui_agent.tts_requested.connect(self._on_tts_speak)

        # 设置对话框
        self._window.settings_requested.connect(self._open_settings)

        # 图片附件选择 -> OCR 识别
        self._window.image_selected.connect(self._on_image_selected)

        # 语音功能
        self._window.voice_record_requested.connect(self._on_voice_record)
        self._window.voice_stop_requested.connect(self._on_voice_stop)
        self._window.tts_toggle_requested.connect(self._on_tts_toggle)

        # 生成空间
        self._window.generated_space_requested.connect(self._on_open_generated_space)

        # 历史对话
        self._window.history_requested.connect(self._on_open_history)

        # 设置模型列表
        models = self._model_registry.list_models() if self._model_registry else []
        model_names = [m.name for m in models]
        self._window.set_models(model_names)

        # 设置当前模型
        if self._agent and self._model_registry:
            cfg = self._model_registry.get(self._agent.model_key)
            if cfg:
                self._window.set_current_model(cfg.name)
        
        # 工作流面板信号连接
        self._window.workflow_panel.cancel_requested.connect(self._on_workflow_cancel)
        
        # 设置工作流事件订阅
        self._setup_workflow_events()

        # 设置文件生成事件订阅
        self._setup_file_generated_events()

    def _on_user_message(self, message: str) -> None:
        """处理用户消息。"""
        if not self._gui_agent or not self._task_runner:
            return

        # 内部命令
        if message == "/new_session":
            if self._agent:
                self._agent.reset()
            return
        
        # 检查是否触发工作流
        if self._workflow_loader:
            matched_workflow = self._workflow_loader.match_trigger(message)
            if matched_workflow:
                if self._window:
                    self._window.add_tool_log(f"📊 触发工作流: {matched_workflow}")
                self._task_runner.run(
                    "workflow",
                    self._execute_workflow(matched_workflow, message)
                )
                return

        # 运行 Agent chat 任务，并跟踪当前任务
        self._current_chat_task = self._task_runner.run("chat", self._gui_agent.chat(message))
    
    def _on_stop(self) -> None:
        """停止当前运行的任务。"""
        if self._current_chat_task and not self._current_chat_task.done():
            self._current_chat_task.cancel()
            logger.info("用户取消了当前任务")
            if self._window:
                self._window.add_ai_message("\n[已取消]")
                self._window._set_thinking_state(False)
        self._current_chat_task = None
    
    def _setup_global_error_handler(self) -> None:
        """设置全局异常处理器。"""
        def on_error(error_info: ErrorInfo) -> None:
            """全局错误回调。"""
            logger.error("全局异常: %s - %s", error_info.category.value, error_info.message)
            # 在主线程中显示错误（通过 Qt 信号机制）
            if self._window:
                try:
                    QMessageBox.warning(
                        self._window,
                        "错误",
                        error_info.to_display(),
                    )
                except Exception:
                    pass  # Qt 可能还未准备好

        install_error_handler(on_error=on_error)
    
    async def _execute_workflow(self, workflow_name: str, user_input: str) -> None:
        """执行工作流。"""
        if not self._workflow_loader or not self._window:
            return
        
        try:
            template = self._workflow_loader.get_template(workflow_name)
            if template:
                # 启动工作流面板
                steps_info = [
                    {"id": s.id, "name": s.name}
                    for s in template.definition.steps
                ]
                self._window.workflow_panel.start_workflow(
                    workflow_name,
                    template.definition.description,
                    steps_info
                )
            
            # 执行工作流
            context = await self._workflow_loader.execute_template(workflow_name)
            
            # 显示结果
            if context.status.value == "completed":
                self._window.add_tool_log(f"✅ 工作流执行成功")
            else:
                self._window.add_tool_log(f"❌ 工作流执行失败: {context.error}")
        
        except Exception as e:
            logger.error(f"工作流执行失败: {e}")
            self._window.add_tool_log(f"❌ 工作流错误: {e}")
        finally:
            self._window.workflow_panel.reset()

    def _on_user_message_with_attachments(self, message: str, attachments: list) -> None:
        """处理带附件的用户消息。"""
        if not self._gui_agent or not self._task_runner:
            return
        
        # 构建附件上下文
        attachment_context = self._build_attachment_context(attachments)
        
        # 将附件信息添加到消息前面
        full_message = f"{attachment_context}\n用户请求: {message}"
        
        # 显示附件信息
        if self._window:
            self._window.add_tool_log(f"📎 发送 {len(attachments)} 个附件")
        
        # 运行 Agent chat 任务
        self._task_runner.run("chat", self._gui_agent.chat(full_message))
    
    def _build_attachment_context(self, attachments: list) -> str:
        """构建附件上下文描述。"""
        if not attachments:
            return ""
        
        lines = ["[附件信息]"]
        for att in attachments:
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

    def _on_model_changed(self, model_name: str) -> None:
        """处理模型切换。"""
        if not self._agent:
            return
        key = self._model_key_map.get(model_name)
        if key:
            self._agent.model_key = key
            logger.info("模型切换为: %s (%s)", model_name, key)

    def _toggle_window(self) -> None:
        """切换窗口显示/隐藏（全局快捷键触发）。"""
        if not self._window:
            return
        if self._window.isVisible():
            self._window.hide()
        else:
            self._window.show()
            self._window.raise_()
            self._window.activateWindow()

    def _open_settings(self) -> None:
        """打开设置对话框。"""
        models = [m.name for m in (self._model_registry.list_models() if self._model_registry else [])]
        current_model = ""
        if self._agent and self._model_registry:
            cfg = self._model_registry.get(self._agent.model_key)
            if cfg:
                current_model = cfg.name

        dlg = SettingsDialog(
            self._window,
            current_theme=self._current_theme.value,
            current_model=current_model,
            available_models=models,
            current_hotkey=self._hotkey.hotkey if self._hotkey else "Win+Shift+Space",
            current_whisper_model=self._whisper_model,
            mcp_manager=self._mcp_manager,
        )
        dlg.theme_changed.connect(self._on_theme_changed)
        dlg.model_changed.connect(self._on_model_changed)
        dlg.hotkey_changed.connect(self._on_hotkey_changed)
        dlg.keys_updated.connect(lambda: logger.info("API Key 已更新"))
        dlg.whisper_model_changed.connect(self._on_whisper_model_changed)
        dlg.exec()

    def _on_theme_changed(self, theme_str: str) -> None:
        """切换主题。"""
        theme = Theme(theme_str)
        self._current_theme = theme
        if self._app:
            apply_theme(self._app, theme)
        self._apply_chat_theme(theme)

    def _apply_chat_theme(self, theme: Theme) -> None:
        """同步聊天区域主题颜色。"""
        if self._window:
            colors = get_theme_colors(theme)
            self._window._chat_widget.apply_theme(colors)

    def _on_hotkey_changed(self, hotkey: str) -> None:
        """更新快捷键。"""
        # 将显示格式转为 pynput 格式
        hk = hotkey.lower().replace("win", "<cmd>").replace("+", "+")
        for part in ["shift", "ctrl", "alt"]:
            hk = hk.replace(part, f"<{part}>")
        # 防止重复尖括号
        import re
        hk = re.sub(r"<(<[^>]+>)>", r"\1", hk)
        if self._hotkey:
            self._hotkey.set_hotkey(hk)

    def _on_image_selected(self, image_path: str) -> None:
        """处理图片选择，进行 OCR 识别。"""
        if not self._task_runner or not self._window:
            return
        
        # 更新状态
        self._window.set_tool_status("图片 OCR 识别中...")
        self._window.add_tool_log(f"📷 开始识别: {image_path.split('/')[-1].split(chr(92))[-1]}")
        
        # 启动 OCR 任务
        self._task_runner.run(
            "ocr_recognize",
            self._recognize_image(image_path)
        )

    async def _recognize_image(self, image_path: str) -> None:
        """OCR 识别图片。"""
        try:
            from src.tools.ocr import OCRTool
            
            tool = OCRTool()
            
            # 识别图片
            result = await tool.execute(
                "recognize_file",
                {"image_path": image_path, "merge_lines": True}
            )
            
            if result.status == ToolResultStatus.SUCCESS and self._window:
                text = result.data.get("text", "") if result.data else ""
                line_count = result.data.get("line_count", 0) if result.data else 0
                
                if text.strip():
                    # 将识别结果填入输入框
                    self._window.set_input_text(text)
                    self._window.set_tool_status(f"OCR 完成: {line_count} 行文字")
                    self._window.add_tool_log(f"✅ OCR 识别成功: {len(text)} 字符")
                    
                    # 在聊天区显示识别结果预览
                    preview_text = text[:200] + ("..." if len(text) > 200 else "")
                    self._window._chat_widget.add_ai_message(
                        f"📝 OCR 识别结果 ({line_count} 行):\n```\n{preview_text}\n```\n"
                        f"\nℹ️ 识别文字已填入输入框，可以进行编辑或直接发送。"
                    )
                else:
                    self._window.set_tool_status("未识别到文字")
                    self._window.add_tool_log("⚠️ 图片中未识别到文字")
            else:
                if self._window:
                    error_msg = result.error or "OCR 识别失败"
                    self._window.set_tool_status(f"OCR 失败: {error_msg}")
                    self._window.add_tool_log(f"❌ {error_msg}")
        
        except ImportError as e:
            logger.error("OCR 工具不可用: %s", e)
            if self._window:
                self._window.set_tool_status("OCR 功能不可用")
                self._window.add_tool_log("❌ OCR 功能需要安装: pip install rapidocr-onnxruntime pillow")
                QMessageBox.warning(
                    self._window,
                    "OCR 功能不可用",
                    "OCR 功能需要安装额外依赖\n\n请运行: pip install rapidocr-onnxruntime pillow",
                )
        except Exception as e:
            logger.exception("OCR 识别错误")
            if self._window:
                self._window.set_tool_status(f"OCR 错误: {e}")
                self._window.add_tool_log(f"❌ OCR 错误: {e}")
        finally:
            if self._window:
                self._window.set_tool_status("空闲")

    def _cleanup(self) -> None:
        """清理资源。"""
        # 取消当前任务
        if self._current_chat_task and not self._current_chat_task.done():
            self._current_chat_task.cancel()
            self._current_chat_task = None
        
        # 清理所有工具
        if self._tool_registry:
            for tool in self._tool_registry.list_tools():
                try:
                    if hasattr(tool, 'close'):
                        import asyncio
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(tool.close())
                        else:
                            loop.run_until_complete(tool.close())
                except Exception as e:
                    logger.warning("工具 %s 清理失败: %s", tool.name, e)
        
        if self._hotkey:
            self._hotkey.stop()
        if self._tray:
            self._tray.hide()
        if self._task_runner:
            self._task_runner.cancel_all()

    # ===== 历史对话相关 =====

    def _get_storage(self):
        """获取 ChatStorage 实例（从 Agent 的 SessionManager 中取）。"""
        if self._agent and self._agent.session_manager._storage:
            return self._agent.session_manager._storage
        return None

    def _preload_history_sessions(self) -> None:
        """预加载历史会话列表（应用启动后调用，同步快速读取）。"""
        storage = self._get_storage()
        if not storage:
            return
        try:
            self._cached_history = storage.list_sessions_sync(limit=100)
            logger.info("预加载了 %d 个历史会话", len(self._cached_history))
        except Exception as e:
            logger.warning("预加载历史会话失败: %s", e)
            self._cached_history = []

    def _on_open_history(self) -> None:
        """打开历史对话对话框（纯同步，不阻塞事件循环）。"""
        if not self._window or not self._agent:
            return

        from .history_dialog import HistoryDialog

        storage = self._get_storage()
        sessions_data: list[dict] = []

        if storage:
            try:
                # 同步读取全部历史会话（直接用 sqlite3，无死锁）
                stored_sessions = storage.list_sessions_sync(limit=100)
                for st in stored_sessions:
                    msg_count = storage.get_message_count_sync(st.id)
                    sessions_data.append({
                        "id": st.id,
                        "title": st.title,
                        "updated_at": st.updated_at.isoformat(),
                        "message_count": msg_count,
                    })
            except Exception as e:
                logger.warning("读取历史会话列表失败: %s", e, exc_info=True)
        else:
            # 无持久化存储，只显示内存中的会话
            session_mgr = self._agent.session_manager
            for s in session_mgr.list_sessions():
                msg_count = sum(
                    1 for m in s.messages if m.get("role") != "system"
                )
                sessions_data.append({
                    "id": s.id,
                    "title": s.title,
                    "updated_at": s.created_at.isoformat(),
                    "message_count": msg_count,
                })

        dlg = HistoryDialog(sessions_data, self._window)
        dlg.session_selected.connect(self._restore_session)
        dlg.exec()

    def _restore_session(self, session_id: str) -> None:
        """恢复指定会话到聊天区域（纯同步，不阻塞事件循环）。"""
        if not self._agent or not self._window:
            return

        session_mgr = self._agent.session_manager
        storage = self._get_storage()

        # 如果会话不在内存中，从 SQLite 同步加载
        if session_id not in session_mgr._sessions:
            if not storage:
                QMessageBox.warning(
                    self._window, "加载失败",
                    "该会话已不在内存中，且未启用持久化存储。",
                )
                return

            try:
                # 同步加载会话元数据
                stored = storage.load_session_sync(session_id)
                if stored is None:
                    QMessageBox.warning(
                        self._window, "加载失败",
                        f"未找到会话 {session_id}，可能已被删除。",
                    )
                    return

                # 创建 Session 对象并注册到内存
                from src.core.session import Session
                session = Session(
                    id=stored.id,
                    title=stored.title,
                    model_key=stored.model_key,
                    created_at=stored.created_at,
                    messages=[],
                    total_tokens=stored.total_tokens,
                    metadata=stored.metadata,
                )
                # 添加 system prompt
                if session_mgr._system_prompt:
                    session.messages.append({
                        "role": "system",
                        "content": session_mgr._system_prompt,
                    })

                # 同步加载所有消息
                stored_msgs = storage.load_messages_sync(session_id)
                for sm in stored_msgs:
                    msg = sm.to_dict()
                    if msg.get("role") == "system" and session.has_system_prompt:
                        continue
                    session.messages.append(msg)

                session_mgr._sessions[session_id] = session
                logger.info("从存储加载会话 %s: %d 条消息", session_id, len(stored_msgs))

            except Exception as e:
                logger.error("加载会话消息失败: %s", e, exc_info=True)
                QMessageBox.warning(
                    self._window, "加载失败",
                    f"无法加载历史会话消息:\n{e}",
                )
                return

        # 切换到该会话
        try:
            session = session_mgr.switch_session(session_id)
        except ValueError as e:
            logger.error("切换会话失败: %s", e)
            return

        # 清空聊天区域并填充历史消息
        self._window._chat_widget.clear()
        self._window._session_info.setText(session.title)

        for msg in session.messages:
            role = msg.get("role", "")
            content = str(msg.get("content", ""))
            if role == "user":
                self._window._chat_widget.add_user_message(content)
            elif role == "assistant" and content:
                self._window._chat_widget.add_ai_message(content)
            # system / tool 消息不显示

        self._window.add_tool_log(f"📋 已恢复对话: {session.title}")

    # ===== 生成空间相关 =====

    def _setup_file_generated_events(self) -> None:
        """订阅文件生成事件。"""
        if not self._agent:
            return

        event_bus = self._agent.event_bus

        async def on_file_generated(event_type, data) -> None:
            """文件生成事件处理。"""
            file_path = data.file_path if hasattr(data, "file_path") else data.get("file_path", "")
            source_tool = data.source_tool if hasattr(data, "source_tool") else data.get("source_tool", "")
            source_action = data.source_action if hasattr(data, "source_action") else data.get("source_action", "")
            session_id = data.session_id if hasattr(data, "session_id") else data.get("session_id", "")

            if not file_path:
                return

            info = self._generated_files_manager.register_file(
                file_path=file_path,
                source_tool=source_tool,
                source_action=source_action,
                session_id=session_id,
            )

            if info and self._window:
                self._window.update_generated_space_count(
                    self._generated_files_manager.count
                )
                self._window.add_tool_log(
                    f"📂 已记录生成文件: {info.name} ({info.size_display()})"
                )

        event_bus.on("file_generated", on_file_generated)

    def _on_open_generated_space(self) -> None:
        """打开生成空间对话框。"""
        if not self._window:
            return

        from .generated_space import GeneratedSpaceDialog

        dlg = GeneratedSpaceDialog(self._generated_files_manager, self._window)
        dlg.exec()

        # 对话框关闭后更新按钮计数
        self._window.update_generated_space_count(
            self._generated_files_manager.count
        )

    def _on_voice_record(self) -> None:
        """处理录音请求。"""
        if not self._task_runner or not self._window:
            return
        
        # 检查语音工具是否可用
        try:
            from src.tools.voice_input import VoiceInputTool
        except ImportError:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self._window,
                "语音功能不可用",
                "语音输入功能需要安装额外依赖\n\n请运行: pip install -e \".[voice]\"",
            )
            self._window.reset_voice_button()
            return
        
        # 更新状态
        self._window.set_tool_status("录音中... (5秒)")
        
        # 启动录音任务
        self._recording_task = self._task_runner.run(
            "voice_record",
            self._record_and_transcribe()
        )

    def _on_voice_stop(self) -> None:
        """处理停止录音请求。"""
        # 目前录音自动停止，此方法保留供未来扩展
        pass

    def _on_whisper_model_changed(self, model_name: str) -> None:
        """处理 Whisper 模型切换。"""
        self._whisper_model = model_name
        logger.info("Whisper 模型已切换为: %s", model_name)
        if self._window:
            self._window.add_tool_log(f"🎵 Whisper 模型已切换为: {model_name}")

    def _on_tts_toggle(self, enabled: bool) -> None:
        """处理 TTS 开关切换。"""
        self._tts_enabled = enabled
        # 同步到 GuiAgent
        if self._gui_agent:
            self._gui_agent.set_tts_enabled(enabled)
        
        logger.info("TTS 已%s", "开启" if enabled else "关闭")
        if self._window:
            status = "开启" if enabled else "关闭"
            self._window.add_tool_log(f"🔊 TTS 已{status}")

    def _on_tts_speak(self, text: str) -> None:
        """处理 TTS 朗读请求。"""
        if not self._task_runner or not self._window or not self._tts_enabled:
            return
        
        # 检查 TTS 工具是否可用
        try:
            from src.tools.voice_output import VoiceOutputTool
        except ImportError:
            logger.warning("TTS 功能不可用,需要安装: pip install -e '[voice]'")
            return
        
        # 启动 TTS 任务 (不阻塞 UI)
        self._task_runner.run(
            "tts_speak",
            self._speak_text(text)
        )

    async def _speak_text(self, text: str) -> None:
        """朗读文本。"""
        from src.tools.voice_output import VoiceOutputTool
        
        try:
            tool = VoiceOutputTool()
            
            # 限制朗读长度 (避免过长)
            max_length = 500
            if len(text) > max_length:
                text = text[:max_length] + "..."
            
            # 朗读
            result = await tool.execute(
                "speak",
                {"text": text, "rate": 200, "volume": 0.8}
            )
            
            if result.status == ToolResultStatus.SUCCESS:
                logger.info("TTS 朗读完成: %d 字符", len(text))
            else:
                logger.warning("TTS 朗读失败: %s", result.error)
        
        except Exception as e:
            logger.exception("TTS 朗读错误")
            if self._window:
                self._window.add_tool_log(f"❌ TTS 错误: {e}")

    async def _record_and_transcribe(self) -> None:
        """录音并转为文字。"""
        from src.tools.voice_input import VoiceInputTool
        
        try:
            tool = VoiceInputTool()
            
            # 使用配置的 Whisper 模型
            model = self._whisper_model
            logger.info("录音使用 Whisper 模型: %s", model)
            
            # 录音
            result = await tool.execute(
                "record_and_transcribe",
                {"duration": 5, "model": model, "language": "zh"}
            )
            
            if result.status == ToolResultStatus.SUCCESS and self._window:
                text = result.data.get("text", "")
                if text.strip():
                    # 将识别结果填入输入框
                    self._window.set_input_text(text)
                    self._window.set_tool_status(f"录音识别完成: {len(text)} 字")
                    self._window.add_tool_log(f"🎤 识别: {text[:50]}...")
                else:
                    self._window.set_tool_status("未识别到语音")
                    self._window.add_tool_log("⚠️ 未识别到有效语音")
            else:
                if self._window:
                    error_msg = result.error or "识别失败"
                    self._window.set_tool_status(f"录音失败: {error_msg}")
                    self._window.add_tool_log(f"❌ {error_msg}")
        
        except Exception as e:
            logger.exception("录音转文字失败")
            if self._window:
                self._window.set_tool_status(f"录音错误: {e}")
                self._window.add_tool_log(f"❌ 录音错误: {e}")
        
        finally:
            # 重置按钮状态
            if self._window:
                self._window.reset_voice_button()
                self._window.set_tool_status("空闲")
    
    # ===== 工作流相关 =====
    
    def _setup_workflow_events(self) -> None:
        """设置工作流事件订阅。"""
        if not self._agent:
            return
        
        # 订阅工作流事件
        event_bus = self._agent.event_bus
        
        async def on_workflow_started(data: dict) -> None:
            """工作流开始事件。"""
            if self._window:
                # 简化处理：记录日志
                self._window.add_tool_log(f"📊 工作流开始: {data.get('name', '')}")
        
        async def on_workflow_finished(data: dict) -> None:
            """工作流完成事件。"""
            if self._window:
                status = data.get('status', 'unknown')
                elapsed = data.get('elapsed', 0)
                self._window.add_tool_log(f"✅ 工作流完成: {status} ({elapsed:.1f}s)")
        
        async def on_step_started(data: dict) -> None:
            """步骤开始事件。"""
            if self._window:
                step_name = data.get('step_name', '')
                self._window.add_tool_log(f"  ▶ {step_name}")
        
        async def on_step_finished(data: dict) -> None:
            """步骤完成事件。"""
            if self._window:
                status = data.get('status', 'unknown')
                elapsed = data.get('elapsed', 0)
                icons = {'completed': '✔', 'failed': '✖', 'skipped': '⋆'}
                icon = icons.get(status, '●')
                self._window.add_tool_log(f"  {icon} ({elapsed:.1f}s)")
        
        event_bus.on("workflow_started", on_workflow_started)
        event_bus.on("workflow_finished", on_workflow_finished)
        event_bus.on("workflow_step_started", on_step_started)
        event_bus.on("workflow_step_finished", on_step_finished)
    
    def _on_workflow_cancel(self) -> None:
        """取消工作流。"""
        # TODO: 实现工作流取消逻辑
        if self._window:
            self._window.add_tool_log("⚠️ 工作流取消功能待实现")
            self._window.workflow_panel.reset()


def main() -> int:
    """GUI 应用程序入口。"""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    app = WinClawGuiApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
