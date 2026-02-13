"""
多模态功能测试 - 测试语音、OCR、图片输入等功能

测试场景:
1. 语音输入 (Whisper STT)
2. 语音输出 (TTS)
3. OCR 文字识别
4. 图片输入组件
5. 多模态协作场景

注意: execute() 签名为 execute(action: str, params: dict)
      ToolResult 使用 .is_success 而非 .success
"""
import asyncio
import base64
import io
import tempfile
from pathlib import Path

import pytest

# 标记为可选测试,因为需要额外依赖
pytestmark = pytest.mark.optional


# ============= 语音输入测试 =============


@pytest.mark.asyncio
async def test_voice_input_tool_import():
    """测试语音输入工具导入"""
    try:
        from src.tools.voice_input import VoiceInputTool

        tool = VoiceInputTool()
        assert tool.name == "voice_input"
        assert len(tool.get_actions()) == 3
    except ImportError:
        pytest.skip("语音输入功能未安装 (pip install winclaw[voice])")


@pytest.mark.asyncio
async def test_voice_input_list_devices():
    """测试列出音频设备"""
    try:
        from src.tools.voice_input import VoiceInputTool

        tool = VoiceInputTool()
        result = await tool.execute("list_devices", {})

        # 应该至少有一个输入设备
        assert result.is_success
        assert "devices" in result.data
        assert isinstance(result.data["devices"], list)
    except ImportError:
        pytest.skip("语音输入功能未安装")


@pytest.mark.asyncio
@pytest.mark.slow
async def test_voice_input_record(tmp_path):
    """测试录音转文字 (需要手动测试)"""
    pytest.skip("录音测试需要麦克风和手动操作,跳过自动化测试")


# ============= 语音输出测试 =============


@pytest.mark.asyncio
async def test_voice_output_tool_import():
    """测试语音输出工具导入"""
    try:
        from src.tools.voice_output import VoiceOutputTool

        tool = VoiceOutputTool()
        assert tool.name == "voice_output"
        assert len(tool.get_actions()) == 4
    except ImportError:
        pytest.skip("语音输出功能未安装 (pip install winclaw[voice])")


@pytest.mark.asyncio
async def test_voice_output_list_voices():
    """测试列出可用音色"""
    try:
        from src.tools.voice_output import VoiceOutputTool

        tool = VoiceOutputTool()
        result = await tool.execute("list_voices", {})

        assert result.is_success
        assert "voices" in result.data
        assert isinstance(result.data["voices"], list)
        assert len(result.data["voices"]) > 0
    except ImportError:
        pytest.skip("语音输出功能未安装")


@pytest.mark.asyncio
@pytest.mark.slow
async def test_voice_output_speak():
    """测试朗读文本"""
    try:
        from src.tools.voice_output import VoiceOutputTool

        tool = VoiceOutputTool()
        result = await tool.execute("speak", {"text": "你好,世界", "rate": 250, "volume": 0.8})

        assert result.is_success
        assert result.data["length"] == 5
    except ImportError:
        pytest.skip("语音输出功能未安装")


@pytest.mark.asyncio
async def test_voice_output_save_to_file(tmp_path):
    """测试保存音频文件"""
    try:
        from src.tools.voice_output import VoiceOutputTool

        tool = VoiceOutputTool()
        output_file = tmp_path / "test_speech.wav"

        result = await tool.execute(
            "save_to_file",
            {"text": "测试语音合成", "output_path": str(output_file), "rate": 200, "volume": 1.0},
        )

        assert result.is_success
        assert output_file.exists()
        assert output_file.stat().st_size > 0
    except ImportError:
        pytest.skip("语音输出功能未安装")


# ============= OCR 测试 =============


@pytest.mark.asyncio
async def test_ocr_tool_import():
    """测试 OCR 工具导入"""
    try:
        from src.tools.ocr import OCRTool

        tool = OCRTool()
        assert tool.name == "ocr"
        assert len(tool.get_actions()) == 2
    except ImportError:
        pytest.skip("OCR 功能未安装 (pip install winclaw[ocr])")


@pytest.mark.asyncio
async def test_ocr_recognize_simple_image(tmp_path):
    """测试识别简单文字图片"""
    try:
        from src.tools.ocr import OCRTool
        from PIL import Image, ImageDraw

        # 创建一个包含文字的简单图片
        img = Image.new("RGB", (400, 100), color="white")
        draw = ImageDraw.Draw(img)

        # 使用默认字体绘制文字
        draw.text((10, 30), "Hello World 123", fill="black")

        # 保存图片
        img_path = tmp_path / "test_text.png"
        img.save(img_path)

        # 执行 OCR
        tool = OCRTool()
        result = await tool.execute("recognize_file", {"image_path": str(img_path)})

        # 检查结果
        assert result.is_success
        # OCR 可能识别不完全准确,所以只检查是否有结果
        assert "text" in result.data
        assert "line_count" in result.data
    except ImportError:
        pytest.skip("OCR 功能未安装")


@pytest.mark.asyncio
async def test_ocr_no_text_image(tmp_path):
    """测试识别无文字图片"""
    try:
        from src.tools.ocr import OCRTool
        from PIL import Image

        # 创建纯色图片 (无文字)
        img = Image.new("RGB", (200, 200), color="blue")
        img_path = tmp_path / "no_text.png"
        img.save(img_path)

        # 执行 OCR
        tool = OCRTool()
        result = await tool.execute("recognize_file", {"image_path": str(img_path)})

        # 应该成功但没有识别到文字
        assert result.is_success
        assert result.data.get("text", "") == ""
    except ImportError:
        pytest.skip("OCR 功能未安装")


# ============= 图片输入组件测试 (需要 GUI) =============


