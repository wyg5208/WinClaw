"""测试搜索工具的分页功能"""
import asyncio
from src.tools.search import SearchTool

async def main():
    print("=" * 70)
    print("WinClaw 搜索工具分页测试")
    print("=" * 70)
    
    tool = SearchTool(web_timeout=10)
    query = "Python编程"
    
    # 测试1: 单页多结果
    print(f"\n{'='*70}")
    print(f"测试1: 单页返回多个结果 (max_results=20)")
    print(f"{'='*70}")
    
    result = await tool.execute("web_search", {
        "query": query,
        "max_results": 20,
    })
    
    if result.status.value == "success":
        print(f"✅ 成功! 找到 {result.data['count']} 条结果")
        print(f"   引擎: {result.data['engine']}")
        print(f"   页码: {result.data['page']}")
        print(f"   可能有更多: {result.data['has_more']}")
        print(f"\n前5条结果:")
        for i, r in enumerate(result.data['results'][:5], 1):
            print(f"  {i}. {r['title'][:60]}")
    else:
        print(f"❌ 失败: {result.error}")
    
    # 测试2: 第一页
    print(f"\n{'='*70}")
    print(f"测试2: 第1页 (每页10条)")
    print(f"{'='*70}")
    
    result = await tool.execute("web_search", {
        "query": query,
        "max_results": 10,
        "page": 1,
    })
    
    if result.status.value == "success":
        print(f"✅ 第1页: {result.data['count']} 条结果")
        for i, r in enumerate(result.data['results'], 1):
            print(f"  {i}. {r['title'][:60]}")
    
    # 测试3: 第二页
    print(f"\n{'='*70}")
    print(f"测试3: 第2页 (每页10条)")
    print(f"{'='*70}")
    
    result = await tool.execute("web_search", {
        "query": query,
        "max_results": 10,
        "page": 2,
    })
    
    if result.status.value == "success":
        print(f"✅ 第2页: {result.data['count']} 条结果")
        for i, r in enumerate(result.data['results'], 1):
            print(f"  {i + 10}. {r['title'][:60]}")  # 编号从11开始
    else:
        print(f"❌ 失败: {result.error}")
    
    # 测试4: 第三页
    print(f"\n{'='*70}")
    print(f"测试4: 第3页 (每页10条)")
    print(f"{'='*70}")
    
    result = await tool.execute("web_search", {
        "query": query,
        "max_results": 10,
        "page": 3,
    })
    
    if result.status.value == "success":
        print(f"✅ 第3页: {result.data['count']} 条结果")
        for i, r in enumerate(result.data['results'], 1):
            print(f"  {i + 20}. {r['title'][:60]}")  # 编号从21开始
    else:
        print(f"❌ 失败: {result.error}")
    
    # 测试5: 最大结果测试
    print(f"\n{'='*70}")
    print(f"测试5: 单次最大结果数 (max_results=50)")
    print(f"{'='*70}")
    
    result = await tool.execute("web_search", {
        "query": "人工智能",
        "max_results": 50,
    })
    
    if result.status.value == "success":
        print(f"✅ 成功! 找到 {result.data['count']} 条结果")
        print(f"   实际返回: {len(result.data['results'])} 条")
        print(f"   (Bing最多支持50条/页)")
    else:
        print(f"❌ 失败: {result.error}")
    
    print("\n" + "=" * 70)
    print("分页功能总结:")
    print("=" * 70)
    print("✅ 支持参数:")
    print("   - max_results: 每页结果数 (1-50, 默认10)")
    print("   - page: 页码 (1-10, 默认1)")
    print()
    print("✅ 分页支持情况:")
    print("   - Bing: ✅ 完整支持 (最多50条/页, 最多10页)")
    print("   - 百度: ✅ 完整支持 (最多50条/页, 最多10页)")
    print("   - DuckDuckGo: ❌ 仅第一页 (HTML版限制)")
    print()
    print("✅ 使用示例:")
    print("   # 第一页10条")
    print("   tool.execute('web_search', {'query': 'Python', 'max_results': 10, 'page': 1})")
    print()
    print("   # 第二页20条")
    print("   tool.execute('web_search', {'query': 'Python', 'max_results': 20, 'page': 2})")
    print()
    print("   # 单次最多50条")
    print("   tool.execute('web_search', {'query': 'Python', 'max_results': 50})")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
