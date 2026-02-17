"""语音识别器。

支持多种语音识别引擎：SpeechRecognition、Whisper等。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from enum import Enum
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer

logger = logging.getLogger(__name__)

# 简繁转换工具
try:
    from src.tools.text_utils import to_simplified_chinese
except ImportError:
    # 如果导入失败，定义一个空实现
    def to_simplified_chinese(text: str) -> str:
        return text


class RecognizerEngine(Enum):
    """语音识别引擎枚举。"""
    SPEECH_RECOGNITION = "speech_recognition"  # 使用Google Web Speech API
    WHISPER = "whisper"                        # OpenAI Whisper本地识别


class VoiceRecognizer(QObject):
    """语音识别器。

    支持持续监听、语音转文本、实时识别。
    """

    # 信号
    speech_started = Signal()        # 开始识别
    speech_result = Signal(str, bool)  # 识别结果 (text, is_final)
    speech_error = Signal(str)       # 识别错误
    audio_level = Signal(float)      # 音频级别（0.0-1.0）

    def __init__(
        self,
        engine: RecognizerEngine = RecognizerEngine.SPEECH_RECOGNITION,
        language: str = "zh-CN",
        continuous: bool = True,
        interim_results: bool = True,
    ):
        """初始化语音识别器。

        Args:
            engine: 识别引擎类型
            language: 识别语言
            continuous: 是否持续识别
            interim_results: 是否返回临时结果
        """
        super().__init__()
        self._engine = engine
        self._language = language
        # Whisper使用"zh"，而不是"zh-CN"等格式
        self._language_for_whisper = self._convert_language_for_whisper(language)
        self._continuous = continuous
        self._interim_results = interim_results
        self._is_listening = False
        self._is_paused = False

        self._recognizer = None
        self._microphone = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._engine_init()

    @staticmethod
    def _convert_language_for_whisper(language: str) -> str:
        """将语言代码转换为Whisper格式。

        Whisper支持的语言代码格式与Google Speech不同：
        - "zh-CN" / "zh-cn" -> "zh"
        - "en-US" -> "en"
        - 其他保持不变
        """
        # 处理常见的语言代码转换
        lang_map = {
            "zh-CN": "zh",
            "zh-cn": "zh",
            "zh-TW": "zh",
            "zh-tw": "zh",
            "en-US": "en",
            "en-us": "en",
            "en-GB": "en",
            "en-gb": "en",
        }
        return lang_map.get(language, language)

    def _engine_init(self) -> None:
        """初始化识别引擎。"""
        # 优先尝试使用whisper
        try:
            import whisper
            self._whisper_model = whisper.load_model("base", device="cpu")
            self._whisper_available = True
            self._active_engine = RecognizerEngine.WHISPER
            logger.info("语音识别引擎初始化成功: Whisper (CPU)")
            return
        except ImportError:
            logger.warning("whisper未安装")
        except Exception as e:
            logger.warning(f"whisper加载失败: {e}")

        # 尝试使用speech_recognition
        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            # 设置更宽松的静音检测阈值，允许更长的安静时长
            self._recognizer.energy_threshold = 200  # 降低灵敏度，允许更安静的环境
            self._recognizer.dynamic_energy_threshold = True  # 动态调整
            self._microphone = sr.Microphone()

            # 校准环境噪音（缩短时间，加快启动）
            with self._microphone as source:
                logger.info("正在校准麦克风...")
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                logger.info("麦克风校准完成")

            self._active_engine = RecognizerEngine.SPEECH_RECOGNITION
            logger.info("语音识别引擎初始化成功: SpeechRecognition")

        except ImportError:
            logger.error("speech_recognition库和whisper都未安装，请运行: pip install speech_recognition")
            self._active_engine = None
        except Exception as e:
            logger.error(f"语音识别初始化失败: {e}")
            self._active_engine = None

    # ========== 公共API ==========

    @property
    def is_listening(self) -> bool:
        """是否正在监听。"""
        return self._is_listening

    @property
    def is_paused(self) -> bool:
        """是否暂停。"""
        return self._is_paused

    def start_listening(self) -> bool:
        """开始持续监听。

        Returns:
            是否成功开始
        """
        if self._is_listening:
            return True

        if not self._active_engine:
            logger.error("没有可用的语音识别引擎")
            return False

        # 对于speech_recognition引擎，检查必要组件
        if self._active_engine == RecognizerEngine.SPEECH_RECOGNITION:
            if not self._recognizer or not self._microphone:
                logger.error("SpeechRecognition组件未初始化")
                return False

        logger.info(f"开始语音监听，当前引擎: {self._active_engine}")

        self._is_listening = True
        self._is_paused = False
        self._stop_event.clear()

        # 在后台线程中运行
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

        self.speech_started.emit()
        logger.info("开始语音监听")
        return True

    def stop_listening(self) -> None:
        """停止监听。"""
        if not self._is_listening:
            return

        self._is_listening = False
        self._is_paused = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

        logger.info("停止语音监听")

    def pause_listening(self) -> None:
        """暂停监听。"""
        self._is_paused = True

    def resume_listening(self) -> None:
        """恢复监听。"""
        self._is_paused = False

    def recognize_once(self) -> Optional[str]:
        """识别一次语音。

        Returns:
            识别结果文本，失败返回None
        """
        if not self._active_engine or not self._microphone:
            return None

        try:
            import speech_recognition as sr

            with self._microphone as source:
                logger.info("正在识别...")
                audio = self._recognizer.listen(source, timeout=5)

            # 使用Google Web Speech API识别
            text = self._recognizer.recognize_google(audio, language=self._language)
            logger.info(f"识别结果: {text}")
            return text

        except sr.UnknownValueError:
            logger.debug("未能识别音频内容")
        except sr.RequestError as e:
            logger.error(f"识别服务请求失败: {e}")
            self.speech_error.emit(f"识别服务请求失败: {e}")
        except Exception as e:
            logger.error(f"识别错误: {e}")
            self.speech_error.emit(str(e))

        return None

    # ========== 私有方法 ==========

    def _listen_loop(self) -> None:
        """监听循环（在后台线程中运行）。"""
        import speech_recognition as sr

        # 根据不同引擎检查必要组件
        if self._active_engine == RecognizerEngine.SPEECH_RECOGNITION:
            if not self._recognizer or not self._microphone:
                logger.error("SpeechRecognition组件未正确初始化")
                return
        elif self._active_engine == RecognizerEngine.WHISPER:
            if not self._whisper_model:
                logger.error("Whisper模型未正确初始化")
                return
        else:
            logger.error("没有可用的语音识别引擎")
            return

        try:
            while not self._stop_event.is_set():
                if self._is_paused:
                    self._stop_event.wait(0.1)
                    continue

                try:
                    if self._active_engine == RecognizerEngine.SPEECH_RECOGNITION:
                        # 使用SpeechRecognition监听
                        with self._microphone as source:
                            # 监听音频
                            # timeout=1: 等待声音开始的超时（1秒无声音则跳过）
                            # phrase_time_limit=20: 单次语音最大时长（根据实际语音长度自适应）
                            audio = self._recognizer.listen(
                                source,
                                timeout=1,
                                phrase_time_limit=20
                            )

                        if self._stop_event.is_set():
                            break

                        # 非阻塞识别
                        self._recognize_async(audio)
                        
                    elif self._active_engine == RecognizerEngine.WHISPER:
                        # 使用Whisper进行实时监听（内存方式，避免文件锁定）
                        import pyaudio
                        import numpy as np
                        
                        # 音频参数
                        FORMAT = pyaudio.paInt16
                        CHANNELS = 1
                        RATE = 16000
                        CHUNK = 1024
                        
                        # 初始化PyAudio
                        audio = pyaudio.PyAudio()
                        
                        # 打开音频流
                        stream = audio.open(
                            format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            input=True,
                            frames_per_buffer=CHUNK
                        )
                        
                        logger.info("开始Whisper实时监听...")
                        
                        # 使用numpy数组存储音频数据
                        audio_buffer = np.array([], dtype=np.int16)
                        silence_frames = 0
                        max_silence_frames = 20  # 20帧静音判定为结束
                        
                        try:
                            while not self._stop_event.is_set():
                                # 读取音频数据
                                data = stream.read(CHUNK, exception_on_overflow=False)
                                
                                # 转换为numpy数组并追加到缓冲区
                                audio_chunk = np.frombuffer(data, dtype=np.int16)
                                audio_buffer = np.concatenate([audio_buffer, audio_chunk])
                                
                                # 简单的能量检测判断是否有人声
                                energy = np.mean(np.abs(audio_chunk))
                                
                                if energy < 100:  # 静音阈值
                                    silence_frames += 1
                                else:
                                    silence_frames = 0
                                
                                # 如果连续静音超过阈值，认为说话结束
                                if silence_frames > max_silence_frames and len(audio_buffer) > RATE:
                                    # 将音频归一化到[-1, 1]范围（whisper需要）
                                    audio_float32 = audio_buffer.astype(np.float32) / 32768.0
                                    
                                    # 直接使用whisper识别（不写入文件）
                                    try:
                                        result = self._whisper_model.transcribe(
                                            audio_float32,
                                            language=self._language_for_whisper,
                                            fp16=False
                                        )
                                        
                                        text = result["text"].strip()
                                        if text:
                                            # 转换为简体中文
                                            text = to_simplified_chinese(text)
                                            logger.info(f"Whisper识别结果: {text}")
                                            self.speech_result.emit(text, True)
                                                
                                    except Exception as e:
                                        logger.error(f"Whisper识别错误: {e}")
                                    
                                    # 重置
                                    audio_buffer = np.array([], dtype=np.int16)
                                    silence_frames = 0
                                    
                                # 短暂等待
                                self._stop_event.wait(0.05)
                                
                        finally:
                            # 清理资源
                            stream.stop_stream()
                            stream.close()
                            audio.terminate()
                        
                except sr.WaitTimeoutError:
                    # 超时，继续循环
                    continue
                except Exception as e:
                    logger.error(f"监听错误: {e}")
                    continue

        except Exception as e:
            logger.error(f"监听循环错误: {e}")
            self.speech_error.emit(str(e))
        finally:
            self._is_listening = False

    def _recognize_async(self, audio) -> None:
        """异步识别音频。"""
        import speech_recognition as sr

        try:
            # 尝试使用Google识别
            text = self._recognizer.recognize_google(
                audio,
                language=self._language,
                show_all=False
            )

            if text:
                # 转换为简体中文
                text = to_simplified_chinese(text)
                logger.info(f"识别结果: {text}")
                self.speech_result.emit(text, True)

        except sr.UnknownValueError:
            # 未能识别
            pass
        except sr.RequestError as e:
            logger.error(f"识别请求失败: {e}")
            self.speech_error.emit(f"识别请求失败: {e}")
        except Exception as e:
            logger.error(f"识别错误: {e}")
            self.speech_error.emit(str(e))


class WhisperRecognizer(VoiceRecognizer):
    """Whisper语音识别器（可选实现）。"""

    def __init__(
        self,
        model_name: str = "base",
        language: str = "zh",
        device: str = "cpu",
    ):
        """初始化Whisper识别器。

        Args:
            model_name: 模型名称 (tiny, base, small, medium, large)
            language: 识别语言
            device: 运行设备 (cpu, cuda)
        """
        super().__init__(engine=RecognizerEngine.WHISPER)
        self._model_name = model_name
        self._device = device
        self._whisper_model = None
        self._whisper_init()

    def _whisper_init(self) -> None:
        """初始化Whisper模型。"""
        try:
            import whisper
            logger.info(f"正在加载Whisper模型: {self._model_name}")
            self._whisper_model = whisper.load_model(
                self._model_name,
                device=self._device
            )
            logger.info("Whisper模型加载完成")
        except ImportError:
            logger.error("whisper库未安装")
        except Exception as e:
            logger.error(f"Whisper模型加载失败: {e}")

    def recognize_audio_file(self, audio_path: str) -> Optional[str]:
        """识别音频文件。

        Args:
            audio_path: 音频文件路径

        Returns:
            识别结果
        """
        if not self._whisper_model:
            return None

        try:
            import whisper
            result = self._whisper_model.transcribe(
                audio_path,
                language=self._language_for_whisper,
                fp16=False
            )
            text = result["text"].strip()
            # 转换为简体中文
            text = to_simplified_chinese(text)
            return text
        except Exception as e:
            logger.error(f"Whisper识别失败: {e}")
            return None
