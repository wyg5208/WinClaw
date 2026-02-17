"""WinClaw 主窗口。

布局：
- 顶部：标题栏（窗口控制 + 模型选择）
- 中部：聊天区域（消息气泡列表）
- 底部：输入区域（多行输入框 + 发送按钮 + 附件面板）
- 右侧：状态面板（工具执行状态、Token 用量）
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, List

from PySide6.QtGui import QAction, QCloseEvent, QGuiApplication, QIcon, QKeySequence, QShortcut
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

from src.i18n import tr
from src.core.command_handler import CommandHandler
from src.conversation import (
    ConversationManager,
    AskParser,
    AskWidget,
    TimeoutManager,
    TaskNotificationHandler,
    get_scheduler,
    TaskPriority,
    TTSPlayer,
    TTSEngine,
    VoiceRecognizer,
    WakeWordDetector,
    SimpleWakeWordDetector,
)

from .attachment_manager import AttachmentManager
from .attachment_panel import AttachmentPanel
from .workflow_panel import WorkflowPanel
from .commands_data import get_commands_data
from .commands_dialog import CommandsDialog

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
    knowledge_rag_requested = Signal()  # 打开知识库
    cron_job_requested = Signal()  # 打开定时任务管理
    stop_requested = Signal()  # 请求停止当前任务
    history_requested = Signal()  # 打开历史对话
    conversation_mode_changed = Signal(str)  # 对话模式切换 (off/continuous/wake_word)
    conversation_state_changed = Signal(str)  # 对话状态变化 (idle/listening/chatting/thinking/speaking)
    theme_changed = Signal(str)  # 主题切换 (light/dark/system)
    language_changed = Signal(str)  # 语言切换 (zh_CN/en_US)

    def __init__(
        self,
        bridge: AsyncBridge | None = None,
        tool_registry=None,
        model_registry=None,
        *,
        minimize_to_tray: bool = True
    ) -> None:
        super().__init__()
        self._bridge = bridge
        self._tool_registry = tool_registry
        self._model_registry = model_registry
        self._minimize_to_tray = minimize_to_tray
        self._force_quit = False
        self._tool_log_entries: list[str] = []
        self._is_recording = False  # 录音状态
        self._tts_enabled = False  # TTS 开启状态

        # 对话模式状态
        self._conversation_mode = "off"  # off/continuous/wake_word
        self._conversation_state = "idle"  # idle/listening/chatting/thinking/speaking

        # 对话模式管理器
        self._conversation_mgr: ConversationManager | None = None
        self._ask_parser: AskParser | None = None
        self._timeout_mgr: TimeoutManager | None = None

        # 附件管理器
        self._attachment_manager = AttachmentManager(self)

        # 初始化命令处理器
        self._init_command_handler()

        self._setup_window()
        self._setup_menu_bar()
        self._setup_tool_bar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._setup_shortcuts()
        self._setup_conversation()

    def _init_command_handler(self) -> None:
        """初始化命令处理器。"""
        self._cmd_handler = CommandHandler(
            tool_registry=self._tool_registry,
            model_registry=self._model_registry,
            attachment_manager=self._attachment_manager,
            agent=None,  # GUI模式下agent通过bridge访问，需后续设置
        )
        # 设置模型切换回调，用于同步更新下拉框
        self._cmd_handler.set_model_switched_callback(self._on_cmd_model_switched)

    def _on_cmd_model_switched(self, model_key: str, model_name: str) -> None:
        """处理命令切换模型后的UI同步。"""
        # 更新下拉框显示
        self.set_current_model(model_name)
        # 发出模型切换信号
        self.model_changed.emit(model_name)

    def _setup_conversation(self) -> None:
        """初始化对话模式相关组件。"""
        # 初始化对话管理器
        self._conversation_mgr = ConversationManager()
        self._conversation_mgr.set_callbacks(
            on_start_listening=self._on_conversation_start_listening,
            on_stop_listening=self._on_conversation_stop_listening,
            on_send_message=self._on_conversation_send_message,
            on_play_tts=self._on_conversation_play_tts,
        )

        # 连接信号
        self._conversation_mgr.mode_changed.connect(self._on_conversation_mgr_mode_changed)
        self._conversation_mgr.state_changed.connect(self._on_conversation_mgr_state_changed)
        self._conversation_mgr.wake_word_detected.connect(self._on_wake_word_detected)
        self._conversation_mgr.speech_recognized.connect(self._on_speech_recognized)
        self._conversation_mgr.speech_recognized_with_prompt.connect(self._on_speech_recognized_with_prompt)
        self._conversation_mgr.silence_warning.connect(self._on_silence_warning)
        self._conversation_mgr.silence_timeout.connect(self._on_silence_timeout)

        # 初始化TTS播放器
        self._tts_player: TTSPlayer | None = None
        try:
            self._tts_player = TTSPlayer()
            self._tts_player.playback_finished.connect(self._on_tts_playback_finished)
            logger.info("TTS播放器初始化成功")
        except Exception as e:
            logger.warning(f"TTS播放器初始化失败: {e}")

        # 初始化语音识别器
        self._voice_recognizer: VoiceRecognizer | None = None
        try:
            self._voice_recognizer = VoiceRecognizer()
            self._voice_recognizer.speech_result.connect(self._on_voice_speech_result)
            self._voice_recognizer.speech_error.connect(self._on_voice_speech_error)
            logger.info("语音识别器初始化成功")
        except Exception as e:
            logger.warning(f"语音识别器初始化失败: {e}")

        # 初始化唤醒词检测器
        self._wake_word_detector: SimpleWakeWordDetector | None = None
        self._wake_word_detector = SimpleWakeWordDetector(wake_words=["小铃铛"])
        self._wake_word_detector.wake_word_detected.connect(self._on_wake_word_detected_from_recognizer)

        # 初始化追问解析器
        self._ask_parser = AskParser()

        # 初始化超时管理器
        self._timeout_mgr = TimeoutManager()

        # 初始化追问UI组件
        self._ask_widget = AskWidget()
        self._ask_widget.option_selected.connect(self._on_ask_option_selected)

        # 初始化任务通知处理器
        self._task_notification = TaskNotificationHandler(self)

    def _on_conversation_start_listening(self) -> None:
        """对话模式开始监听回调。"""
        # 强制更新UI为录音状态
        self._is_recording = True
        self._voice_btn.setText("🔴 监听中...")
        self._voice_btn.setStyleSheet("background-color: #ff4444; color: white;")
        
        # 强制刷新UI
        self._voice_btn.repaint()
        self._voice_btn.update()

        # 启动语音识别器
        if self._voice_recognizer:
            self._voice_recognizer.start_listening()
            logger.info("语音识别器已启动")
        else:
            logger.warning("语音识别器未初始化")

        self.voice_record_requested.emit()

    def _on_conversation_stop_listening(self) -> None:
        """对话模式停止监听回调。"""
        # 停止语音识别器
        if self._voice_recognizer:
            self._voice_recognizer.stop_listening()
            logger.info("语音识别器已停止")

        # 更新UI为停止状态
        self._is_recording = False
        self._voice_btn.setText("🎤 录音")
        self._voice_btn.setStyleSheet("")
        
        # 强制刷新UI
        self._voice_btn.repaint()
        self._voice_btn.update()

        self.voice_stop_requested.emit()

    def _on_conversation_send_message(self, text: str) -> None:
        """对话模式发送消息回调。"""
        logger.info(f"对话模式发送消息: {text}")
        # 设置输入框内容
        self._input_edit.setPlainText(text)
        
        # 自动发送消息（模拟点击发送按钮）
        # 清空附件管理器
        self._attachment_manager.clear()
        
        # 触发发送信号
        self.message_sent.emit(text)
        
        # 显示思考状态
        self._set_thinking_state(True)

    def _on_conversation_play_tts(self, text: str) -> None:
        """对话模式播放TTS回调。"""
        # TODO: 实现TTS播放
        pass

    def _on_conversation_mgr_mode_changed(self, mode: str) -> None:
        """对话模式切换回调。"""
        logger.info(f"对话模式切换: {mode}")

    def _on_conversation_mgr_state_changed(self, state: str) -> None:
        """对话状态变化回调。"""
        self._conversation_state = state
        self.conversation_state_changed.emit(state)
        logger.info(f"对话状态变化: {state}")

    def _on_wake_word_detected(self) -> None:
        """检测到唤醒词回调。"""
        logger.info("检测到唤醒词")
        self.add_tool_log("检测到唤醒词，已激活对话模式")

    def _on_speech_recognized(self, text: str, is_voice_mode: bool = False) -> None:
        """语音识别完成回调。

        Args:
            text: 识别的文本
            is_voice_mode: 是否是语音对话模式
        """
        logger.info(f"语音识别完成: {text}, 语音模式: {is_voice_mode}")
        # 添加到聊天显示
        self._chat_widget.add_user_message(text)

        # 清空输入框
        self._input_edit.clear()

        # 获取附件列表（对话模式通常没有附件）
        attachments = self._attachment_manager.attachments

        # 发出信号（包含附件信息）
        if attachments:
            self.message_with_attachments.emit(text, attachments)
            self._attachment_manager.clear()
        else:
            self.message_sent.emit(text)

        # 显示思考状态
        self._set_thinking_state(True)

    def _on_speech_recognized_with_prompt(self, text: str, is_voice_mode: bool = False) -> None:
        """带提示词的语音识别完成回调（用于发送给AI）。

        Args:
            text: 带提示词的文本
            is_voice_mode: 是否是语音对话模式
        """
        if is_voice_mode:
            logger.info(f"发送带提示词的文本给AI: {text[:50]}...")
            # 发送带提示词的文本给AI
            self.message_sent.emit(text)

    def _on_silence_warning(self, remaining: int) -> None:
        """沉默警告回调。"""
        logger.info(f"沉默警告: {remaining}秒")
        self._conversation_status_label.setText(f"⚠️ {remaining}秒无输入将停止...")

    def _on_silence_timeout(self) -> None:
        """沉默超时回调。"""
        logger.info("沉默超时")
        if self._conversation_mode == "wake_word":
            self._conversation_status_label.setText("🔔 等待唤醒词...")
        else:
            self._conversation_status_label.setText("")

    def _on_tts_playback_finished(self) -> None:
        """TTS播放完成回调。"""
        logger.info("TTS播放完成")
        if self._conversation_mgr:
            self._conversation_mgr.on_tts_finished()

    def _on_voice_speech_result(self, text: str, is_final: bool) -> None:
        """语音识别结果回调。"""
        logger.info(f"语音识别结果: {text} (final={is_final})")

        # 检查唤醒词
        if self._conversation_mode == "wake_word" and self._wake_word_detector:
            if self._wake_word_detector.check(text):
                self.add_tool_log("检测到唤醒词，已激活对话模式")
                self._conversation_mgr.set_mode("continuous")

        # 发送到对话管理器
        if self._conversation_mgr:
            self._conversation_mgr.on_speech_result(text, is_final)

    def _on_voice_speech_error(self, error: str) -> None:
        """语音识别错误回调。"""
        logger.error(f"语音识别错误: {error}")
        self.add_tool_log(f"⚠️ 语音识别错误: {error}")

    def _on_wake_word_detected_from_recognizer(self) -> None:
        """从识别器检测到唤醒词回调。"""
        logger.info("唤醒词检测器检测到唤醒词")
        if self._conversation_mgr:
            self._conversation_mgr.on_speech_result("小铃铛", True)

    def _on_ask_option_selected(self, option: str) -> None:
        """追问选项选择回调。"""
        logger.info(f"用户选择选项: {option}")
        if option and option != "__done__":
            # 发送选择到AI
            self._chat_widget.add_user_message(f"[选择] {option}")
            self.message_sent.emit(option)
            self._set_thinking_state(True)
        self._timeout_mgr.cancel()

    def _on_conversation_play_tts(self, text: str) -> None:
        """对话模式播放TTS回调。"""
        if self._tts_player and self._tts_player.is_playing:
            self._tts_player.stop()

        if self._tts_player:
            # 解析文本，检查是否有追问
            cleaned_text, ask_intent = self._ask_parser.parse_without_markup(text) if self._ask_parser else (text, None)

            if ask_intent:
                # 有追问，显示选项UI
                self._ask_widget.show_choice(
                    ask_intent.question,
                    ask_intent.options,
                    ask_intent.recommended,
                    ask_intent.timeout_seconds,
                )
                # 启动超时管理器
                self._timeout_mgr.start(
                    ask_intent.timeout_strategy,
                    ask_intent.recommended,
                    ask_intent.timeout_seconds,
                )

            # 播放TTS
            if cleaned_text:
                self._tts_player.speak(cleaned_text)
                if self._conversation_mgr:
                    self._conversation_mgr.on_tts_start()

    def _setup_window(self) -> None:
        """设置窗口属性。"""
        self.setWindowTitle(f"WinClaw - {tr('AI 助手')}")
        self.setMinimumSize(900, 375)
        self.resize(1200, 600)
        self._setup_window_icon()
        self._center_on_screen()
    
    def _setup_window_icon(self) -> None:
        """设置窗口图标。"""
        # 尝试多种路径找到图标文件
        possible_paths = [
            Path(__file__).parent.parent.parent / "resources" / "icons" / "app_icon.ico",
            Path(__file__).parent.parent.parent / "resources" / "icons" / "app_icon_256.png",
            Path(__file__).parent.parent.parent / "resources" / "icons" / "logo1_bold_w.png",
            Path.cwd() / "resources" / "icons" / "app_icon.ico",
            Path.cwd() / "resources" / "icons" / "app_icon_256.png",
        ]
        
        for icon_path in possible_paths:
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
                logging.getLogger(__name__).debug(f"窗口图标已设置: {icon_path}")
                return
        
        logging.getLogger(__name__).warning("未找到窗口图标文件")

    def _center_on_screen(self) -> None:
        """将窗口居中显示在屏幕上。"""
        screen = self.screen()
        if screen:
            screen_geometry = screen.geometry()
            window_geometry = self.geometry()
            x = (screen_geometry.width() - window_geometry.width()) // 2
            y = (screen_geometry.height() - window_geometry.height()) // 2
            self.move(x, y)

    def reload_ui(self) -> None:
        """重新加载 UI（语言切换后调用）。"""
        # 重新设置窗口标题
        self.setWindowTitle(f"WinClaw - {tr('AI 助手')}")

        # 重建菜单栏
        menubar = self.menuBar()
        menubar.clear()
        self._setup_menu_bar()

        # 重建工具栏
        toolbar = self.findChild(QToolBar, "MainToolBar")
        if toolbar:
            toolbar.setWindowTitle(tr("主工具栏"))
            # 刷新工具栏按钮文本
            self._refresh_toolbar()

        # 刷新状态栏
        self._status_model.setText(tr("模型") + ": " + tr("未选择"))
        self._status_connection.setText("● " + tr("未连接"))

    def _refresh_toolbar(self) -> None:
        """刷新工具栏按钮文本。"""
        # 重新查找并更新工具栏中的按钮
        toolbar = self.findChild(QToolBar)
        if not toolbar:
            return

        # 遍历工具栏 actions
        for action in toolbar.actions():
            widget = toolbar.widgetForAction(action)
            if isinstance(widget, QPushButton):
                text = action.text()
                # 根据原文本映射到新的翻译
                if "新建会话" in text or "New Session" in text:
                    widget.setText(tr("新建会话"))
                elif "历史对话" in text or "History" in text:
                    widget.setText(tr("📋 历史对话"))
                elif text == "清空" or text == "Clear":
                    widget.setText(tr("清空"))
                elif "录音" in text or "Record" in text:
                    widget.setText(tr("🎤 录音"))
                elif "TTS" in text:
                    widget.setText(tr("🔇 TTS"))
                elif "生成空间" in text or "Generated" in text:
                    widget.setText(tr("📂 生成空间"))
                elif "知识库" in text or "Knowledge" in text:
                    widget.setText(tr("🧠 知识库"))

    def _setup_menu_bar(self) -> None:
        """设置菜单栏。"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu(tr("文件"))

        new_session_action = QAction(tr("新建会话"), self)
        new_session_action.setShortcut(QKeySequence.StandardKey.New)
        new_session_action.triggered.connect(self._on_new_session)
        file_menu.addAction(new_session_action)

        history_action = QAction(tr("历史对话") + "...", self)
        history_action.setShortcut(QKeySequence("Ctrl+H"))
        history_action.triggered.connect(self._on_history)
        file_menu.addAction(history_action)

        file_menu.addSeparator()

        exit_action = QAction(tr("退出"), self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 编辑菜单
        edit_menu = menubar.addMenu(tr("编辑"))

        clear_action = QAction(tr("清空对话"), self)
        clear_action.setShortcut("Ctrl+L")
        clear_action.triggered.connect(self._on_clear_chat)
        edit_menu.addAction(clear_action)

        # 显示菜单（主题 + 语言切换）
        view_menu = menubar.addMenu(tr("显示"))

        # 主题子菜单
        theme_menu = QMenu(tr("主题"), self)
        view_menu.addMenu(theme_menu)

        # 基础主题
        theme_light_action = QAction(tr("亮色"), self)
        theme_light_action.triggered.connect(lambda: self.theme_changed.emit("light"))
        theme_menu.addAction(theme_light_action)

        theme_dark_action = QAction(tr("暗色"), self)
        theme_dark_action.triggered.connect(lambda: self.theme_changed.emit("dark"))
        theme_menu.addAction(theme_dark_action)

        theme_system_action = QAction(tr("跟随系统"), self)
        theme_system_action.triggered.connect(lambda: self.theme_changed.emit("system"))
        theme_menu.addAction(theme_system_action)

        theme_menu.addSeparator()

        # 时尚渐变主题
        theme_ocean_action = QAction(tr("海洋蓝"), self)
        theme_ocean_action.triggered.connect(lambda: self.theme_changed.emit("ocean_blue"))
        theme_menu.addAction(theme_ocean_action)

        theme_forest_action = QAction(tr("森林绿"), self)
        theme_forest_action.triggered.connect(lambda: self.theme_changed.emit("forest_green"))
        theme_menu.addAction(theme_forest_action)

        theme_sunset_action = QAction(tr("日落橙"), self)
        theme_sunset_action.triggered.connect(lambda: self.theme_changed.emit("sunset_orange"))
        theme_menu.addAction(theme_sunset_action)

        theme_purple_action = QAction(tr("紫色梦幻"), self)
        theme_purple_action.triggered.connect(lambda: self.theme_changed.emit("purple_dream"))
        theme_menu.addAction(theme_purple_action)

        theme_pink_action = QAction(tr("玫瑰粉"), self)
        theme_pink_action.triggered.connect(lambda: self.theme_changed.emit("pink_rose"))
        theme_menu.addAction(theme_pink_action)

        theme_minimal_action = QAction(tr("极简白"), self)
        theme_minimal_action.triggered.connect(lambda: self.theme_changed.emit("minimal_white"))
        theme_menu.addAction(theme_minimal_action)

        theme_menu.addSeparator()

        # 深色系主题
        theme_deep_blue_action = QAction(tr("深蓝色"), self)
        theme_deep_blue_action.triggered.connect(lambda: self.theme_changed.emit("deep_blue"))
        theme_menu.addAction(theme_deep_blue_action)

        theme_deep_brown_action = QAction(tr("深棕色"), self)
        theme_deep_brown_action.triggered.connect(lambda: self.theme_changed.emit("deep_brown"))
        theme_menu.addAction(theme_deep_brown_action)

        # 语言子菜单
        language_menu = QMenu(tr("语言"), self)
        view_menu.addMenu(language_menu)

        lang_zh_action = QAction("简体中文", self)
        lang_zh_action.triggered.connect(lambda: self.language_changed.emit("zh_CN"))
        language_menu.addAction(lang_zh_action)

        lang_en_action = QAction("English", self)
        lang_en_action.triggered.connect(lambda: self.language_changed.emit("en_US"))
        language_menu.addAction(lang_en_action)

        # 工具菜单
        tools_menu = menubar.addMenu(tr("工具"))

        gen_space_action = QAction(tr("📂 生成空间") + "...", self)
        gen_space_action.setShortcut(QKeySequence("Ctrl+G"))
        gen_space_action.triggered.connect(self._on_generated_space)
        tools_menu.addAction(gen_space_action)

        # 知识库管理
        knowledge_action = QAction(tr("🧠 知识库") + "...", self)
        knowledge_action.setShortcut(QKeySequence("Ctrl+K"))
        knowledge_action.triggered.connect(self._on_knowledge_rag)
        tools_menu.addAction(knowledge_action)

        # 定时任务管理
        cron_action = QAction(tr("⏰ 定时任务") + "...", self)
        cron_action.setShortcut(QKeySequence("Ctrl+T"))
        cron_action.triggered.connect(self._on_cron_job)
        tools_menu.addAction(cron_action)

        tools_menu.addSeparator()

        settings_action = QAction(tr("设置") + "...", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._on_settings)
        tools_menu.addAction(settings_action)

        # 帮助菜单
        help_menu = menubar.addMenu(tr("帮助"))

        about_action = QAction(tr("关于") + "...", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _setup_tool_bar(self) -> None:
        """设置工具栏。"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # 模型选择下拉框
        model_label = QLabel(tr("模型") + ":")
        toolbar.addWidget(model_label)

        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(200)
        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        toolbar.addWidget(self._model_combo)

        toolbar.addSeparator()

        # 新建会话按钮
        new_btn = QPushButton(tr("新建会话"))
        new_btn.clicked.connect(self._on_new_session)
        toolbar.addWidget(new_btn)

        # 复制对话区按钮
        copy_chat_btn = QPushButton(tr("📋 复制对话"))
        copy_chat_btn.setToolTip(tr("复制所有对话内容"))
        copy_chat_btn.clicked.connect(self._on_copy_chat)
        toolbar.addWidget(copy_chat_btn)

        # 历史对话按钮
        history_btn = QPushButton(tr("📋 历史对话"))
        history_btn.setToolTip(tr("查看历史对话记录") + " (Ctrl+H)")
        history_btn.clicked.connect(self._on_history)
        toolbar.addWidget(history_btn)

        toolbar.addSeparator()

        # 清空按钮
        clear_btn = QPushButton(tr("清空"))
        clear_btn.clicked.connect(self._on_clear_chat)
        toolbar.addWidget(clear_btn)

        toolbar.addSeparator()

        # 语音输入按钮 (麦克风)
        self._voice_btn = QPushButton(tr("🎤 录音"))
        self._voice_btn.setToolTip(tr("按住录音,松开发送") + " (Ctrl+R)")
        self._voice_btn.setCheckable(False)
        self._voice_btn.clicked.connect(self._on_voice_record)
        toolbar.addWidget(self._voice_btn)

        # TTS 开关按钮
        self._tts_btn = QPushButton(tr("🔇 TTS"))
        self._tts_btn.setToolTip(tr("切换 AI 回复自动朗读"))
        self._tts_btn.setCheckable(True)
        self._tts_btn.setChecked(False)
        self._tts_btn.clicked.connect(self._on_tts_toggle)
        toolbar.addWidget(self._tts_btn)

        # 对话模式开关（下拉菜单）
        self._conversation_mode_combo = QComboBox()
        self._conversation_mode_combo.setMinimumWidth(140)
        self._conversation_mode_combo.addItems([
            tr("💬 对话模式"),
            tr("⚡ 持续对话"),
            tr("🔔 唤醒词模式"),
        ])
        self._conversation_mode_combo.setCurrentIndex(0)
        self._conversation_mode_combo.setToolTip(tr("选择对话模式，开启后实现语音交互"))
        self._conversation_mode_combo.currentIndexChanged.connect(self._on_conversation_mode_changed)
        toolbar.addWidget(self._conversation_mode_combo)

        # 对话状态标签
        self._conversation_status_label = QLabel("")
        self._conversation_status_label.setStyleSheet("color: #888; font-size: 11px;")
        self._conversation_status_label.setVisible(False)
        toolbar.addWidget(self._conversation_status_label)

        toolbar.addSeparator()

        # 生成空间按钮
        self._gen_space_btn = QPushButton(tr("📂 生成空间"))
        self._gen_space_btn.setToolTip(tr("查看 AI 生成的所有文件"))
        self._gen_space_btn.clicked.connect(self._on_generated_space)
        toolbar.addWidget(self._gen_space_btn)

        # 知识库按钮
        self._knowledge_btn = QPushButton(tr("🧠 知识库"))
        self._knowledge_btn.setToolTip(tr("管理知识库文档") + " (Ctrl+K)")
        self._knowledge_btn.clicked.connect(self._on_knowledge_rag)
        toolbar.addWidget(self._knowledge_btn)

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

        # 设置分割比例：左侧800，右侧200（右侧宽度减少一半）
        splitter.setSizes([800, 200])

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
        self._input_edit.setPlaceholderText("输入消息... (Enter发送，Shift+Enter换行)，/help 查看快捷工具指令清单，点击快捷命令、组合命令 获取100+示例")
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

        # 常用命令按钮
        self._quick_commands_btn = QPushButton("⚡ 快捷命令")
        self._quick_commands_btn.setToolTip("常用快捷命令")
        self._quick_commands_btn.clicked.connect(self._on_show_quick_commands)
        button_layout.addWidget(self._quick_commands_btn)

        self._combo_commands_btn = QPushButton("🔗 组合命令")
        self._combo_commands_btn.setToolTip("常用组合命令")
        self._combo_commands_btn.clicked.connect(self._on_show_combo_commands)
        button_layout.addWidget(self._combo_commands_btn)

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
        widget.setMinimumWidth(150)
        widget.setMaximumWidth(250)
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

        # 标题行：状态 + 复制按钮
        header_layout = QHBoxLayout()
        self._tool_status = QLabel("空闲")
        header_layout.addWidget(self._tool_status)
        header_layout.addStretch()
        copy_tools_btn = QPushButton("复制")
        copy_tools_btn.setToolTip("复制工具执行状态")
        copy_tools_btn.setFixedSize(45, 22)
        copy_tools_btn.setStyleSheet("font-size: 10px; border: none; padding: 2px;")
        copy_tools_btn.clicked.connect(self._copy_tool_status)
        header_layout.addWidget(copy_tools_btn)
        tools_layout.addLayout(header_layout)

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
        # 使用整数值兼容不同 PySide6 版本
        self._tool_log_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tool_log_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._tool_log_scroll.setMinimumHeight(60)
        self._tool_log_scroll.setMaximumHeight(180)
        self._tool_log_scroll.setWidget(self._tool_log)
        tools_layout.addWidget(self._tool_log_scroll)

        layout.addWidget(tools_group)

        # 工作流状态面板
        self._workflow_panel = WorkflowPanel()
        self._workflow_panel.copy_requested.connect(self._on_workflow_copy)
        layout.addWidget(self._workflow_panel)

        layout.addStretch()
        return widget

    def _setup_status_bar(self) -> None:
        """设置状态栏（P2-12 增强版）。"""
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        # 左侧：模型名
        self._status_model = QLabel(tr("模型") + ": " + tr("未选择"))
        self._status_bar.addWidget(self._status_model)

        # 中间：Token 简报
        self._status_tokens = QLabel("")
        self._status_tokens.setStyleSheet("margin-left: 16px;")
        self._status_bar.addWidget(self._status_tokens)

        # 定时任务概览（活跃任务数量和最近任务）
        self._status_cron_overview = QLabel("")
        self._status_cron_overview.setStyleSheet("margin-left: 16px; color: #666;")
        self._status_bar.addWidget(self._status_cron_overview)

        # 定时任务执行状态（执行中/完成/失败）
        self._status_cron = QLabel("")
        self._status_cron.setStyleSheet("margin-left: 16px; padding: 2px 8px; border-radius: 4px;")
        self._status_cron.setMinimumWidth(50)  # 确保有最小宽度
        self._status_bar.addWidget(self._status_cron)

        # 右侧：连接状态
        self._status_connection = QLabel("● " + tr("未连接"))
        self._status_connection.setStyleSheet("color: #888;")
        self._status_bar.addPermanentWidget(self._status_connection)
        
        # 启动定时任务概览刷新定时器（每60秒刷新一次）
        self._cron_overview_timer = QTimer(self)
        self._cron_overview_timer.timeout.connect(self._refresh_cron_overview)
        self._cron_overview_timer.start(60000)  # 60秒
        # 初始刷新
        QTimer.singleShot(1000, self._refresh_cron_overview)
    
    def _refresh_cron_overview(self) -> None:
        """刷新定时任务概览信息。"""
        try:
            # 从工具注册表获取 CronTool
            if self._tool_registry:
                cron_tool = self._tool_registry.get_tool("cron")
                if cron_tool and hasattr(cron_tool, 'storage'):
                    jobs = cron_tool.storage.get_all_jobs()
                    active_jobs = [j for j in jobs if j.status.value == "active"]
                    count = len(active_jobs)
                    
                    if count == 0:
                        self._status_cron_overview.setText("")
                        return
                    
                    # 获取最近即将执行的任务
                    from datetime import datetime
                    now = datetime.now()
                    upcoming = None
                    upcoming_name = ""
                    
                    for job in active_jobs:
                        # 尝试从 trigger_config 获取下次执行时间
                        next_run = None
                        if hasattr(job, 'trigger_config') and job.trigger_config:
                            trigger_type = job.trigger_config.get('type', '')
                            if trigger_type == 'once' and 'run_date' in job.trigger_config:
                                try:
                                    next_run = datetime.fromisoformat(job.trigger_config['run_date'])
                                except:
                                    pass
                        
                        if next_run and next_run > now:
                            if upcoming is None or next_run < upcoming:
                                upcoming = next_run
                                upcoming_name = job.description or job.job_id
                    
                    if upcoming:
                        time_str = upcoming.strftime("%H:%M")
                        self._status_cron_overview.setText(
                            f"📅 {count}个任务 | 下次: {time_str} {upcoming_name[:12]}"
                        )
                    else:
                        self._status_cron_overview.setText(f"📅 {count}个活跃任务")
        except Exception as e:
            logger.debug(f"刷新定时任务概览失败: {e}")
    
    def update_cron_status(self, status: str, job_description: str = "") -> None:
        """更新定时任务状态显示。
        
        Args:
            status: 状态类型 (idle/running/success/error)
            job_description: 任务描述
        """
        if status == "idle" or not job_description:
            self._status_cron.setText("")
            self._status_cron.setStyleSheet("margin-left: 16px; padding: 2px 8px; border-radius: 4px;")
        elif status == "running":
            self._status_cron.setText(f"⏰ {job_description[:25]}...")
            # 橙色背景更醒目
            self._status_cron.setStyleSheet(
                "margin-left: 16px; padding: 2px 8px; border-radius: 4px; "
                "color: white; background-color: #FF9800; font-weight: bold;"
            )
        elif status == "success":
            self._status_cron.setText(f"✓ {job_description[:25]}")
            self._status_cron.setStyleSheet(
                "margin-left: 16px; padding: 2px 8px; border-radius: 4px; "
                "color: white; background-color: #4CAF50;"
            )
        elif status == "error":
            self._status_cron.setText(f"✗ {job_description[:25]}")
            self._status_cron.setStyleSheet(
                "margin-left: 16px; padding: 2px 8px; border-radius: 4px; "
                "color: white; background-color: #F44336;"
            )

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

    def _copy_tool_status(self) -> None:
        """复制工具执行状态到剪贴板。"""
        # 构建要复制的文本
        status_text = f"状态: {self._tool_status.text()}\n"
        log_text = self._tool_log.text()
        if log_text:
            status_text += f"日志:\n{log_text}"
        else:
            status_text += "日志: (无)"

        clipboard = QGuiApplication.clipboard()
        clipboard.setText(status_text)

        # 反馈复制成功
        self.statusBar().showMessage("已复制工具执行状态到剪贴板", 3000)

    def _on_workflow_copy(self) -> None:
        """工作流复制成功时的回调。"""
        self.statusBar().showMessage("已复制工作流信息到剪贴板", 3000)

    def _on_send(self) -> None:
        """发送消息。"""
        text = self._input_edit.toPlainText().strip()
        if not text:
            return

        # 添加到聊天显示
        self._chat_widget.add_user_message(text)

        # 清空输入框
        self._input_edit.clear()

        # 检查是否为命令
        if text.startswith("/"):
            # 异步执行命令
            asyncio.create_task(self._execute_command(text))
            return

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

    async def _execute_command(self, text: str) -> None:
        """执行快捷命令。"""
        # 显示思考中状态
        self._set_thinking_state(True)

        try:
            result = await self._cmd_handler.execute(text)

            # 移除思考状态
            self._set_thinking_state(False)

            # 显示命令执行结果
            if result.is_quit:
                self.close()
            elif result.success:
                self._chat_widget.add_ai_message(result.output)
            else:
                self._chat_widget.add_ai_message(f"❌ {result.output}")
        except Exception as e:
            self._set_thinking_state(False)
            self._chat_widget.add_ai_message(f"❌ 命令执行错误: {e}")

    def _on_stop(self) -> None:
        """停止生成。"""
        self.stop_requested.emit()

    def _on_show_commands_menu(self) -> None:
        """显示常用命令菜单"""
        # 获取命令数据
        commands_data = get_commands_data()

        # 创建菜单
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #555;
            }
            QMenu::item:selected {
                background-color: #0078d4;
            }
            QMenu::separator {
                height: 1px;
                background-color: #555;
                margin: 5px 0px;
            }
        """)

        # 遍历分类和子分组
        for category_key, category_value in commands_data.items():
            # 创建分类菜单（快捷命令 / 组合命令）
            category_menu = QMenu(category_value["name"], menu)
            category_menu.setIcon(QIcon(""))

            for subgroup_key, subgroup_value in category_value["subgroups"].items():
                # 创建子分组菜单
                subgroup_menu = QMenu(subgroup_value["name"], category_menu)

                for cmd in subgroup_value["commands"]:
                    # 创建命令项
                    action = QAction(cmd, subgroup_menu)
                    action.triggered.connect(lambda checked, c=cmd: self._on_command_selected(c))
                    subgroup_menu.addAction(action)

                category_menu.addMenu(subgroup_menu)

            menu.addMenu(category_menu)

        # 显示菜单（位于按钮下方）
        menu.exec(self._commands_btn.mapToGlobal(self._commands_btn.rect().bottomLeft()))

    def _on_show_quick_commands(self) -> None:
        """显示快捷命令对话框"""
        dialog = CommandsDialog(self, "快捷命令", get_commands_data()["快捷命令"])
        dialog.command_selected.connect(self._on_command_selected)
        dialog.exec()

    def _on_show_combo_commands(self) -> None:
        """显示组合命令对话框"""
        dialog = CommandsDialog(self, "组合命令", get_commands_data()["组合命令"])
        dialog.command_selected.connect(self._on_command_selected)
        dialog.exec()

    def _on_command_selected(self, command: str) -> None:
        """当用户选择一个命令时"""
        # 将命令填入输入框
        self._input_edit.setPlainText(command)
        # 聚焦到输入框
        self._input_edit.setFocus()

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

    def _on_copy_chat(self) -> None:
        """复制所有对话内容到剪贴板。"""
        from PySide6.QtWidgets import QApplication
        conversation_text = self._chat_widget.copy_all_conversation()
        if conversation_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(conversation_text)

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
            "<p><a href='https://github.com/wyg5208/WinClaw'>GitHub</a></p>"
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

    def start_reasoning(self) -> None:
        """开始显示思考过程。"""
        self._chat_widget.start_reasoning()

    def append_reasoning(self, text: str) -> None:
        """追加思考内容。"""
        self._chat_widget.append_reasoning(text)

    def finish_reasoning(self) -> None:
        """完成思考过程。"""
        self._chat_widget.finish_reasoning()

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

    def _on_conversation_mode_changed(self, index: int) -> None:
        """处理对话模式切换。"""
        mode_map = {
            0: "off",
            1: "continuous",
            2: "wake_word",
        }
        mode = mode_map.get(index, "off")
        self._conversation_mode = mode

        # 调用ConversationManager设置模式
        if self._conversation_mgr:
            self._conversation_mgr.set_mode(mode)

        self._update_conversation_status()
        self.conversation_mode_changed.emit(mode)

    def _update_conversation_status(self) -> None:
        """更新对话模式状态显示。"""
        mode_texts = {
            "off": ("", False),
            "continuous": (tr("⚡ 持续对话中..."), True),
            "wake_word": (tr("🔔 等待唤醒词..."), True),
        }
        text, visible = mode_texts.get(self._conversation_mode, ("", False))
        self._conversation_status_label.setText(text)
        self._conversation_status_label.setVisible(visible)

        # 根据模式设置颜色
        color_map = {
            "off": "#888",
            "continuous": "#28a745",  # 绿色
            "wake_word": "#0078d4",  # 蓝色
        }
        color = color_map.get(self._conversation_mode, "#888")
        self._conversation_status_label.setStyleSheet(f"color: {color}; font-size: 11px;")

    def set_conversation_state(self, state: str) -> None:
        """设置对话状态（供外部调用）。"""
        self._conversation_state = state
        self.conversation_state_changed.emit(state)

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

    def _on_knowledge_rag(self) -> None:
        """打开知识库管理。"""
        self.knowledge_rag_requested.emit()

    def _on_cron_job(self) -> None:
        """打开定时任务管理。"""
        self.cron_job_requested.emit()

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
