"""WinClaw 主窗口。

布局：
- 顶部：标题栏（窗口控制 + 模型选择）
- 中部：聊天区域（消息气泡列表）
- 底部：输入区域（多行输入框 + 发送按钮 + 附件面板）
- 右侧：状态面板（工具执行状态、Token 用量）
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtCore import Qt, QEvent, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .attachment_manager import AttachmentManager
from .attachment_panel import AttachmentPanel
from .workflow_panel import WorkflowPanel

if TYPE_CHECKING:
    from .async_bridge import AsyncBridge

logger = logging.getLogger(__name__)


class ChatInputEdit(QTextEdit):
    """自定义输入框：Enter 发送，Shift+Enter 换行。"""

    send_requested = Signal()

    def keyPressEvent(self, event) -> None:
        """拦截回车键。"""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+Enter → 换行
                super().keyPressEvent(event)
            else:
                # Enter → 发送
                self.send_requested.emit()
        else:
            super().keyPressEvent(event)


class MainWindow(QMainWindow):
    """WinClaw 主窗口。"""

    # 信号
    message_sent = Signal(str)  # 用户发送的消息
    message_with_attachments = Signal(str, list)  # 用户发送的消息 + 附件列表
    attachment_requested = Signal()  # 请求添加附件
    image_selected = Signal(str)  # 图片文件路径被选择 (兼容旧版)
    model_changed = Signal(str)  # 模型切换
    settings_requested = Signal()  # 打开设置
    close_to_tray = Signal()  # 关闭到托盘
    voice_record_requested = Signal()  # 请求录音
    voice_stop_requested = Signal()  # 请求停止录音
    tts_toggle_requested = Signal(bool)  # 请求切换 TTS
    generated_space_requested = Signal()  # 打开生成空间
    stop_requested = Signal()  # 请求停止当前任务
    history_requested = Signal()  # 打开历史对话

    def __init__(self, bridge: AsyncBridge | None = None, *, minimize_to_tray: bool = True) -> None:
        super().__init__()
        self._bridge = bridge
        self._minimize_to_tray = minimize_to_tray
        self._force_quit = False
        self._tool_log_entries: list[str] = []
        self._is_recording = False  # 录音状态
        self._tts_enabled = False  # TTS 开启状态
        
        # 附件管理器
        self._attachment_manager = AttachmentManager(self)
        
        self._setup_window()
        self._setup_menu_bar()
        self._setup_tool_bar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._setup_shortcuts()

    def _setup_window(self) -> None:
        """设置窗口属性。"""
        self.setWindowTitle("WinClaw - AI 桌面智能体")
        self.setMinimumSize(900, 375)
        self.resize(1200, 600)
        self.setWindowIcon(QIcon())  # 后续添加图标

    def _setup_menu_bar(self) -> None:
        """设置菜单栏。"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        
        new_session_action = QAction("新建会话(&N)", self)
        new_session_action.setShortcut(QKeySequence.StandardKey.New)
        new_session_action.triggered.connect(self._on_new_session)
        file_menu.addAction(new_session_action)

        history_action = QAction("历史对话(&H)...", self)
        history_action.setShortcut(QKeySequence("Ctrl+H"))
        history_action.triggered.connect(self._on_history)
        file_menu.addAction(history_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&Q)", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 编辑菜单
        edit_menu = menubar.addMenu("编辑(&E)")

        clear_action = QAction("清空对话(&C)", self)
        clear_action.setShortcut("Ctrl+L")
        clear_action.triggered.connect(self._on_clear_chat)
        edit_menu.addAction(clear_action)

        # 工具菜单
        tools_menu = menubar.addMenu("工具(&T)")

        gen_space_action = QAction("📂 生成空间(&G)...", self)
        gen_space_action.setShortcut(QKeySequence("Ctrl+G"))
        gen_space_action.triggered.connect(self._on_generated_space)
        tools_menu.addAction(gen_space_action)

        tools_menu.addSeparator()

        settings_action = QAction("设置(&S)...", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._on_settings)
        tools_menu.addAction(settings_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("关于(&A)...", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _setup_tool_bar(self) -> None:
        """设置工具栏。"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # 模型选择下拉框
        model_label = QLabel("模型:")
        toolbar.addWidget(model_label)

        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(200)
        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        toolbar.addWidget(self._model_combo)

        toolbar.addSeparator()

        # 新建会话按钮
        new_btn = QPushButton("新建会话")
        new_btn.clicked.connect(self._on_new_session)
        toolbar.addWidget(new_btn)

        # 历史对话按钮
        history_btn = QPushButton("📋 历史对话")
        history_btn.setToolTip("查看历史对话记录 (Ctrl+H)")
        history_btn.clicked.connect(self._on_history)
        toolbar.addWidget(history_btn)

        toolbar.addSeparator()

        # 清空按钮
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._on_clear_chat)
        toolbar.addWidget(clear_btn)

        toolbar.addSeparator()

        # 语音输入按钮 (麦克风)
        self._voice_btn = QPushButton("🎤 录音")
        self._voice_btn.setToolTip("按住录音,松开发送 (Ctrl+R)")
        self._voice_btn.setCheckable(False)
        self._voice_btn.clicked.connect(self._on_voice_record)
        toolbar.addWidget(self._voice_btn)

        # TTS 开关按钮
        self._tts_btn = QPushButton("🔇 TTS")
        self._tts_btn.setToolTip("切换 AI 回复自动朗读")
        self._tts_btn.setCheckable(True)
        self._tts_btn.setChecked(False)
        self._tts_btn.clicked.connect(self._on_tts_toggle)
        toolbar.addWidget(self._tts_btn)

        toolbar.addSeparator()

        # 生成空间按钮
        self._gen_space_btn = QPushButton("📂 生成空间")
        self._gen_space_btn.setToolTip("查看 AI 生成的所有文件")
        self._gen_space_btn.clicked.connect(self._on_generated_space)
        toolbar.addWidget(self._gen_space_btn)

        # 生成空间文件计数徽标
        self._gen_space_count = 0

    def _setup_central_widget(self) -> None:
        """设置中央部件。"""
        central = QWidget()
        self.setCentralWidget(central)

        # 主布局：水平分割器
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # 左侧：聊天区域
        left_widget = self._create_chat_area()
        splitter.addWidget(left_widget)

        # 右侧：状态面板
        right_widget = self._create_status_panel()
        splitter.addWidget(right_widget)

        # 设置分割比例
        splitter.setSizes([800, 400])

    def _create_chat_area(self) -> QWidget:
        """创建聊天区域。"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 聊天显示区域
        from .chat import ChatWidget
        self._chat_widget = ChatWidget()
        layout.addWidget(self._chat_widget, stretch=1)

        # 输入区域
        input_widget = self._create_input_area()
        layout.addWidget(input_widget)

        return widget

    def _create_input_area(self) -> QWidget:
        """创建输入区域。"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # 附件面板
        self._attachment_panel = AttachmentPanel(self._attachment_manager)
        self._attachment_panel.add_files_requested.connect(self._on_attachment)
        self._attachment_panel.file_removed.connect(self._on_attachment_removed)
        self._attachment_panel.clear_requested.connect(self._on_attachments_clear)
        self._attachment_panel.files_dropped.connect(self._on_files_dropped)
        layout.addWidget(self._attachment_panel)

        # 输入框（自定义键监听）
        self._input_edit = ChatInputEdit()
        self._input_edit.send_requested.connect(self._on_send)
        self._input_edit.setPlaceholderText("输入消息... (Enter 发送, Shift+Enter 换行)")
        self._input_edit.setMaximumHeight(120)
        self._input_edit.setMinimumHeight(60)
        layout.addWidget(self._input_edit)

        # 按钮行
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # 附件按钮
        self._attach_btn = QPushButton("📎 添加文件")
        self._attach_btn.setToolTip("添加图片或文件附件")
        self._attach_btn.clicked.connect(self._on_attachment)
        button_layout.addWidget(self._attach_btn)

        button_layout.addStretch()

        # 发送按钮
        self._send_btn = QPushButton("发送")
        self._send_btn.setDefault(True)
        self._send_btn.setMinimumWidth(80)
        self._send_btn.clicked.connect(self._on_send)
        button_layout.addWidget(self._send_btn)

        # 停止按钮（默认隐藏）
        self._stop_btn = QPushButton("停止")
        self._stop_btn.setMinimumWidth(80)
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self._on_stop)
        button_layout.addWidget(self._stop_btn)

        layout.addLayout(button_layout)

        return widget

    def _create_status_panel(self) -> QWidget:
        """创建右侧状态面板（P2-11 增强版）。"""
        widget = QWidget()
        widget.setMinimumWidth(250)
        widget.setMaximumWidth(400)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 会话信息
        session_group = QGroupBox("当前会话")
        session_layout = QVBoxLayout(session_group)
        self._session_info = QLabel("新会话")
        self._session_info.setWordWrap(True)
        session_layout.addWidget(self._session_info)
        layout.addWidget(session_group)

        # Token 用量
        usage_group = QGroupBox("Token 用量")
        usage_layout = QVBoxLayout(usage_group)
        self._token_label = QLabel("输入: 0 | 输出: 0")
        usage_layout.addWidget(self._token_label)
        self._cost_label = QLabel("费用: $0.0000")
        usage_layout.addWidget(self._cost_label)
        layout.addWidget(usage_group)

        # 工具执行状态（P2-11 新增实时日志）
        tools_group = QGroupBox("工具执行状态")
        tools_layout = QVBoxLayout(tools_group)

        self._tool_status = QLabel("空闲")
        tools_layout.addWidget(self._tool_status)

        # 进度条
        self._tool_progress = QProgressBar()
        self._tool_progress.setRange(0, 0)  # 不确定进度
        self._tool_progress.setMaximumHeight(6)
        self._tool_progress.setVisible(False)
        tools_layout.addWidget(self._tool_progress)

        # 工具执行日志滚动区
        self._tool_log = QLabel("")
        self._tool_log.setWordWrap(True)
        self._tool_log.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._tool_log.setStyleSheet("font-size: 12px;")

        self._tool_log_scroll = QScrollArea()
        self._tool_log_scroll.setWidgetResizable(True)
        self._tool_log_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._tool_log_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._tool_log_scroll.setMinimumHeight(60)
        self._tool_log_scroll.setMaximumHeight(180)
        self._tool_log_scroll.setWidget(self._tool_log)
        tools_layout.addWidget(self._tool_log_scroll)

        layout.addWidget(tools_group)

        # 工作流状态面板
        self._workflow_panel = WorkflowPanel()
        layout.addWidget(self._workflow_panel)

        layout.addStretch()
        return widget

    def _setup_status_bar(self) -> None:
        """设置状态栏（P2-12 增强版）。"""
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        # 左侧：模型名
        self._status_model = QLabel("模型: 未选择")
        self._status_bar.addWidget(self._status_model)

        # 中间：Token 简报
        self._status_tokens = QLabel("")
        self._status_tokens.setStyleSheet("margin-left: 16px;")
        self._status_bar.addWidget(self._status_tokens)

        # 右侧：连接状态
        self._status_connection = QLabel("● 未连接")
        self._status_connection.setStyleSheet("color: #888;")
        self._status_bar.addPermanentWidget(self._status_connection)

    def _setup_shortcuts(self) -> None:
        """设置快捷键。"""
        # Ctrl+L 清空
        clear_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        clear_shortcut.activated.connect(self._on_clear_chat)

    def closeEvent(self, event: QCloseEvent) -> None:
        """拦截关闭事件 → 最小化到托盘。"""
        if self._minimize_to_tray and not self._force_quit:
            event.ignore()
            self.hide()
            self.close_to_tray.emit()
        else:
            event.accept()

    def force_quit(self) -> None:
        """强制退出（不最小化到托盘）。"""
        self._force_quit = True
        self.close()

    # ===== 事件处理 =====

    def _on_send(self) -> None:
        """发送消息。"""
        text = self._input_edit.toPlainText().strip()
        if not text:
            return

        # 添加到聊天显示
        self._chat_widget.add_user_message(text)
        
        # 清空输入框
        self._input_edit.clear()

        # 获取附件列表
        attachments = self._attachment_manager.attachments
        
        # 发出信号（包含附件信息）
        if attachments:
            self.message_with_attachments.emit(text, attachments)
            # 清空附件
            self._attachment_manager.clear()
        else:
            self.message_sent.emit(text)

        # 显示思考中状态
        self._set_thinking_state(True)

    def _on_stop(self) -> None:
        """停止生成。"""
        self.stop_requested.emit()

    def _on_attachment(self) -> None:
        """添加附件 - 打开多选文件对话框。"""
        file_filter = (
            "所有支持的文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.txt *.md *.csv *.log "
            "*.json *.xml *.yaml *.yml *.py *.js *.java *.cpp *.c *.html *.css);;"
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;"
            "文本文件 (*.txt *.md *.csv *.log *.json *.xml *.yaml *.yml);;"
            "代码文件 (*.py *.js *.java *.cpp *.c *.html *.css);;"
            "所有文件 (*.*)"
        )
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择要添加的文件",
            "",
            file_filter
        )
        
        if file_paths:
            success, errors = self._attachment_manager.add_files(file_paths)
            if errors:
                # 显示错误信息
                self.add_tool_log(f"⚠️ 部分文件添加失败: {len(errors)} 个")
            if success > 0:
                self.add_tool_log(f"📎 已添加 {success} 个文件")
    
    def _on_attachment_removed(self, file_path: str) -> None:
        """附件被移除。"""
        self._attachment_manager.remove_file(file_path)
    
    def _on_attachments_clear(self) -> None:
        """清空所有附件。"""
        self._attachment_manager.clear()
    
    def _on_files_dropped(self, file_paths: List[str]) -> None:
        """文件被拖放到附件面板。"""
        success, errors = self._attachment_manager.add_files(file_paths)
        if success > 0:
            self.add_tool_log(f"📎 已添加 {success} 个文件")

    def _on_new_session(self) -> None:
        """新建会话。"""
        self._chat_widget.clear()
        self._session_info.setText("新会话")
        self.message_sent.emit("/new_session")

    def _on_clear_chat(self) -> None:
        """清空对话。"""
        self._chat_widget.clear()

    def _on_settings(self) -> None:
        """打开设置。"""
        self.settings_requested.emit()

    def _on_about(self) -> None:
        """关于对话框。"""
        from src import __version__
        QMessageBox.about(
            self,
            "关于 WinClaw",
            f"<h2>WinClaw v{__version__}</h2>"
            "<p>Windows AI 桌面智能体</p>"
            "<p>基于 PySide6 + LiteLLM 构建</p>"
            "<hr>"
            "<p><b>功能特性:</b></p>"
            "<ul>"
            "<li>多模型支持 (OpenAI/DeepSeek/Ollama)</li>"
            "<li>工具调用 (Shell/文件/截图/浏览器等)</li>"
            "<li>MCP 协议支持</li>"
            "<li>对话历史持久化</li>"
            "</ul>"
            "<hr>"
            "<p><a href='https://github.com/your-org/winclaw'>GitHub</a></p>"
        )

    def _on_model_changed(self, model_name: str) -> None:
        """模型切换。"""
        self._status_model.setText(f"模型: {model_name}")
        self.model_changed.emit(model_name)

    def _set_thinking_state(self, thinking: bool) -> None:
        """设置思考状态。"""
        self._send_btn.setVisible(not thinking)
        self._stop_btn.setVisible(thinking)
        self._input_edit.setEnabled(not thinking)
        
        if thinking:
            self._tool_status.setText("思考中...")
        else:
            self._tool_status.setText("空闲")

    # ===== 公共 API =====

    def add_ai_message(self, text: str) -> None:
        """添加 AI 消息。"""
        self._chat_widget.add_ai_message(text)
        self._set_thinking_state(False)

    def append_ai_message(self, text: str) -> None:
        """追加 AI 消息（流式输出）。"""
        self._chat_widget.append_ai_message(text)

    def set_models(self, models: list[str]) -> None:
        """设置可用模型列表。"""
        current = self._model_combo.currentText()
        self._model_combo.clear()
        self._model_combo.addItems(models)
        
        # 恢复之前的选择
        if current in models:
            self._model_combo.setCurrentText(current)

    def set_current_model(self, model: str) -> None:
        """设置当前模型。"""
        index = self._model_combo.findText(model)
        if index >= 0:
            self._model_combo.setCurrentIndex(index)

    def update_usage(self, input_tokens: int, output_tokens: int, cost: float) -> None:
        """更新用量显示（侧面板 + 状态栏）。"""
        self._token_label.setText(f"输入: {input_tokens} | 输出: {output_tokens}")
        self._cost_label.setText(f"费用: ${cost:.4f}")
        # 状态栏简报
        total = input_tokens + output_tokens
        if total > 0:
            self._status_tokens.setText(f"Token: {total} | ${cost:.4f}")

    def set_connection_status(self, connected: bool) -> None:
        """设置连接状态。"""
        if connected:
            self._status_connection.setText("● 已连接")
            self._status_connection.setStyleSheet("color: #28a745;")
        else:
            self._status_connection.setText("● 未连接")
            self._status_connection.setStyleSheet("color: #888;")

    def set_tool_status(self, status: str) -> None:
        """设置工具状态。"""
        self._tool_status.setText(status)
        # 控制进度条可见性
        is_busy = status not in ("空闲", "完成")
        self._tool_progress.setVisible(is_busy)

    def add_tool_log(self, entry: str) -> None:
        """追加一条工具执行日志。"""
        self._tool_log_entries.append(entry)
        # 只保留最近 10 条
        if len(self._tool_log_entries) > 10:
            self._tool_log_entries = self._tool_log_entries[-10:]
        self._tool_log.setText("\n".join(self._tool_log_entries))
        # 自动滚动到底部
        v_bar = self._tool_log_scroll.verticalScrollBar()
        if v_bar:
            v_bar.setValue(v_bar.maximum())

    def clear_tool_log(self) -> None:
        """清空工具日志。"""
        self._tool_log_entries.clear()
        self._tool_log.setText("")
    
    def _on_voice_record(self) -> None:
        """处理录音按钮点击。"""
        if not self._is_recording:
            # 开始录音
            self._is_recording = True
            self._voice_btn.setText("🔴 录音中...")
            self._voice_btn.setStyleSheet("background-color: #ff4444; color: white;")
            self.voice_record_requested.emit()
        else:
            # 停止录音
            self._is_recording = False
            self._voice_btn.setText("🎤 录音")
            self._voice_btn.setStyleSheet("")
            self.voice_stop_requested.emit()
    
    def _on_tts_toggle(self, checked: bool) -> None:
        """处理 TTS 开关切换。"""
        self._tts_enabled = checked
        if checked:
            self._tts_btn.setText("🔊 TTS")
        else:
            self._tts_btn.setText("🔇 TTS")
        self.tts_toggle_requested.emit(checked)
    
    def reset_voice_button(self) -> None:
        """重置录音按钮状态（录音完成后调用）。"""
        self._is_recording = False
        self._voice_btn.setText("🎤 录音")
        self._voice_btn.setStyleSheet("")
    
    def set_input_text(self, text: str) -> None:
        """设置输入框文字。"""
        self._input_edit.setPlainText(text)
        self._input_edit.setFocus()  # 聚焦到输入框
    
    @property
    def attachment_manager(self) -> AttachmentManager:
        """获取附件管理器。"""
        return self._attachment_manager
    
    @property
    def workflow_panel(self) -> WorkflowPanel:
        """获取工作流面板。"""
        return self._workflow_panel

    def _on_generated_space(self) -> None:
        """打开生成空间。"""
        self.generated_space_requested.emit()

    def _on_history(self) -> None:
        """打开历史对话。"""
        self.history_requested.emit()

    def update_generated_space_count(self, count: int) -> None:
        """更新生成空间按钮上的文件数量显示。"""
        self._gen_space_count = count
        if count > 0:
            self._gen_space_btn.setText(f"📂 生成空间 ({count})")
            self._gen_space_btn.setStyleSheet(
                "font-weight: bold; color: #0078d4;"
            )
        else:
            self._gen_space_btn.setText("📂 生成空间")
            self._gen_space_btn.setStyleSheet("")
