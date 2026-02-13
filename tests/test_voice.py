"""测试语音输入功能"""
import asyncio
import sys

async def test_voice():
    print("=" * 50)
    print("语音输入功能测试")
    print("=" * 50)
    
    # 测试 1: 依赖检查
    print("\n[1] 检查依赖...")
    try:
        import whisper
        print(f"    ✓ whisper 版本: {whisper.__version__}")
    except ImportError as e:
        print(f"    ✗ whisper 导入失败: {e}")
        return
    
    try:
        import sounddevice as sd
        print(f"    ✓ sounddevice 可用")
    except ImportError as e:
        print(f"    ✗ sounddevice 导入失败: {e}")
        return
    
    try:
        import numpy as np
        print(f"    ✓ numpy 版本: {np.__version__}")
    except ImportError as e:
        print(f"    ✗ numpy 导入失败: {e}")
        return
    
    try:
        from scipy.io.wavfile import write as write_wav
        print(f"    ✓ scipy 可用")
    except ImportError as e:
        print(f"    ✗ scipy 导入失败: {e}")
        return
    
    # 测试 2: 工具导入
    print("\n[2] 导入语音工具...")
    try:
        from src.tools.voice_input import VoiceInputTool, VOICE_AVAILABLE
        print(f"    ✓ VoiceInputTool 导入成功")
        print(f"    ✓ VOICE_AVAILABLE: {VOICE_AVAILABLE}")
    except ImportError as e:
        print(f"    ✗ 工具导入失败: {e}")
        return
    
    # 测试 3: 创建工具实例
    print("\n[3] 创建工具实例...")
    try:
        tool = VoiceInputTool()
        print(f"    ✓ 工具创建成功: {tool.name}")
        print(f"    ✓ 可用动作: {[a.name for a in tool.get_actions()]}")
    except Exception as e:
        print(f"    ✗ 工具创建失败: {e}")
        return
    
    # 测试 4: 列出音频设备
    print("\n[4] 列出音频设备...")
    try:
        result = await tool.execute("list_devices", {})
        print(f"    状态: {result.status}")
        print(f"    输出: {result.output}")
        if result.data:
            devices = result.data.get("devices", [])
            default = result.data.get("default", "")
            print(f"    默认设备: {default}")
            for dev in devices[:5]:  # 只显示前 5 个
                print(f"      - [{dev['index']}] {dev['name']}")
    except Exception as e:
        print(f"    ✗ 执行失败: {e}")
        return
    
    # 测试 5: 简短录音测试（2秒）
    print("\n[5] 录音测试 (2秒)...")
    print("    请对着麦克风说话...")
    try:
        result = await tool.execute(
            "record_and_transcribe",
            {"duration": 2, "model": "base", "language": "zh"}
        )
        print(f"    状态: {result.status}")
        if result.status.value == "success":
            text = result.data.get("text", "")
            lang = result.data.get("language", "")
            print(f"    识别语言: {lang}")
            print(f"    识别结果: {text}")
        else:
            print(f"    错误: {result.error}")
    except Exception as e:
        print(f"    ✗ 录音失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_voice())
