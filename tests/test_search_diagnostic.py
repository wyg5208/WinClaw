"""搜索工具完整诊断脚本 - 定位网络搜索问题"""
import asyncio
import sys
import time
import urllib.request
import urllib.parse
from src.tools.search import SearchTool

def test_basic_network():
    """测试基础网络连接"""
    print("=" * 70)
    print("第一步: 测试基础网络连接")
    print("=" * 70)
    
    test_urls = [
        ("百度", "https://www.baidu.com"),
        ("Bing", "https://www.bing.com"),
        ("DuckDuckGo", "https://duckduckgo.com"),
    ]
    
    results = {}
    for name, url in test_urls:
        try:
            print(f"\n[{name}] 测试连接 {url} ...")
            start = time.time()
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                elapsed = time.time() - start
                print(f"  ✅ 连接成功 (HTTP {status}, 耗时 {elapsed:.2f}s)")
                results[name] = True
        except Exception as e:
            elapsed = time.time() - start
            print(f"  ❌ 连接失败 ({elapsed:.2f}s): {type(e).__name__}: {e}")
            results[name] = False
    
    print("\n" + "-" * 70)
    print("基础连接测试结果:")
    for name, success in results.items():
        status = "✅ 可用" if success else "❌ 不可用"
        print(f"  {name}: {status}")
    
    return results

def test_search_engines_directly():
    """直接测试各搜索引擎的解析"""
    print("\n" + "=" * 70)
    print("第二步: 直接测试搜索引擎API")
    print("=" * 70)
    
    tool = SearchTool(web_timeout=15)
    
    engines = [
        ("百度", "baidu", "Python"),
        ("Bing", "bing", "Python"),
        ("DuckDuckGo", "duckduckgo", "Python"),
    ]
    
    results = {}
    for name, engine, query in engines:
        print(f"\n[{name}] 测试搜索 '{query}'...")
        try:
            start = time.time()
            fetch_func = getattr(tool, f"_fetch_{engine}")
            search_results = fetch_func(query, 3)
            elapsed = time.time() - start
            
            if search_results:
                print(f"  ✅ 搜索成功 ({elapsed:.2f}s)")
                print(f"  找到 {len(search_results)} 条结果:")
                for i, r in enumerate(search_results[:2], 1):
                    print(f"    {i}. {r['title'][:50]}")
                    print(f"       {r['url'][:80]}")
                results[name] = True
            else:
                print(f"  ⚠️  搜索完成但无结果 ({elapsed:.2f}s)")
                results[name] = False
        except Exception as e:
            elapsed = time.time() - start
            print(f"  ❌ 搜索失败 ({elapsed:.2f}s): {type(e).__name__}: {e}")
            results[name] = False
    
    print("\n" + "-" * 70)
    print("搜索引擎测试结果:")
    for name, success in results.items():
        status = "✅ 可用" if success else "❌ 不可用"
        print(f"  {name}: {status}")
    
    return results

async def test_tool_execute():
    """测试工具的 execute 方法"""
    print("\n" + "=" * 70)
    print("第三步: 测试 SearchTool.execute() 方法")
    print("=" * 70)
    
    tool = SearchTool(web_timeout=15)
    
    # 测试自动模式
    print("\n[自动模式] 测试 web_search...")
    print(f"  当前配置: search_engine='{tool.search_engine}'")
    
    start = time.time()
    result = await tool.execute("web_search", {"query": "Python编程", "max_results": 3})
    elapsed = time.time() - start
    
    print(f"\n  执行完成 (耗时 {elapsed:.2f}s)")
    print(f"  状态: {result.status.value}")
    
    if result.status.value == "success":
        print(f"  ✅ 搜索成功")
        print(f"  使用的引擎: {result.data.get('engine', 'unknown')}")
        print(f"  结果数量: {result.data.get('count', 0)}")
        print(f"\n  前2条结果:")
        for i, r in enumerate(result.data.get('results', [])[:2], 1):
            print(f"    {i}. {r['title'][:60]}")
            print(f"       {r['url'][:80]}")
    else:
        print(f"  ❌ 搜索失败")
        print(f"  错误: {result.error}")
        if result.output:
            print(f"  输出: {result.output}")
    
    return result.status.value == "success"

