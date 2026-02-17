#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CSDN 博客发布助手
专门处理 CSDN 编辑器的 contenteditable 元素输入问题

使用 Browserbase API + Playwright 连接云端浏览器
支持 JavaScript 注入和模拟键盘输入两种方式
"""

import os
import sys
import json
import asyncio
import time
from pathlib import Path
from datetime import datetime

# 配置文件路径
CONFIG_DIR = Path(__file__).parent.parent / "config"
CONTEXTS_FILE = CONFIG_DIR / "browserbase_contexts.json"


def load_env():
    """从 mcp_servers.json 加载 Browserbase 凭证"""
    mcp_config_path = CONFIG_DIR / "mcp_servers.json"
    if not mcp_config_path.exists():
        print("❌ 找不到 mcp_servers.json 配置文件")
        sys.exit(1)
    
    with open(mcp_config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    browserbase_config = config.get("mcpServers", {}).get("browserbase-csdn", {})
    env = browserbase_config.get("env", {})
    
    api_key = env.get("BROWSERBASE_API_KEY", "")
    project_id = env.get("BROWSERBASE_PROJECT_ID", "")
    
    if not api_key or api_key.startswith("在此填入"):
        print("❌ 请先在 mcp_servers.json 中配置 BROWSERBASE_API_KEY")
        sys.exit(1)
    
    return api_key, project_id


def get_context_id():
    """获取 CSDN context ID"""
    if CONTEXTS_FILE.exists():
        with open(CONTEXTS_FILE, "r", encoding="utf-8") as f:
            contexts = json.load(f)
            if "csdn" in contexts:
                return contexts["csdn"].get("context_id")
    return None


async def publish_blog(title: str, content: str, method: str = "js"):
    """发布 CSDN 博客
    
    Args:
        title: 博客标题
        content: 博客内容（Markdown 或纯文本）
        method: 输入方式
            - "js": JavaScript 注入（快速，可能被检测）
            - "type": 模拟键盘输入（慢，更真实）
            - "paste": 模拟粘贴（推荐）
    """
    import requests
    
    api_key, project_id = load_env()
    context_id = get_context_id()
    
    if not context_id:
        print("❌ 找不到 CSDN context，请先运行认证助手")
        sys.exit(1)
    
    print(f"\n🔄 创建 Browserbase 会话...")
    print(f"   Context ID: {context_id}")
    
    # 创建 session
    session_data = {
        "projectId": project_id,
        "browserSettings": {
            "context": {
                "id": context_id,
                "persist": True
            }
        }
    }
    
    response = requests.post(
        "https://api.browserbase.com/v1/sessions",
        headers={
            "Content-Type": "application/json",
            "X-BB-API-Key": api_key
        },
        json=session_data
    )
    
    if response.status_code not in [200, 201]:
        print(f"❌ 创建 session 失败: {response.text}")
        sys.exit(1)
    
    session = response.json()
    session_id = session.get("id")
    connect_url = session.get("connectUrl")
    live_url = f"https://www.browserbase.com/sessions/{session_id}"
    
    print(f"✅ 会话创建成功")
    print(f"   Live View: {live_url}")
    
    # 使用 Playwright 连接
    print(f"\n🔄 连接云端浏览器...")
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(connect_url)
            
            # 获取默认上下文和页面
            contexts = browser.contexts
            if contexts:
                context = contexts[0]
                pages = context.pages
                if pages:
                    page = pages[0]
                else:
                    page = await context.new_page()
            else:
                context = await browser.new_context()
                page = await context.new_page()
            
            print(f"✅ 已连接到云端浏览器")
            
            # 导航到 CSDN 编辑器
            editor_url = "https://editor.csdn.net/md/?not_checkout=1&spm=1015.2103.3001.8066"
            print(f"\n🔄 打开 CSDN 编辑器: {editor_url}")
            
            await page.goto(editor_url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)  # 等待编辑器加载
            
            # 检查是否已登录
            current_url = page.url
            if "passport.csdn.net" in current_url or "login" in current_url:
                print("❌ 未登录或登录已过期，请重新运行认证助手")
                await browser.close()
                sys.exit(1)
            
            print(f"✅ 已登录 CSDN")
            
            # 等待编辑器完全加载
            print(f"\n⏳ 等待编辑器加载...")
            await page.wait_for_timeout(5000)
            
            # 输入标题
            print(f"\n📝 输入标题: {title}")
            
            # CSDN 标题输入框
            title_selectors = [
                "#title",
                "input[placeholder*='标题']",
                "input.title-input",
                ".article-bar input",
            ]
            
            title_input = None
            for selector in title_selectors:
                try:
                    title_input = await page.wait_for_selector(selector, timeout=5000)
                    if title_input:
                        break
                except:
                    continue
            
            if title_input:
                await title_input.click()
                await title_input.fill("")
                await title_input.type(title, delay=50)
                print(f"✅ 标题已输入")
            else:
                print("⚠️ 未找到标题输入框，尝试 JavaScript 方式")
                await page.evaluate(f"""
                    const titleInput = document.querySelector('#title') || 
                                      document.querySelector('input[placeholder*="标题"]');
                    if (titleInput) {{
                        titleInput.value = '{title}';
                        titleInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                """)
            
            await page.wait_for_timeout(1000)
            
            # 输入内容
            print(f"\n📝 输入博客内容 ({len(content)} 字符)...")
            print(f"   使用方式: {method}")
            
            # CSDN 编辑器选择器（contenteditable）
            editor_selectors = [
                "#editor",
                ".editor-content",
                "[contenteditable='true']",
                ".markdown-body",
                ".ck-editor__editable",
                ".vditor-ir",
            ]
            
            if method == "js":
                # JavaScript 注入方式
                print("   使用 JavaScript 注入...")
                
                # 尝试多种编辑器
                js_code = f"""
                (function() {{
                    // 尝试多种编辑器选择器
                    const selectors = {json.dumps(editor_selectors)};
                    let editor = null;
                    
                    for (const sel of selectors) {{
                        editor = document.querySelector(sel);
                        if (editor) break;
                    }}
                    
                    if (editor) {{
                        // 清空并设置内容
                        editor.innerHTML = `{content.replace('`', '\\`').replace('\n', '<br>')}`;
                        editor.focus();
                        
                        // 触发事件
                        editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        editor.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        editor.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true }}));
                        
                        return '内容已注入到: ' + editor.className;
                    }}
                    
                    return '未找到编辑器元素';
                }})();
                """
                
                result = await page.evaluate(js_code)
                print(f"   {result}")
                
            elif method == "paste":
                # 模拟粘贴方式（推荐）
                print("   使用模拟粘贴...")
                
                editor = None
                for selector in editor_selectors:
                    try:
                        editor = await page.wait_for_selector(selector, timeout=3000)
                        if editor:
                            print(f"   找到编辑器: {selector}")
                            break
                    except:
                        continue
                
                if editor:
                    await editor.click()
                    await page.wait_for_timeout(500)
                    
                    # 使用 clipboard API
                    await page.evaluate(f"""
                        navigator.clipboard.writeText(`{content.replace('`', '\\`')}`);
                    """)
                    
                    # 模拟 Ctrl+V
                    await page.keyboard.down("Control")
                    await page.keyboard.press("v")
                    await page.keyboard.up("Control")
                    
                    print(f"✅ 内容已粘贴")
                else:
                    print("❌ 未找到编辑器，回退到 JavaScript 方式")
                    method = "js"
                    
            else:  # type
                # 模拟键盘输入方式
                print("   使用模拟键盘输入（较慢）...")
                
                editor = None
                for selector in editor_selectors:
                    try:
                        editor = await page.wait_for_selector(selector, timeout=3000)
                        if editor:
                            break
                    except:
                        continue
                
                if editor:
                    await editor.click()
                    await page.wait_for_timeout(500)
                    
                    # 分段输入，每段之间有延迟
                    chunk_size = 100
                    for i in range(0, len(content), chunk_size):
                        chunk = content[i:i+chunk_size]
                        await page.keyboard.type(chunk, delay=10)
                        await page.wait_for_timeout(100)
                        print(f"   已输入 {min(i+chunk_size, len(content))}/{len(content)} 字符")
                    
                    print(f"✅ 内容已输入")
            
            await page.wait_for_timeout(2000)
            
            # 截图确认
            screenshot_path = Path(__file__).parent.parent / "output" / f"csdn_editor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path))
            print(f"\n📸 编辑器截图已保存: {screenshot_path}")
            
            print(f"\n" + "=" * 60)
            print("✅ 博客内容已填入编辑器！")
            print("=" * 60)
            print(f"\n请手动检查编辑器内容，然后点击发布按钮。")
            print(f"Live View: {live_url}")
            print(f"\n提示：如果内容未显示，请尝试其他输入方式：")
            print(f"  python csdn_publisher.py --method paste")
            print(f"  python csdn_publisher.py --method type")
            
            # 等待用户确认
            input("\n按回车键结束会话...")
            
            await browser.close()
            
    except ImportError:
        print("❌ 未安装 playwright，请运行: pip install playwright && playwright install chromium")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 操作失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="CSDN 博客发布助手")
    parser.add_argument("--title", "-t", default="测试博客", help="博客标题")
    parser.add_argument("--content", "-c", help="博客内容（不提供则使用示例内容）")
    parser.add_argument("--file", "-f", help="从文件读取博客内容")
    parser.add_argument("--method", "-m", choices=["js", "type", "paste"], default="paste",
                        help="输入方式: js(JavaScript注入), type(模拟键盘), paste(模拟粘贴，推荐)")
    
    args = parser.parse_args()
    
    # 获取内容
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    elif args.content:
        content = args.content
    else:
        # 示例内容
        content = """# 测试博客标题

这是一篇测试博客，用于验证 CSDN 博客发布功能。

## 功能特点

1. **自动登录** - 使用 Browserbase Context 保持登录状态
2. **智能输入** - 支持 JavaScript 注入、模拟键盘、模拟粘贴三种方式
3. **内容验证** - 自动截图确认编辑器状态

## 代码示例

```python
def hello_world():
    print("Hello, CSDN!")
```

## 总结

这是一个测试博客，展示了 WinClaw 自动发布 CSDN 博客的能力。
"""
    
    asyncio.run(publish_blog(args.title, content, args.method))


if __name__ == "__main__":
    main()
