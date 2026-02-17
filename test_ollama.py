"""测试Ollama本地模型调用"""
import asyncio
import sys
import time

sys.path.insert(0, '.')

async def test_ollama_streaming():
    """测试Ollama流式调用"""
    from src.models.registry import ModelRegistry
    
    print("=" * 60)
    print("测试Ollama本地模型调用")
    print("=" * 60)
    
    # 初始化模型注册表
    registry = ModelRegistry()
    
    # 列出所有Ollama模型
    ollama_models = [m for m in registry.list_models() if m.provider == "ollama"]
    print(f"\n发现 {len(ollama_models)} 个Ollama模型:")
    for m in ollama_models:
        print(f"  - {m.name} (id={m.id}, key={m.key})")
    
    if not ollama_models:
        print("错误: 没有找到Ollama模型!")
        return
    
    # 选择第一个模型测试
    model = ollama_models[0]
    print(f"\n选择测试模型: {model.name}")
    print(f"  model_id: {model.id}")
    print(f"  base_url: {model.base_url}")
    
    # 测试非流式调用
    print("\n" + "-" * 60)
    print("测试1: 非流式调用")
    print("-" * 60)
    try:
        start_time = time.time()
        response = await registry.chat(
            model_key=model.key,
            messages=[{"role": "user", "content": "你好，请用一句话介绍自己"}],
        )
        elapsed = time.time() - start_time
        content = response.choices[0].message.content
        print(f"✓ 成功! 耗时: {elapsed:.2f}秒")
        print(f"响应: {content[:100]}...")
    except Exception as e:
        print(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试流式调用
    print("\n" + "-" * 60)
    print("测试2: 流式调用")
    print("-" * 60)
    try:
        start_time = time.time()
        stream = registry.chat_stream(
            model_key=model.key,
            messages=[{"role": "user", "content": "你好，请用一句话介绍自己"}],
        )
        
        print("开始接收流式响应...")
        chunk_count = 0
        full_content = ""
        
        async for chunk in stream:
            chunk_count += 1
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                full_content += delta.content
                print(f"\r收到chunk {chunk_count}: {full_content[:50]}...", end="", flush=True)
        
        elapsed = time.time() - start_time
        print(f"\n✓ 成功! 共{chunk_count}个chunk, 耗时: {elapsed:.2f}秒")
        print(f"完整响应: {full_content[:100]}...")
    except Exception as e:
        print(f"\n✗ 失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试直接LiteLLM调用
    print("\n" + "-" * 60)
    print("测试3: 直接使用LiteLLM调用Ollama")
    print("-" * 60)
    try:
        import litellm
        litellm.set_verbose = True  # 开启调试输出
        
        start_time = time.time()
        response = await litellm.acompletion(
            model=model.id,
            messages=[{"role": "user", "content": "你好"}],
            api_base="http://localhost:11434",
            stream=False,
        )
        elapsed = time.time() - start_time
        content = response.choices[0].message.content
        print(f"✓ 成功! 耗时: {elapsed:.2f}秒")
        print(f"响应: {content[:100]}...")
    except Exception as e:
        print(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_ollama_streaming())
