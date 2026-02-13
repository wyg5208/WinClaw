"""语音输入工具 - 基于 Whisper 的语音转文字

支持:
- 实时录音（直接传 numpy 数组给 Whisper，无需 ffmpeg）
- 音频文件转文字（WAV 可用 scipy 读取，其他格式需 ffmpeg）
- 多语言识别
- 可选模型大小 (tiny/base/small/medium/large)

Phase 4.6 优化：
- 延迟导入：whisper/sounddevice/numpy/scipy 仅在实际使用时导入
- 启动速度大幅提升
"""
import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 延迟导入标记
VOICE_AVAILABLE: bool | None = None
FFMPEG_AVAILABLE: bool | None = None

# 模块引用（延迟加载后赋值）
_whisper = None
_sd = None
_np = None
_read_wav = None
_write_wav = None


def _check_voice_dependencies() -> bool:
    """检查语音依赖是否可用，延迟导入。"""
    global VOICE_AVAILABLE, _whisper, _sd, _np, _read_wav, _write_wav
    if VOICE_AVAILABLE is not None:
        return VOICE_AVAILABLE

    try:
        import whisper
        import sounddevice as sd
        import numpy as np
        from scipy.io.wavfile import read as read_wav
        from scipy.io.wavfile import write as write_wav

        _whisper = whisper
        _sd = sd
        _np = np
        _read_wav = read_wav
        _write_wav = write_wav
        VOICE_AVAILABLE = True
        logger.debug("语音依赖加载成功")
    except ImportError:
        VOICE_AVAILABLE = False
        logger.debug("语音依赖不可用")

    return VOICE_AVAILABLE


def _check_ffmpeg() -> bool:
    """检测 ffmpeg 是否可用。"""
    global FFMPEG_AVAILABLE
    if FFMPEG_AVAILABLE is None:
        FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
    return FFMPEG_AVAILABLE


from .base import ActionDef, BaseTool, ToolResult, ToolResultStatus


