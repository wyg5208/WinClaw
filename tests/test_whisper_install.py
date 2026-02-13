"""
Whisper 安装测试脚本
运行此脚本验证 Whisper 是否正确安装
"""
import sys

def test_whisper_installation():
    """测试 Whisper 安装"""
    print("=" * 60)
    print("Whisper 安装测试")
    print("=" * 60)
    
    # 1. 测试导入
    print("\n[1/4] 测试依赖导入...")
    try:
        import whisper
        import sounddevice as sd
        import numpy as np
        from scipy.io.wavfile import write as write_wav
        print("✅ 所有依赖导入成功")
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("\n请运行: pip install -e \".[voice]\"")
        return False
    
    # 2. 列出可用模型
    print("\n[2/4] 可用模型列表:")
    models = ["tiny", "base", "small", "medium", "large"]
    for model in models:
        print(f"  - {model}")
    
    # 3. 测试加载模型 (tiny - 最小)
    print("\n[3/4] 测试加载 tiny 模型 (首次会自动下载 ~39MB)...")
    try:
        model = whisper.load_model("tiny")
        print("✅ 模型加载成功")
    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        return False
    
    # 4. 列出音频设备
    print("\n[4/4] 可用音频输入设备:")
    try:
        devices = sd.query_devices()
        input_count = 0
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                input_count += 1
                mark = "🎤" if i == sd.default.device[0] else "  "
                print(f"  {mark} [{i}] {dev['name']} ({dev['max_input_channels']} 通道)")
        
        if input_count == 0:
            print("  ⚠️  未检测到音频输入设备")
        else:
            print(f"\n✅ 检测到 {input_count} 个音频输入设备")
    except Exception as e:
        print(f"❌ 设备查询失败: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ Whisper 安装测试通过！")
    print("=" * 60)
    return True


def test_tts_installation():
    """测试 TTS 安装"""
    print("\n" + "=" * 60)
    print("TTS (文字转语音) 安装测试")
    print("=" * 60)
    
    try:
        import pyttsx3
        print("\n✅ pyttsx3 导入成功")
        
        # 初始化引擎
        engine = pyttsx3.init()
        print("✅ TTS 引擎初始化成功")
        
        # 列出音色
        voices = engine.getProperty('voices')
        print(f"\n可用音色: {len(voices)} 个")
        for i, voice in enumerate(voices[:3]):  # 只显示前3个
            print(f"  [{i}] {voice.name}")
        
        print("\n✅ TTS 安装测试通过！")
        return True
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("\n请运行: pip install -e \".[voice]\"")
        return False
    except Exception as e:
        print(f"❌ TTS 测试失败: {e}")
        return False


if __name__ == "__main__":
    success = test_whisper_installation()
    if success:
        test_tts_installation()
    
    print("\n按任意键退出...")
    input()
