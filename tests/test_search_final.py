"""最终搜索测试 - 验证修复效果"""
import asyncio
from src.tools.search import SearchTool

async def main():
    print("=" * 70)
    print("WinClaw 搜索工具最终测试")
    print("=" * 70)
    
    tool = SearchTool(web_timeout=10)  # 自动模式
    
    test_queries = [
        ("Python编程", 3),
        ("DeepSeek V3", 5),
        ("人工智能AI", 3),
    ]
    
    for query, max_results in test_queries:
        print(f"\n{'='*70}")
        print(f"搜索: '{query}' (最多 {max_results} 条结果)")
        print(f"{'='*70}")
        
        result = await tool.execute("web_search", {
            "query": query,
            "max_results": max_results
        })
        
        if result.status.value == "success":
            engine = result.data.get('engine', 'unknown')
            count = result.data.get('count', 0)
            print(f"✅ 搜索成功! (使用引擎: {engine}, 找到 {count} 条结果)\n")
            
            for i, r in enumerate(result.data.get('results', []), 1):
                print(f"{i}. {r['title'][:65]}")
                print(f"   {r['url'][:75]}")
                if r.get('snippet'):
                    print(f"   {r['snippet'][:100]}...")
                print()
        else:
            print(f"❌ 搜索失败: {result.error}\n")
            if result.output:
                print(f"   {result.output}")
    
    print("=" * 70)
    print("测试完成!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
