"""调试搜索引擎HTML返回内容"""
import urllib.request
import urllib.parse
import re

def debug_baidu():
    """调试百度搜索返回的HTML"""
    print("=" * 70)
    print("调试百度搜索")
    print("=" * 70)
    
    query = "Python"
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.baidu.com/s?wd={encoded_query}&rn=10"
    
    print(f"\n请求URL: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            
            print(f"\n响应状态: {resp.status}")
            print(f"内容长度: {len(html)} 字符")
            
            # 保存HTML到文件
            with open("debug_baidu.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("\n✅ HTML已保存到 debug_baidu.html")
            
            # 尝试查找结果块
            print("\n查找结果块...")
            
            # 方法1: 查找 id="content_left" 或类似容器
            content_match = re.search(r'<div[^>]*id="content_left"[^>]*>(.*?)</div>', html, re.DOTALL)
            if content_match:
                print("  找到 content_left 容器")
            
            # 方法2: 查找所有 class 包含 "result" 的 div
            result_divs = re.findall(r'<div[^>]*class="[^"]*result[^"]*"', html)
            print(f"  找到 {len(result_divs)} 个包含 'result' class 的 div")
            if result_divs:
                print(f"  示例: {result_divs[0]}")
            
            # 方法3: 查找所有链接
            links = re.findall(r'<a[^>]+href="([^"]*)"[^>]*>([^<]+)</a>', html)
            print(f"  找到 {len(links)} 个链接")
            
            # 方法4: 查找 <h3> 标签（通常是标题）
            h3_tags = re.findall(r'<h3[^>]*>(.*?)</h3>', html, re.DOTALL)
            print(f"  找到 {len(h3_tags)} 个 <h3> 标签")
            if h3_tags:
                for i, h3 in enumerate(h3_tags[:3], 1):
                    clean = re.sub(r'<[^>]+>', '', h3).strip()
                    if clean:
                        print(f"    {i}. {clean[:80]}")
            
            # 方法5: 更激进的匹配
            print("\n尝试更宽松的匹配模式...")
            
            # 查找 tpl="xxx" 属性 (百度新版)
            tpl_results = re.findall(r'<div[^>]*tpl="[^"]*"[^>]*>', html)
            print(f"  找到 {len(tpl_results)} 个带 tpl 属性的结果")
            
            # 查找 data-tools 属性
            data_tools = re.findall(r'<div[^>]*data-tools="[^"]*"[^>]*>', html)
            print(f"  找到 {len(data_tools)} 个带 data-tools 属性的结果")
            
    except Exception as e:
        print(f"\n❌ 请求失败: {e}")

def debug_bing():
    """调试Bing搜索返回的HTML"""
    print("\n" + "=" * 70)
    print("调试Bing搜索")
    print("=" * 70)
    
    query = "Python"
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/search?q={encoded_query}&count=10"
    
    print(f"\n请求URL: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            
            print(f"\n响应状态: {resp.status}")
            print(f"内容长度: {len(html)} 字符")
            
            # 保存HTML到文件
            with open("debug_bing.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("\n✅ HTML已保存到 debug_bing.html")
            
            # 查找结果
            print("\n查找结果块...")
            
            # 查找 class="b_algo"
            algo_results = re.findall(r'<li[^>]*class="[^"]*b_algo[^"]*"', html)
            print(f"  找到 {len(algo_results)} 个 b_algo 结果")
            
            # 查找所有 h2 标签
            h2_tags = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL)
            print(f"  找到 {len(h2_tags)} 个 <h2> 标签")
            if h2_tags:
                for i, h2 in enumerate(h2_tags[:3], 1):
                    clean = re.sub(r'<[^>]+>', '', h2).strip()
                    if clean:
                        print(f"    {i}. {clean[:80]}")
            
            # 查找 data-bm 属性
            data_bm = re.findall(r'data-bm="[^"]*"', html)
            print(f"  找到 {len(data_bm)} 个带 data-bm 属性的元素")
            
    except Exception as e:
        print(f"\n❌ 请求失败: {e}")

if __name__ == "__main__":
    debug_baidu()
    debug_bing()
    
    print("\n" + "=" * 70)
    print("调试完成! 请检查生成的 HTML 文件")
    print("  - debug_baidu.html")
    print("  - debug_bing.html")
    print("=" * 70)