class VoiceInputTool(BaseTool):
    """语音输入工具 - 使用 Whisper 将语音转为文字"""

    name = "voice_input"
    emoji = "🎤"
    title = "语音输入"
    description = "语音转文字工具,支持实时录音或从音频文件识别"

    def __init__(self):
        super().__init__()
        self._model: Optional[Any] = None
        self._model_name: str = "base"
        self._sample_rate: int = 16000
        # 不在初始化时检查依赖，延迟到实际使用时

    def _check_available(self) -> bool:
        """检查语音功能是否可用。"""
        if not _check_voice_dependencies():
            raise ImportError(
                "语音功能不可用。请安装依赖: pip install openai-whisper sounddevice scipy"
            )
        return True

    def _load_model(self, model_name: str = "base") -> Any:
        """延迟加载 Whisper 模型"""
        self._check_available()
        if self._model is None or self._model_name != model_name:
            self._model_name = model_name
            self._model = _whisper.load_model(model_name)
        return self._model

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="record_and_transcribe",
                description="录制音频并转为文字",
                parameters={
                    "duration": {
                        "type": "number",
                        "description": "录音时长(秒),默认 5 秒",
                        "default": 5,
                    },
                    "model": {
                        "type": "string",
                        "description": "Whisper 模型 (tiny/base/small/medium/large),默认 base",
                        "default": "base",
                        "enum": ["tiny", "base", "small", "medium", "large"],
                    },
                    "language": {
                        "type": "string",
                        "description": "语言代码(如 zh/en),留空自动检测",
                        "default": None,
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="transcribe_file",
                description="将音频文件转为文字",
                parameters={
                    "file_path": {
                        "type": "string",
                        "description": "音频文件路径(支持 wav/mp3/m4a 等)",
                    },
                    "model": {
                        "type": "string",
                        "description": "Whisper 模型",
                        "default": "base",
                        "enum": ["tiny", "base", "small", "medium", "large"],
                    },
                    "language": {
                        "type": "string",
                        "description": "语言代码,留空自动检测",
                        "default": None,
                    },
                },
                required_params=["file_path"],
            ),
            ActionDef(
                name="list_devices",
                description="列出可用的音频输入设备",
                parameters={},
                required_params=[],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        """执行语音输入操作"""
        if action == "record_and_transcribe":
            return await self._record_and_transcribe(**params)
        elif action == "transcribe_file":
            return await self._transcribe_file(**params)
        elif action == "list_devices":
            return self._list_devices()
        else:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"未知动作: {action}",
                output=f"可用动作: {[a.name for a in self.get_actions()]}",
            )

    async def _record_and_transcribe(
        self, duration: float = 5.0, model: str = "base", language: Optional[str] = None
    ) -> ToolResult:
        """录制音频并转文字（直接传 numpy 数组，无需 ffmpeg）"""
        try:
            # 检查依赖
            self._check_available()

            # 录音
            duration = max(1, min(duration, 60))  # 限制 1-60 秒
            frames = int(duration * self._sample_rate)

            logger.info("开始录音: %.1f 秒, 采样率 %d", duration, self._sample_rate)

            # 在线程池中执行阻塞的录音操作
            loop = asyncio.get_event_loop()
            audio_data = await loop.run_in_executor(
                None, lambda: _sd.rec(frames, samplerate=self._sample_rate, channels=1, dtype="float32")
            )
            await loop.run_in_executor(None, _sd.wait)

            # 转为一维 float32 numpy 数组 (Whisper 要求的格式)
            audio_data = audio_data.flatten().astype(_np.float32)

            logger.info("录音完成, 数据长度: %d, 范围: [%.4f, %.4f]",
                        len(audio_data), audio_data.min(), audio_data.max())

            # 加载模型
            model_obj = await loop.run_in_executor(None, self._load_model, model)

            # 直接将 numpy 数组传给 Whisper（无需 ffmpeg）
            transcribe_kwargs = {"fp16": False}
            if language:
                transcribe_kwargs["language"] = language

            result = await loop.run_in_executor(
                None, lambda: model_obj.transcribe(audio_data, **transcribe_kwargs)
            )

            text = result["text"].strip()
            detected_language = result.get("language", "unknown")

            logger.info("转录完成: 语言=%s, 文字=%s", detected_language, text[:50])

            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"录音转录成功 (时长: {duration}s, 语言: {detected_language})",
                data={
                    "text": text,
                    "language": detected_language,
                    "duration": duration,
                    "model": model,
                },
            )

        except Exception as e:
            logger.exception("录音转录失败")
            return ToolResult(status=ToolResultStatus.ERROR, error=f"录音转录失败: {e}")

    def _load_audio_file(self, file_path: str):
        """加载音频文件为 Whisper 要求的 float32 numpy 数组。

        优先使用 ffmpeg（支持所有格式），若不可用则用 scipy 读取 WAV。
        """
        self._check_available()

        if _check_ffmpeg():
            # ffmpeg 可用时，使用 whisper 内置加载（支持所有格式）
            return _whisper.load_audio(file_path)

        # ffmpeg 不可用，用 scipy 读取 WAV 文件
        ext = Path(file_path).suffix.lower()
        if ext not in (".wav", ".wave"):
            raise RuntimeError(
                f"不支持 {ext} 格式（需要 ffmpeg）。"
                f"请安装 ffmpeg 或将文件转为 WAV 格式。\n"
                f"安装方法: winget install Gyan.FFmpeg"
            )

        sample_rate, data = _read_wav(file_path)

        # 转为 float32
        if data.dtype == _np.int16:
            audio = data.astype(_np.float32) / 32768.0
        elif data.dtype == _np.int32:
            audio = data.astype(_np.float32) / 2147483648.0
        elif data.dtype == _np.float32:
            audio = data
        else:
            audio = data.astype(_np.float32)

        # 多声道转单声道
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        # 重采样到 16kHz (Whisper 要求)
        if sample_rate != 16000:
            # 简单线性重采样
            duration = len(audio) / sample_rate
            target_len = int(duration * 16000)
            indices = _np.linspace(0, len(audio) - 1, target_len)
            audio = _np.interp(indices, _np.arange(len(audio)), audio).astype(_np.float32)

        return audio

    async def _transcribe_file(
        self, file_path: str, model: str = "base", language: Optional[str] = None
    ) -> ToolResult:
        """将音频文件转为文字"""
        try:
            path = Path(file_path).expanduser().resolve()
            if not path.exists():
                return ToolResult(status=ToolResultStatus.ERROR, error=f"文件不存在: {file_path}")

            # 检查文件大小 (限制 50MB)
            file_size_mb = path.stat().st_size / (1024 * 1024)
            if file_size_mb > 50:
                return ToolResult(
                    status=ToolResultStatus.ERROR, error=f"文件过大: {file_size_mb:.1f}MB (限制 50MB)"
                )

            # 加载模型
            loop = asyncio.get_event_loop()
            model_obj = await loop.run_in_executor(None, self._load_model, model)

            # 加载音频文件为 numpy 数组
            audio_data = await loop.run_in_executor(None, self._load_audio_file, str(path))

            # 转录（传入 numpy 数组，无需 ffmpeg）
            transcribe_kwargs = {"fp16": False}
            if language:
                transcribe_kwargs["language"] = language

            result = await loop.run_in_executor(
                None, lambda: model_obj.transcribe(audio_data, **transcribe_kwargs)
            )

            text = result["text"].strip()
            detected_language = result.get("language", "unknown")

            ffmpeg_note = "" if _check_ffmpeg() else " (无 ffmpeg, 仅支持 WAV)"
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"文件转录成功: {path.name}{ffmpeg_note}",
                data={
                    "text": text,
                    "language": detected_language,
                    "file_path": str(path),
                    "file_size_mb": file_size_mb,
                    "model": model,
                },
            )

        except Exception as e:
            logger.exception("文件转录失败")
            return ToolResult(status=ToolResultStatus.ERROR, error=f"文件转录失败: {e}")

    def _list_devices(self) -> ToolResult:
        """列出可用的音频输入设备"""
        try:
            self._check_available()

            devices = _sd.query_devices()
            input_devices = []

            for i, dev in enumerate(devices):
                if dev["max_input_channels"] > 0:
                    input_devices.append(
                        {
                            "index": i,
                            "name": dev["name"],
                            "channels": dev["max_input_channels"],
                            "sample_rate": dev["default_samplerate"],
                        }
                    )

            default_device = _sd.query_devices(kind="input")

            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"找到 {len(input_devices)} 个音频输入设备",
                data={"devices": input_devices, "default": default_device["name"]},
            )

        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"查询设备失败: {e}")
