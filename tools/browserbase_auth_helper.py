#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Browserbase 认证助手
用于创建持久化的登录会话，支持需要登录的网站自动化

使用方法:
1. python browserbase_auth_helper.py create --name csdn
   创建一个新的 context，返回 Live View URL
2. 在浏览器中打开 Live View URL，手动登录 CSDN
3. 登录完成后按回车键，context 会被保存
4. python browserbase_auth_helper.py list
   查看已保存的所有 context
5. python browserbase_auth_helper.py test --name csdn
   测试 context 是否有效
"""

import os
import sys
import json
import time
import argparse
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
    
    browserbase_config = config.get("mcpServers", {}).get("browserbase", {})
    env = browserbase_config.get("env", {})
    
    api_key = env.get("BROWSERBASE_API_KEY", "")
    project_id = env.get("BROWSERBASE_PROJECT_ID", "")
    
    if not api_key or api_key.startswith("在此填入"):
        print("❌ 请先在 mcp_servers.json 中配置 BROWSERBASE_API_KEY")
        sys.exit(1)
    
    if not project_id or project_id.startswith("在此填入"):
        print("❌ 请先在 mcp_servers.json 中配置 BROWSERBASE_PROJECT_ID")
        sys.exit(1)
    
    return api_key, project_id


def load_contexts():
    """加载已保存的 contexts"""
    if CONTEXTS_FILE.exists():
        with open(CONTEXTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_contexts(contexts):
    """保存 contexts"""
    with open(CONTEXTS_FILE, "w", encoding="utf-8") as f:
        json.dump(contexts, f, indent=2, ensure_ascii=False)


def create_context(api_key: str, project_id: str, name: str, login_url: str = None):
    """创建新的 Browserbase context"""
    import requests
    
    print(f"\n🔄 正在创建新的 Browserbase context: {name}")
    
    # 创建 context
    response = requests.post(
        "https://api.browserbase.com/v1/contexts",
        headers={
            "Content-Type": "application/json",
            "X-BB-API-Key": api_key
        },
        json={"projectId": project_id}
    )
    
    if response.status_code not in [200, 201]:
        print(f"❌ 创建 context 失败: {response.status_code} - {response.text}")
        sys.exit(1)
    
    context = response.json()
    context_id = context.get("id")
    print(f"✅ Context 创建成功: {context_id}")
    
    # 创建 session 并启用 persist
    session_data = {
        "projectId": project_id,
        "browserSettings": {
            "context": {
                "id": context_id,
                "persist": True
            }
        }
    }
    
    # 代理功能需要付费计划，免费用户禁用
    # session_data["proxies"] = True
    
    print("🔄 正在创建浏览器会话...")
    
    session_response = requests.post(
        "https://api.browserbase.com/v1/sessions",
        headers={
            "Content-Type": "application/json",
            "X-BB-API-Key": api_key
        },
        json=session_data
    )
    
    if session_response.status_code not in [200, 201]:
        print(f"❌ 创建 session 失败: {session_response.status_code} - {session_response.text}")
        sys.exit(1)
    
    session = session_response.json()
    session_id = session.get("id")
    live_url = f"https://www.browserbase.com/sessions/{session_id}"
    
    print("\n" + "=" * 60)
    print("🌐 浏览器会话已创建!")
    print("=" * 60)
    print(f"\n📱 Live View URL: {live_url}")
    print("\n请在浏览器中打开上面的链接，完成以下步骤：")
    print("1. 在打开的浏览器中访问目标网站")
    print("2. 手动完成登录")
    print("3. 确认登录成功后，回到此终端按回车键")
    print("=" * 60)
    
    # 可选：自动导航到登录页面
    if login_url:
        print(f"\n🔗 建议访问: {login_url}")
    
    input("\n✅ 登录完成后按回车键继续...")
    
    # 结束 session 以保存 context
    print("\n🔄 正在保存登录状态...")
    
    end_response = requests.post(
        f"https://api.browserbase.com/v1/sessions/{session_id}/end",
        headers={"X-BB-API-Key": api_key}
    )
    
    # 等待 context 同步
    print("⏳ 等待 context 数据同步...")
    time.sleep(3)
    
    # 保存 context 信息
    contexts = load_contexts()
    contexts[name] = {
        "context_id": context_id,
        "created_at": datetime.now().isoformat(),
        "last_used": datetime.now().isoformat(),
        "login_url": login_url,
        "session_id": session_id
    }
    save_contexts(contexts)
    
    print(f"\n✅ 登录状态已保存到 context: {name}")
    print(f"   Context ID: {context_id}")
    print(f"   下次使用时将自动恢复登录状态")
    
    return context_id


def test_context(api_key: str, project_id: str, name: str):
    """测试 context 是否有效"""
    import requests
    
    contexts = load_contexts()
    if name not in contexts:
        print(f"❌ 找不到名为 '{name}' 的 context")
        print(f"   已有的 context: {list(contexts.keys())}")
        sys.exit(1)
    
    context_info = contexts[name]
    context_id = context_info["context_id"]
    
    print(f"\n🔄 测试 context: {name} ({context_id})")
    
    # 创建使用该 context 的 session
    session_data = {
        "projectId": project_id,
        "browserSettings": {
            "context": {
                "id": context_id,
                "persist": False  # 只读模式测试
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
    
    if response.status_code == 200:
        session = response.json()
        session_id = session.get("id")
        live_url = f"https://www.browserbase.com/sessions/{session_id}"
        
        print(f"✅ Context 有效!")
        print(f"   Live View: {live_url}")
        print(f"   你可以在 Live View 中检查登录状态")
        
        # 更新最后使用时间
        contexts[name]["last_used"] = datetime.now().isoformat()
        save_contexts(contexts)
    else:
        print(f"❌ Context 可能已失效: {response.text}")


def list_contexts():
    """列出所有已保存的 contexts"""
    contexts = load_contexts()
    
    if not contexts:
        print("\n📭 还没有保存任何 context")
        print("   使用 'python browserbase_auth_helper.py create --name <名称>' 创建")
        return
    
    print("\n📋 已保存的 Browserbase Contexts:")
    print("=" * 60)
    
    for name, info in contexts.items():
        print(f"\n🏷️  {name}")
        print(f"   Context ID: {info.get('context_id')}")
        print(f"   创建时间: {info.get('created_at')}")
        print(f"   最后使用: {info.get('last_used')}")
        if info.get('login_url'):
            print(f"   登录页面: {info.get('login_url')}")


def delete_context(api_key: str, name: str):
    """删除 context"""
    import requests
    
    contexts = load_contexts()
    if name not in contexts:
        print(f"❌ 找不到名为 '{name}' 的 context")
        sys.exit(1)
    
    context_id = contexts[name]["context_id"]
    
    print(f"\n🗑️  正在删除 context: {name} ({context_id})")
    
    response = requests.delete(
        f"https://api.browserbase.com/v1/contexts/{context_id}",
        headers={"X-BB-API-Key": api_key}
    )
    
    if response.status_code == 200:
        del contexts[name]
        save_contexts(contexts)
        print(f"✅ Context 已删除")
    else:
        print(f"❌ 删除失败: {response.text}")


def main():
    parser = argparse.ArgumentParser(
        description="Browserbase 认证助手 - 管理持久化登录会话",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python browserbase_auth_helper.py create --name csdn --url https://editor.csdn.net
  python browserbase_auth_helper.py list
  python browserbase_auth_helper.py test --name csdn
  python browserbase_auth_helper.py delete --name csdn
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # create 命令
    create_parser = subparsers.add_parser("create", help="创建新的认证 context")
    create_parser.add_argument("--name", required=True, help="Context 名称（如：csdn, github）")
    create_parser.add_argument("--url", help="登录页面 URL（可选）")
    
    # list 命令
    subparsers.add_parser("list", help="列出所有已保存的 contexts")
    
    # test 命令
    test_parser = subparsers.add_parser("test", help="测试 context 是否有效")
    test_parser.add_argument("--name", required=True, help="Context 名称")
    
    # delete 命令
    delete_parser = subparsers.add_parser("delete", help="删除 context")
    delete_parser.add_argument("--name", required=True, help="Context 名称")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    api_key, project_id = load_env()
    
    if args.command == "create":
        create_context(api_key, project_id, args.name, args.url)
    elif args.command == "list":
        list_contexts()
    elif args.command == "test":
        test_context(api_key, project_id, args.name)
    elif args.command == "delete":
        delete_context(api_key, args.name)


if __name__ == "__main__":
    main()
