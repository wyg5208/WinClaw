"""TTS语音播放器。

支持多种TTS引擎：pyttsx3、edge-tts、gtts等。
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from enum import Enum
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QThread

logger = logging.getLogger(__name__)


class TTSEngine(Enum):
    """TTS引擎枚举。"""
    PYTTSX3 = "pyttsx3"     # 本地TTS，无需网络
    EDGE_TTS = "edge_tts"   # Edge在线TTS，音质好
    GTTS = "gtts"           # Google TTS，需联网


class TTSPlayer(QObject):
    """TTS语音播放器。

    支持多种TTS引擎，自动降级，提供播放控制。
    """

    # 信号
    playback_started = Signal()    # 开始播放
    playback_finished = Signal()   # 播放完成
    playback_error = Signal(str)   # 播放错误
    progress_changed = Signal(int) # 播放进度（0-100）

    def __init__(
        self,
        engine: TTSEngine = TTSEngine.PYTTSX3,
        voice_rate: int = 0,
        voice_volume: float = 1.0,
        voice_name: str = "",
    ):
        """初始化TTS播放器。

        Args:
            engine: TTS引擎类型
            voice_rate: 语速（-100到100，默认0）
            voice_volume: 音量（0.0到1.0，默认1.0）
            voice_name: 指定语音名称
        """
        super().__init__()
        self._engine = engine
        self._voice_rate = voice_rate
        self._voice_volume = voice_volume
        self._voice_name = voice_name
        self._is_playing = False
        self._is_paused = False
        self._current_text = ""
        self._temp_files: list[Path] = []
        self._current_thread: QThread | None = None  # 保存当前线程引用

        # 实际使用的引擎
        self._active_engine = None
        self._engine_init()

    def _engine_init(self) -> None:
        """初始化TTS引擎。"""
        # 优先尝试使用edge-tts（质量更好，无事件循环问题）
        if self._engine == TTSEngine.EDGE_TTS:
            self._init_edge_tts()
        elif self._engine == TTSEngine.GTTS:
            self._init_gtts()
        elif self._engine == TTSEngine.PYTTSX3:
            self._init_pyttsx3()
        else:
            # 默认优先使用edge-tts
            self._engine = TTSEngine.EDGE_TTS
            self._init_edge_tts()

    def _init_pyttsx3(self) -> None:
        """初始化pyttsx3引擎。"""
        try:
            import pyttsx3
            self._pyttsx3_engine = pyttsx3.init()
            # 设置语音参数
            if self._voice_rate != 0:
                self._pyttsx3_engine.setProperty('rate', 200 + self._voice_rate * 2)
            if self._voice_volume != 1.0:
                self._pyttsx3_engine.setProperty('volume', self._voice_volume)

            # 选择语音
            if self._voice_name:
                voices = self._pyttsx3_engine.getProperty('voices')
                for voice in voices:
                    if self._voice_name in voice.name:
                        self._pyttsx3_engine.setProperty('voice', voice.id)
                        break

            self._active_engine = TTSEngine.PYTTSX3
            logger.info("TTS引擎初始化成功: pyttsx3")
        except ImportError:
            logger.warning("pyttsx3未安装，尝试其他引擎")
            self._engine = TTSEngine.EDGE_TTS
            self._init_edge_tts()
        except Exception as e:
            logger.error(f"pyttsx3初始化失败: {e}")
            self._engine = TTSEngine.EDGE_TTS
            self._init_edge_tts()

    def _init_edge_tts(self) -> None:
        """初始化Edge TTS引擎。"""
        try:
            import edge_tts
            self._edge_tts = edge_tts
            self._active_engine = TTSEngine.EDGE_TTS
            logger.info("TTS引擎初始化成功: edge-tts")
        except ImportError:
            logger.warning("edge-tts未安装，尝试gtts")
            self._engine = TTSEngine.GTTS
            self._init_gtts()
        except Exception as e:
            logger.error(f"edge-tts初始化失败: {e}")
            self._engine = TTSEngine.GTTS
            self._init_gtts()

    def _init_gtts(self) -> None:
        """初始化Google TTS引擎。"""
        try:
            from gtts import gTTS
            self._gtts = gTTS
            self._active_engine = TTSEngine.GTTS
            logger.info("TTS引擎初始化成功: gTTS")
        except ImportError:
            logger.error("所有TTS引擎都不可用")
            self._active_engine = None

    # ========== 公共API ==========

    @property
    def is_playing(self) -> bool:
        """是否正在播放。"""
        return self._is_playing

    @property
    def is_paused(self) -> bool:
        """是否暂停。"""
        return self._is_paused

    @property
    def engine(self) -> TTSEngine:
        """当前使用的引擎。"""
        return self._active_engine or self._engine

    def speak(self, text: str) -> None:
        """播放文本语音。

        Args:
            text: 要播放的文本
        """
        if not text:
            return

        # 如果正在播放，先停止
        if self._is_playing:
            self.stop()

        # 预处理文本
        cleaned_text = self._preprocess_text(text)
        if not cleaned_text:
            return

        self._current_text = cleaned_text
        self._is_playing = True

        # 先停止之前的线程
        if self._current_thread and self._current_thread.isRunning():
            self._current_thread.quit()
            self._current_thread.wait(500)

        # 在新线程中执行
        thread = QThread()
        thread.run = lambda: self._speak_async(cleaned_text)
        self._current_thread = thread
        thread.start()

    def stop(self) -> None:
        """停止播放。"""
        self._is_playing = False
        self._is_paused = False

        # 等待并停止当前线程
        if self._current_thread and self._current_thread.isRunning():
            self._current_thread.quit()
            self._current_thread.wait(1000)
            self._current_thread = None

        if self._active_engine == TTSEngine.PYTTSX3 and hasattr(self, '_pyttsx3_engine'):
            try:
                self._pyttsx3_engine.stop()
            except:
                pass

        # 清理临时文件
        self._cleanup_temp_files()

        logger.info("TTS播放已停止")

    def pause(self) -> None:
        """暂停播放（仅pyttsx3支持）。"""
        if self._active_engine == TTSEngine.PYTTSX3:
            self._is_paused = True

    def resume(self) -> None:
        """恢复播放（仅pyttsx3支持）。"""
        if self._active_engine == TTSEngine.PYTTSX3:
            self._is_paused = False

    def set_voice(self, voice_name: str) -> None:
        """设置语音。

        Args:
            voice_name: 语音名称
        """
        self._voice_name = voice_name
        if self._active_engine == TTSEngine.PYTTSX3 and hasattr(self, '_pyttsx3_engine'):
            try:
                voices = self._pyttsx3_engine.getProperty('voices')
                for voice in voices:
                    if voice_name in voice.name:
                        self._pyttsx3_engine.setProperty('voice', voice.id)
                        break
            except Exception as e:
                logger.error(f"设置语音失败: {e}")

    def get_available_voices(self) -> list[str]:
        """获取可用的语音列表。"""
        if self._active_engine == TTSEngine.PYTTSX3 and hasattr(self, '_pyttsx3_engine'):
            try:
                voices = self._pyttsx3_engine.getProperty('voices')
                return [voice.name for voice in voices]
            except:
                return []
        return []

    # ========== 私有方法 ==========

    def _preprocess_text(self, text: str) -> str:
        """预处理文本，移除无法朗读的字符。"""
        # 移除特殊标记
        text = re.sub(r'<\|.*?\|>', '', text)
        text = re.sub(r'\[.*?\]', '', text)

        # 移除Emoji（保留基本标点）
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE
        )
        text = emoji_pattern.sub('', text)

        # 清理多余空白
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        return text

    def _speak_async(self, text: str) -> None:
        """异步播放（在线程中执行）。"""
        try:
            self.playback_started.emit()

            if self._active_engine == TTSEngine.PYTTSX3:
                self._speak_pyttsx3(text)
            elif self._active_engine == TTSEngine.EDGE_TTS:
                asyncio.run(self._speak_edge_tts(text))
            elif self._active_engine == TTSEngine.GTTS:
                self._speak_gtts(text)
            else:
                logger.error("没有可用的TTS引擎")
                self.playback_error.emit("没有可用的TTS引擎")
                return

            self.playback_finished.emit()

        except Exception as e:
            logger.error(f"TTS播放错误: {e}")
            self.playback_error.emit(str(e))
        finally:
            self._is_playing = False
            self._is_paused = False
            self._cleanup_temp_files()

    def _speak_pyttsx3(self, text: str) -> None:
        """使用pyttsx3播放。"""
        if not hasattr(self, '_pyttsx3_engine'):
            return

        # 方案1：使用独立线程执行
        import threading
        
        def run_speak():
            try:
                # 先停止之前的播放
                try:
                    self._pyttsx3_engine.stop()
                except:
                    pass
                
                self._pyttsx3_engine.say(text)
                self._pyttsx3_engine.runAndWait()
            except Exception as e:
                logger.error(f"pyttsx3播放错误: {e}")
                self.playback_error.emit(str(e))

        # 在新线程中执行
        thread = threading.Thread(target=run_speak, daemon=True)
        thread.start()
        thread.join()  # 等待播放完成

    async def _speak_edge_tts(self, text: str) -> None:
        """使用Edge TTS播放。"""
        # 生成语音到临时文件
        communicate = self._edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f:
            temp_file = Path(f.name)
            self._temp_files.append(temp_file)
            await communicate.save(temp_file)

        # 播放（使用playsound或其他方式）
        try:
            import winsound
            winsound.PlaySound(str(temp_file), winsound.SND_FILENAME)
        except Exception as e:
            logger.error(f"播放音频失败: {e}")

    def _speak_gtts(self, text: str) -> None:
        """使用gTTS播放。"""
        try:
            tts = self._gtts(text=text, lang='zh-cn')
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f:
                temp_file = Path(f.name)
                self._temp_files.append(temp_file)
                tts.save(str(temp_file))

            # 播放
            try:
                import winsound
                winsound.PlaySound(str(temp_file), winsound.SND_FILENAME)
            except Exception as e:
                logger.error(f"播放音频失败: {e}")
        except Exception as e:
            logger.error(f"gTTS生成失败: {e}")

    def _cleanup_temp_files(self) -> None:
        """清理临时文件。"""
        for temp_file in self._temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception as e:
                logger.warning(f"删除临时文件失败: {e}")
        self._temp_files.clear()
