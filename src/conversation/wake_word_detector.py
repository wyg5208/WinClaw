"""唤醒词检测器。

支持多种唤醒词检测方式：pvporcupine、edge-tts唤醒词检测、关键词匹配等。
"""

from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Optional

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class WakeWordEngine(Enum):
    """唤醒词引擎枚举。"""
    PV_PORCUPINE = "pv_porcupine"    # Picovoice Porcupine本地检测
    KEYWORD_MATCH = "keyword_match"  # 关键词简单匹配
    EDGE_TTS = "edge_tts"           # Edge TTS语音合成检测


class WakeWordDetector(QObject):
    """唤醒词检测器。

    支持多种检测方式，本地快速响应。
    """

    # 信号
    wake_word_detected = Signal()   # 检测到唤醒词
    listening_started = Signal()     # 开始监听
    listening_stopped = Signal()    # 停止监听
    error_occurred = Signal(str)    # 错误发生

    def __init__(
        self,
        wake_words: list[str] = None,
        engine: WakeWordEngine = WakeWordEngine.KEYWORD_MATCH,
        sensitivity: float = 0.5,
    ):
        """初始化唤醒词检测器。

        Args:
            wake_words: 唤醒词列表，默认["小铃铛"]
            engine: 检测引擎类型
            sensitivity: 灵敏度（0.0-1.0）
        """
        super().__init__()
        self._wake_words = wake_words or ["小铃铛"]
        self._engine = engine
        self._sensitivity = sensitivity
        self._is_listening = False

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._engine_init()

    def _engine_init(self) -> None:
        """初始化检测引擎。"""
        if self._engine == WakeWordEngine.KEYWORD_MATCH:
            self._active_engine = WakeWordEngine.KEYWORD_MATCH
            logger.info("唤醒词引擎初始化成功: 关键词匹配")
        elif self._engine == WakeWordEngine.PV_PORCUPINE:
            self._init_porcupine()
        else:
            # 默认使用关键词匹配
            self._engine = WakeWordEngine.KEYWORD_MATCH
            self._active_engine = WakeWordEngine.KEYWORD_MATCH

    def _init_porcupine(self) -> None:
        """初始化Porcupine引擎。"""
        try:
            import pvporcupine
            self._porcupine = pvporcupine

            # 创建检测器
            keywords = [w.replace(" ", "_").lower() for w in self._wake_words]
            self._porcupine_instance = pvporcupine.create(
                keywords=keywords,
                sensitivities=[self._sensitivity] * len(keywords)
            )
            self._active_engine = WakeWordEngine.PV_PORCUPINE
            logger.info("唤醒词引擎初始化成功: pvporcupine")
        except ImportError:
            logger.warning("pvporcupine未安装，使用关键词匹配")
            self._engine = WakeWordEngine.KEYWORD_MATCH
            self._active_engine = WakeWordEngine.KEYWORD_MATCH
        except Exception as e:
            logger.error(f"pvporcupine初始化失败: {e}")
            self._engine = WakeWordEngine.KEYWORD_MATCH
            self._active_engine = WakeWordEngine.KEYWORD_MATCH

    # ========== 公共API ==========

    @property
    def is_listening(self) -> bool:
        """是否正在监听。"""
        return self._is_listening

    @property
    def wake_words(self) -> list[str]:
        """获取唤醒词列表。"""
        return self._wake_words.copy()

    def set_wake_words(self, wake_words: list[str]) -> None:
        """设置唤醒词列表。

        Args:
            wake_words: 新的唤醒词列表
        """
        self._wake_words = wake_words
        # 如果使用Porcupine，需要重新初始化
        if self._active_engine == WakeWordEngine.PV_PORCUPINE:
            self._init_porcupine()

    def set_sensitivity(self, sensitivity: float) -> None:
        """设置灵敏度。

        Args:
            sensitivity: 灵敏度（0.0-1.0）
        """
        self._sensitivity = max(0.0, min(1.0, sensitivity))

    def start_listening(self) -> bool:
        """开始监听唤醒词。

        Returns:
            是否成功开始
        """
        if self._is_listening:
            return True

        self._is_listening = True
        self._stop_event.clear()

        # 在后台线程中运行
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

        self.listening_started.emit()
        logger.info(f"开始监听唤醒词: {self._wake_words}")
        return True

    def stop_listening(self) -> None:
        """停止监听。"""
        if not self._is_listening:
            return

        self._is_listening = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

        self.listening_stopped.emit()
        logger.info("停止监听唤醒词")

    def detect_from_text(self, text: str) -> bool:
        """从文本中检测唤醒词。

        Args:
            text: 待检测文本

        Returns:
            是否包含唤醒词
        """
        text_lower = text.lower()
        for wake_word in self._wake_words:
            if wake_word.lower() in text_lower:
                return True
        return False

    # ========== 私有方法 ==========

    def _listen_loop(self) -> None:
        """监听循环。"""
        # 使用关键词匹配时，需要结合语音识别器
        # 这里简化为直接检测麦克风输入的音频能量
        # 实际实现中，应该使用VoiceRecognizer获取音频

        try:
            import speech_recognition as sr

            recognizer = sr.Recognizer()
            microphone = sr.Microphone()

            with microphone as source:
                logger.info("唤醒词检测器就绪")
                recognizer.adjust_for_ambient_noise(source, duration=0.5)

            while not self._stop_event.is_set():
                try:
                    with microphone as source:
                        # 短时间监听
                        audio = recognizer.listen(
                            source,
                            timeout=1,
                            phrase_time_limit=3
                        )

                    if self._stop_event.is_set():
                        break

                    # 识别音频内容
                    try:
                        text = recognizer.recognize_google(
                            audio,
                            language="zh-CN"
                        )
                        logger.debug(f"检测到音频: {text}")

                        if self.detect_from_text(text):
                            logger.info("检测到唤醒词!")
                            self.wake_word_detected.emit()

                    except sr.UnknownValueError:
                        pass
                    except Exception as e:
                        logger.debug(f"识别错误: {e}")

                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"唤醒词检测错误: {e}")
                    continue

        except Exception as e:
            logger.error(f"唤醒词监听循环错误: {e}")
            self.error_occurred.emit(str(e))
        finally:
            self._is_listening = False


class SimpleWakeWordDetector(QObject):
    """简单的唤醒词检测器（基于关键词匹配）。

    适用于与VoiceRecognizer配合使用。
    """

    # 信号
    wake_word_detected = Signal()

    def __init__(self, wake_words: list[str] = None):
        """初始化。

        Args:
            wake_words: 唤醒词列表
        """
        super().__init__()
        self._wake_words = wake_words or ["小铃铛"]

    def check(self, text: str) -> bool:
        """检查文本是否包含唤醒词。

        Args:
            text: 待检查文本

        Returns:
            是否包含唤醒词
        """
        if not text:
            return False

        text_lower = text.lower().strip()
        for wake_word in self._wake_words:
            if wake_word.lower() in text_lower:
                self.wake_word_detected.emit()
                return True
        return False
