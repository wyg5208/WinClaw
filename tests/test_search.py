"""测试搜索工具的网络连接"""
import asyncio
from src.tools.search import SearchTool

async def test_search():
    tool = SearchTool(web_timeout=15)  # 增加超时时间
    
    print("=" * 60)
    print("测试网络搜索功能")
    print("=" * 60)
    
    # 测试 Bing
    print("\n[1/3] 测试 Bing 搜索...")
    tool.search_engine = "bing"
    result = await tool.execute("web_search", {"query": "Python", "max_results": 2})
    if result.status.value == "success":
        print("✅ Bing 搜索成功")
        print(result.output[:200])
    else:
        print(f"❌ Bing 搜索失败: {result.error}")
    
    # 测试百度
    print("\n[2/3] 测试百度搜索...")
    tool.search_engine = "baidu"
    result = await tool.execute("web_search", {"query": "Python", "max_results": 2})
    if result.status.value == "success":
        print("✅ 百度搜索成功")
        print(result.output[:200])
    else:
        print(f"❌ 百度搜索失败: {result.error}")
    
    # 测试自动模式（会尝试所有引擎）
    print("\n[3/3] 测试自动模式...")
    tool.search_engine = "auto"
    result = await tool.execute("web_search", {"query": "Python编程", "max_results": 2})
    if result.status.value == "success":
        print(f"✅ 自动模式成功 (使用引擎: {result.data.get('engine', 'unknown')})")
        print(result.output[:300])
    else:
        print(f"❌ 自动模式失败: {result.error}")
        print(result.output)
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_search())
