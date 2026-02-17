"""对话模式管理器。

管理对话模式的各个状态，处理语音识别、超时、追问等逻辑。
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal, QTimer

logger = logging.getLogger(__name__)


class ConversationMode(Enum):
    """对话模式枚举。"""
    OFF = "off"
    CONTINUOUS = "continuous"  # 持续对话模式，无需唤醒词
    WAKE_WORD = "wake_word"    # 唤醒词模式


class ConversationState(Enum):
    """对话状态枚举。"""
    IDLE = "idle"        # 空闲
    LISTENING = "listening"  # 监听中
    CHATTING = "chatting"    # 对话中
    THINKING = "thinking"    # AI思考中
    SPEAKING = "speaking"    # TTS播放中


class ConversationManager(QObject):
    """对话模式管理器。

    管理对话模式的各个状态转换，处理语音识别、超时等逻辑。
    """

    # 信号
    mode_changed = Signal(str)           # 模式变化 (off/continuous/wake_word)
    state_changed = Signal(str)          # 状态变化 (idle/listening/chatting/thinking/speaking)
    wake_word_detected = Signal()        # 检测到唤醒词
    silence_warning = Signal(int)         # 沉默警告（剩余秒数）
    silence_timeout = Signal()            # 沉默超时
    speech_recognized = Signal(str, bool) # 语音识别完成 (text, is_voice_mode)
    speech_recognized_with_prompt = Signal(str, bool) # 带提示词的语音识别（发送给AI）
    tts_started = Signal()                # TTS开始播放
    tts_finished = Signal()               # TTS播放完成

    # 对话模式简洁回复前缀
    VOICE_MODE_PREFIX = "[语音对话模式]请用口语化表达，回复简洁明了（50字以内），不要生成文档、图片或其他文件，专注于对话交流。"

    # 配置默认值
    DEFAULT_TIMEOUT = 30          # 默认超时秒数
    DEFAULT_SILENCE_WARNING = 10  # 默认沉默警告秒数
    DEFAULT_AUTO_SEND_DELAY = 0.8  # 默认自动发送延迟（秒）- 语音模式下快速响应
    DEFAULT_WAKE_WORD = "小铃铛"   # 默认唤醒词

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        silence_warning_time: int = DEFAULT_SILENCE_WARNING,
        auto_send_delay: float = DEFAULT_AUTO_SEND_DELAY,
        wake_word: str = DEFAULT_WAKE_WORD,
    ):
        """初始化对话管理器。

        Args:
            timeout: 对话超时秒数，默认30秒
            silence_warning_time: 沉默警告秒数，默认10秒
            auto_send_delay: 语音识别完成后自动发送延迟（秒），默认1.5秒
            wake_word: 唤醒词，默认"小铃铛"
        """
        super().__init__()
        self._mode = ConversationMode.OFF
        self._state = ConversationState.IDLE

        # 配置
        self._timeout = timeout
        self._silence_warning_time = silence_warning_time
        self._auto_send_delay = int(auto_send_delay * 1000)  # 转换为毫秒
        self._wake_word = wake_word

        # 定时器
        self._silence_timer: QTimer | None = None  # 沉默超时计时器
        self._warning_timer: QTimer | None = None  # 沉默警告计时器
        self._auto_send_timer: QTimer | None = None # 自动发送计时器
        self._has_warned = False  # 是否已经发送过警告

        # 回调函数（由外部设置）
        self._on_start_listening: Optional[Callable] = None
        self._on_stop_listening: Optional[Callable] = None
        self._on_send_message: Optional[Callable[[str], None]] = None
        self._on_play_tts: Optional[Callable[[str], None]] = None

        # 识别中的文本
        self._current_text = ""

    # ========== 属性 ==========

    @property
    def mode(self) -> ConversationMode:
        """获取当前模式。"""
        return self._mode

    @property
    def state(self) -> ConversationState:
        """获取当前状态。"""
        return self._state

    @property
    def is_active(self) -> bool:
        """是否处于对话模式（未关闭）。"""
        return self._mode != ConversationMode.OFF

    # ========== 公共方法 ==========

    def set_mode(self, mode: str) -> None:
        """设置对话模式。

        Args:
            mode: 模式字符串 ("off", "continuous", "wake_word")
        """
        try:
            new_mode = ConversationMode(mode)
        except ValueError:
            logger.warning(f"未知的对话模式: {mode}")
            return

        if new_mode == self._mode:
            return

        old_mode = self._mode
        self._mode = new_mode
        logger.info(f"对话模式切换: {old_mode.value} -> {new_mode.value}")

        # 停止当前活动
        self._stop_all_timers()
        self._stop_listening()

        # 根据新模式启动
        if new_mode == ConversationMode.OFF:
            self._set_state(ConversationState.IDLE)
        elif new_mode == ConversationMode.CONTINUOUS:
            self._set_state(ConversationState.LISTENING)
            self._start_listening()
        elif new_mode == ConversationMode.WAKE_WORD:
            self._set_state(ConversationState.LISTENING)
            self._start_listening()

        self.mode_changed.emit(new_mode.value)

    def set_callbacks(
        self,
        on_start_listening: Optional[Callable] = None,
        on_stop_listening: Optional[Callable] = None,
        on_send_message: Optional[Callable[[str], None]] = None,
        on_play_tts: Optional[Callable[[str], None]] = None,
    ) -> None:
        """设置回调函数。

        Args:
            on_start_listening: 开始监听回调
            on_stop_listening: 停止监听回调
            on_send_message: 发送消息回调
            on_play_tts: 播放TTS回调
        """
        self._on_start_listening = on_start_listening
        self._on_stop_listening = on_stop_listening
        self._on_send_message = on_send_message
        self._on_play_tts = on_play_tts

    def on_speech_result(self, text: str, is_final: bool = True) -> None:
        """处理语音识别结果。

        Args:
            text: 识别的文本
            is_final: 是否为最终结果
        """
        if not text:
            return

        logger.info(f"语音识别结果: {text} (final={is_final})")

        if is_final:
            # 重置沉默计时器
            self._reset_silence_timer()

            # 检查唤醒词（仅在唤醒词模式下）
            if self._mode == ConversationMode.WAKE_WORD:
                if self._wake_word in text:
                    logger.info("检测到唤醒词!")
                    self.wake_word_detected.emit()
                    self._set_state(ConversationState.CHATTING)

            # 检查结束意图
            if self._is_ending_intent(text):
                self._handle_ending()
                return

            # 如果是对话模式（OFF除外），就发送消息
            if self._mode != ConversationMode.OFF:
                # 确保状态正确
                if self._state == ConversationState.LISTENING:
                    self._set_state(ConversationState.CHATTING)

                # 立即或延迟发送（等待用户说完）
                self._current_text = text
                self._start_auto_send_timer()
        else:
            # 临时结果，更新UI显示
            self._current_text = text

    def on_tts_start(self) -> None:
        """TTS开始播放回调。"""
        self._stop_silence_timer()
        self._set_state(ConversationState.SPEAKING)
        self.tts_started.emit()
        # 停止监听，避免录入TTS声音
        self._stop_listening()

    def on_tts_finished(self) -> None:
        """TTS播放完成回调。"""
        self._set_state(ConversationState.CHATTING)
        self.tts_finished.emit()
        # 重新启动监听
        if self._mode != ConversationMode.OFF:
            self._start_listening()
            self._reset_silence_timer()

    def cancel_current_input(self) -> None:
        """取消当前输入。"""
        self._stop_auto_send_timer()
        self._current_text = ""

    # ========== 私有方法 ==========

    def _set_state(self, state: ConversationState) -> None:
        """设置状态。"""
        if state == self._state:
            return
        old_state = self._state
        self._state = state
        logger.info(f"对话状态切换: {old_state.value} -> {state.value}")
        self.state_changed.emit(state.value)

    def _start_listening(self) -> None:
        """开始监听。"""
        if self._on_start_listening:
            self._on_start_listening()

    def _stop_listening(self) -> None:
        """停止监听。"""
        if self._on_stop_listening:
            self._on_stop_listening()

    def _send_message(self, text: str) -> None:
        """发送消息。"""
        if self._on_send_message:
            self._on_send_message(text)

    def _play_tts(self, text: str) -> None:
        """播放TTS。"""
        if self._on_play_tts:
            self._on_play_tts(text)

    def _start_auto_send_timer(self) -> None:
        """启动自动发送计时器。"""
        self._stop_auto_send_timer()
        self._auto_send_timer = QTimer()
        self._auto_send_timer.setSingleShot(True)
        self._auto_send_timer.timeout.connect(self._on_auto_send_timeout)
        self._auto_send_timer.start(self._auto_send_delay)

    def _stop_auto_send_timer(self) -> None:
        """停止自动发送计时器。"""
        if self._auto_send_timer:
            self._auto_send_timer.stop()
            self._auto_send_timer = None

    def _on_auto_send_timeout(self) -> None:
        """自动发送超时处理。"""
        if self._current_text:
            original_text = self._current_text
            self._current_text = ""
            self._set_state(ConversationState.THINKING)

            # 检查是否是对话模式
            is_voice_mode = self._mode != ConversationMode.OFF

            # 如果是语音对话模式，添加简洁回复前缀（用于发送给AI）
            if is_voice_mode:
                # 原始文本用于显示给用户
                self.speech_recognized.emit(original_text, is_voice_mode)
                # 带提示词的文本用于发送给AI
                ai_text = f"{self.VOICE_MODE_PREFIX} {original_text}"
                self.speech_recognized_with_prompt.emit(ai_text, is_voice_mode)
            else:
                self.speech_recognized.emit(original_text, is_voice_mode)

    def _reset_silence_timer(self) -> None:
        """重置沉默计时器。"""
        self._stop_all_timers()
        self._has_warned = False

        if self._mode == ConversationMode.OFF:
            return

        # 启动沉默超时计时器
        self._silence_timer = QTimer()
        self._silence_timer.setSingleShot(True)
        self._silence_timer.timeout.connect(self._on_silence_timeout)
        self._silence_timer.start(self._timeout * 1000)

        # 启动沉默警告计时器
        warning_time = self._timeout - self._silence_warning_time
        if warning_time > 0:
            self._warning_timer = QTimer()
            self._warning_timer.setSingleShot(True)
            self._warning_timer.timeout.connect(self._on_warning_timeout)
            self._warning_timer.start(warning_time * 1000)

    def _stop_silence_timer(self) -> None:
        """停止沉默计时器。"""
        if self._silence_timer:
            self._silence_timer.stop()
            self._silence_timer = None
        if self._warning_timer:
            self._warning_timer.stop()
            self._warning_timer = None

    def _stop_all_timers(self) -> None:
        """停止所有计时器。"""
        self._stop_silence_timer()
        self._stop_auto_send_timer()

    def _on_warning_timeout(self) -> None:
        """沉默警告超时处理。"""
        if not self._has_warned:
            self._has_warned = True
            remaining = self._silence_warning_time
            self.silence_warning.emit(remaining)

    def _on_silence_timeout(self) -> None:
        """沉默超时处理。"""
        logger.info("对话沉默超时")
        self.silence_timeout.emit()

        if self._mode == ConversationMode.WAKE_WORD:
            # 唤醒词模式下回到监听状态
            self._set_state(ConversationState.LISTENING)
            self._start_listening()
            self._reset_silence_timer()
        else:
            # 持续对话模式下停止监听
            self._stop_listening()

    def _is_ending_intent(self, text: str) -> bool:
        """检查是否是结束对话意图。"""
        ending_keywords = [
            "再见", "不聊了", "不想聊了", "闭嘴", "晚安",
            "拜拜", "好了", "可以了", "结束", "停止",
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in ending_keywords)

    def _handle_ending(self) -> None:
        """处理结束对话。"""
        if self._mode == ConversationMode.WAKE_WORD:
            # 回到唤醒监听状态
            self._set_state(ConversationState.LISTENING)
            self._start_listening()
            self._reset_silence_timer()
        else:
            # 关闭对话模式
            self.set_mode("off")