async def test_each_engine_individually():
    """单独测试每个引擎"""
    print("\n" + "=" * 70)
    print("第四步: 通过 execute() 单独测试各引擎")
    print("=" * 70)
    
    engines = ["baidu", "bing", "duckduckgo"]
    results = {}
    
    for engine in engines:
        tool = SearchTool(web_timeout=15, search_engine=engine)
        print(f"\n[{engine}] 测试...")
        
        start = time.time()
        result = await tool.execute("web_search", {"query": "Python", "max_results": 2})
        elapsed = time.time() - start
        
        if result.status.value == "success":
            print(f"  ✅ 成功 ({elapsed:.2f}s) - {result.data.get('count', 0)} 条结果")
            results[engine] = True
        else:
            print(f"  ❌ 失败 ({elapsed:.2f}s): {result.error}")
            results[engine] = False
    
    print("\n" + "-" * 70)
    print("各引擎单独测试结果:")
    for engine, success in results.items():
        status = "✅ 可用" if success else "❌ 不可用"
        print(f"  {engine}: {status}")
    
    return results

def generate_recommendations(network_test, engine_test, individual_test):
    """生成修复建议"""
    print("\n" + "=" * 70)
    print("诊断结果与修复建议")
    print("=" * 70)
    
    # 分析可用的引擎
    available_engines = [name for name, success in engine_test.items() if success]
    
    if not available_engines:
        print("\n❌ 所有搜索引擎均不可用")
        print("\n可能的原因:")
        print("  1. 网络连接问题（防火墙/代理设置）")
        print("  2. DNS 解析失败")
        print("  3. 搜索引擎服务器暂时不可用")
        print("\n建议:")
        print("  1. 检查网络连接和代理设置")
        print("  2. 尝试在浏览器中访问这些搜索引擎")
        print("  3. 检查防火墙规则")
    else:
        print(f"\n✅ 可用的搜索引擎: {', '.join(available_engines)}")
        
        # 推荐配置
        if "baidu" in available_engines:
            recommended = "baidu"
        elif "bing" in available_engines:
            recommended = "bing"
        else:
            recommended = available_engines[0]
        
        print(f"\n推荐配置: search_engine = '{recommended}'")
        print(f"\n修改方法:")
        print(f"  1. 打开 winclaw/config/tools.json")
        print(f"  2. 找到 'search' 工具配置")
        print(f"  3. 添加或修改:")
        print(f'     "init_params": {{')
        print(f'       "search_engine": "{recommended}"')
        print(f'     }}')
        
        # 如果自动模式有问题，建议修改顺序
        if "baidu" in available_engines:
            print(f"\n或者修改代码中的自动模式顺序:")
            print(f"  在 search.py 的 _web_search() 方法中:")
            print(f"  将 engines = ['bing', 'baidu', 'duckduckgo']")
            print(f"  改为 engines = ['baidu', 'bing', 'duckduckgo']")

async def main():
    """主诊断流程"""
    print("\n" + "=" * 70)
    print("WinClaw 搜索工具完整诊断")
    print("=" * 70)
    print("\n本脚本将执行以下测试:")
    print("  1. 基础网络连接测试")
    print("  2. 搜索引擎直接调用测试")
    print("  3. SearchTool.execute() 方法测试")
    print("  4. 各引擎单独测试")
    print("  5. 生成修复建议")
    print("\n" + "=" * 70)
    
    try:
        # 第一步: 基础网络测试
        network_results = test_basic_network()
        
        # 第二步: 直接测试搜索引擎
        engine_results = test_search_engines_directly()
        
        # 第三步: 测试 execute 方法
        await test_tool_execute()
        
        # 第四步: 单独测试各引擎
        individual_results = await test_each_engine_individually()
        
        # 第五步: 生成建议
        generate_recommendations(network_results, engine_results, individual_results)
        
        print("\n" + "=" * 70)
        print("诊断完成!")
        print("=" * 70)
        
    except KeyboardInterrupt:
        print("\n\n用户中断测试")
    except Exception as e:
        print(f"\n\n❌ 诊断过程出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