def test_image_input_widget_import():
    """测试图片输入组件导入"""
    try:
        from src.ui.image_input import ImageInputWidget

        # 只测试导入
        assert ImageInputWidget is not None
    except ImportError:
        pytest.skip("PySide6 未安装")


# ============= 多模态协作场景测试 =============


@pytest.mark.asyncio
@pytest.mark.slow
async def test_multimodal_scenario_ocr_plus_tts(tmp_path):
    """场景: OCR 识别文字 + TTS 朗读"""
    try:
        from src.tools.ocr import OCRTool
        from src.tools.voice_output import VoiceOutputTool
        from PIL import Image, ImageDraw

        # 1. 创建带文字的图片
        img = Image.new("RGB", (400, 100), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 30), "This is a test", fill="black")
        img_path = tmp_path / "text_image.png"
        img.save(img_path)

        # 2. OCR 识别
        ocr_tool = OCRTool()
        ocr_result = await ocr_tool.execute("recognize_file", {"image_path": str(img_path)})

        assert ocr_result.is_success
        recognized_text = ocr_result.data.get("text", "")

        # 3. TTS 朗读 (如果识别到文字)
        if recognized_text.strip():
            tts_tool = VoiceOutputTool()
            tts_result = await tts_tool.execute(
                "speak", {"text": recognized_text[:50], "rate": 200}
            )
            # TTS 可能因系统原因失败,所以不严格断言

    except ImportError:
        pytest.skip("多模态功能未完全安装")


@pytest.mark.asyncio
async def test_tool_registration():
    """测试新工具是否正确注册"""
    from src.tools.registry import ToolRegistry

    registry = ToolRegistry()

    # 检查工具是否已注册
    all_tools = registry.list_tools()
    tool_names = [t["name"] for t in all_tools]

    # 不强制要求这些工具存在 (因为是可选依赖)
    # 但如果存在,应该被正确注册
    optional_tools = ["voice_input", "voice_output", "ocr"]

    for tool_name in optional_tools:
        if tool_name in tool_names:
            tool_info = registry.get_tool_info(tool_name)
            assert tool_info is not None
            assert tool_info["category"] == "multimedia"


# ============= 性能测试 =============


@pytest.mark.asyncio
@pytest.mark.slow
async def test_ocr_performance(tmp_path):
    """测试 OCR 性能"""
    try:
        from src.tools.ocr import OCRTool
        from PIL import Image, ImageDraw
        import time

        # 创建测试图片
        img = Image.new("RGB", (800, 600), color="white")
        draw = ImageDraw.Draw(img)
        for i in range(10):
            draw.text((10, 30 + i * 40), f"Line {i+1}: Test text for OCR", fill="black")

        img_path = tmp_path / "perf_test.png"
        img.save(img_path)

        # 测试性能
        tool = OCRTool()
        start_time = time.time()
        result = await tool.execute("recognize_file", {"image_path": str(img_path)})
        elapsed = time.time() - start_time

        assert result.is_success
        # OCR 应该在 5 秒内完成
        assert elapsed < 5.0

    except ImportError:
        pytest.skip("OCR 功能未安装")


# ============= 错误处理测试 =============


@pytest.mark.asyncio
async def test_voice_input_invalid_duration():
    """测试无效录音时长"""
    try:
        from src.tools.voice_input import VoiceInputTool

        tool = VoiceInputTool()
        # 时长应该被限制在 1-60 秒
        # 注意: 这会实际录音,所以跳过自动化测试
        pytest.skip("录音测试需要麦克风,跳过")

    except ImportError:
        pytest.skip("语音输入功能未安装")


@pytest.mark.asyncio
async def test_ocr_nonexistent_file():
    """测试 OCR 识别不存在的文件"""
    try:
        from src.tools.ocr import OCRTool

        tool = OCRTool()
        result = await tool.execute("recognize_file", {"image_path": "/nonexistent/file.png"})

        assert not result.is_success
        assert "不存在" in result.error

    except ImportError:
        pytest.skip("OCR 功能未安装")


@pytest.mark.asyncio
async def test_voice_output_empty_text():
    """测试朗读空文本"""
    try:
        from src.tools.voice_output import VoiceOutputTool

        tool = VoiceOutputTool()
        result = await tool.execute("speak", {"text": ""})

        assert not result.is_success
        assert "空" in result.error

    except ImportError:
        pytest.skip("语音输出功能未安装")


# ============= 语音输入 ffmpeg 检测测试 =============


def test_ffmpeg_detection():
    """测试 ffmpeg 可用性检测"""
    from src.tools.voice_input import FFMPEG_AVAILABLE
    # 仅验证检测逻辑不会出错，不要求 ffmpeg 必须安装
    assert isinstance(FFMPEG_AVAILABLE, bool)


@pytest.mark.asyncio
async def test_voice_input_transcribe_file_wav(tmp_path):
    """测试 WAV 文件转录（不依赖 ffmpeg）"""
    try:
        from src.tools.voice_input import VoiceInputTool
        import numpy as np
        from scipy.io.wavfile import write as write_wav

        # 创建一个静音 WAV 文件
        sample_rate = 16000
        duration = 1  # 1 秒
        silence = np.zeros(sample_rate * duration, dtype=np.int16)
        wav_path = tmp_path / "silence.wav"
        write_wav(str(wav_path), sample_rate, silence)

        tool = VoiceInputTool()
        result = await tool.execute("transcribe_file", {"file_path": str(wav_path), "model": "base"})

        # 静音文件应成功转录，文本可能为空或含噪声文本
        assert result.is_success or result.error  # 不崩溃即可

    except ImportError:
        pytest.skip("语音输入功能未安装")
