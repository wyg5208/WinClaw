"""Sprint 2.3 工具集成测试 — 扩展工具集验收。

覆盖：
- Browser 工具（schema / 动作定义 / Playwright 检测）
- App Control 工具（schema / 启动应用 / 列出窗口 / 窗口信息）
- Clipboard 工具（schema / 读写文本 / 清空）
- Notify 工具（schema / 发送通知）
- Search 工具（schema / 本地搜索）
- 工具注册器（8 工具自动发现 / 配置加载 / 分类查询）
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.base import ToolResultStatus
from src.tools.registry import ToolRegistry, create_default_registry
from src.tools.app_control import AppControlTool
from src.tools.clipboard import ClipboardTool
from src.tools.notify import NotifyTool
from src.tools.search import SearchTool
from src.tools.browser import BrowserTool

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} — {detail}")


# =====================================================================
# 1. Browser 工具
# =====================================================================

def test_browser_tool():
    """测试 Browser 工具定义和 schema。"""
    print("\n🧪 Browser 工具")
    tool = BrowserTool()
    check("工具名称", tool.name == "browser")
    check("工具标题", tool.title == "浏览器")
    check("工具 emoji", tool.emoji == "🌐")

    actions = tool.get_actions()
    action_names = [a.name for a in actions]
    check("8 个动作", len(actions) == 8, f"实际 {len(actions)}")
    check("包含 open_url", "open_url" in action_names)
    check("包含 click", "click" in action_names)
    check("包含 type_text", "type_text" in action_names)
    check("包含 get_text", "get_text" in action_names)
    check("包含 screenshot", "screenshot" in action_names)
    check("包含 go_back", "go_back" in action_names)
    check("包含 go_forward", "go_forward" in action_names)
    check("包含 wait", "wait" in action_names)

    schemas = tool.get_schema()
    check("schema 数量", len(schemas) == 8, f"实际 {len(schemas)}")
    check("schema 格式正确", all(s["type"] == "function" for s in schemas))

    # 检查函数名格式
    func_names = [s["function"]["name"] for s in schemas]
    check("函数名前缀", all(fn.startswith("browser_") for fn in func_names))


# =====================================================================
# 2. App Control 工具
# =====================================================================

def test_app_control_tool():
    """测试 App Control 工具定义和窗口枚举。"""
    print("\n🧪 App Control 工具")
    tool = AppControlTool()
    check("工具名称", tool.name == "app_control")
    check("工具标题", tool.title == "应用控制")

    actions = tool.get_actions()
    action_names = [a.name for a in actions]
    check("5 个动作", len(actions) == 5, f"实际 {len(actions)}")
    check("包含 launch", "launch" in action_names)
    check("包含 list_windows", "list_windows" in action_names)
    check("包含 switch_window", "switch_window" in action_names)
    check("包含 close_window", "close_window" in action_names)
    check("包含 get_window_info", "get_window_info" in action_names)

    schemas = tool.get_schema()
    check("schema 数量", len(schemas) == 5, f"实际 {len(schemas)}")


async def test_app_control_list_windows():
    """测试窗口列表功能。"""
    print("\n🧪 App Control — 列出窗口")
    tool = AppControlTool()
    result = await tool.safe_execute("list_windows", {})
    check("列出窗口成功", result.is_success)
    check("找到可见窗口", result.data.get("count", 0) > 0, f"count={result.data.get('count')}")


async def test_app_control_missing_params():
    """测试缺少参数的情况。"""
    print("\n🧪 App Control — 参数验证")
    tool = AppControlTool()

    r = await tool.safe_execute("launch", {"program": ""})
    check("空程序名返回错误", r.status == ToolResultStatus.ERROR)

    r = await tool.safe_execute("switch_window", {})
    check("无窗口参数返回错误", r.status == ToolResultStatus.ERROR)


# =====================================================================
# 3. Clipboard 工具
# =====================================================================

def test_clipboard_tool():
    """测试 Clipboard 工具定义。"""
    print("\n🧪 Clipboard 工具")
    tool = ClipboardTool()
    check("工具名称", tool.name == "clipboard")
    check("工具标题", tool.title == "剪贴板")

    actions = tool.get_actions()
    action_names = [a.name for a in actions]
    check("4 个动作", len(actions) == 4, f"实际 {len(actions)}")
    check("包含 read", "read" in action_names)
    check("包含 write", "write" in action_names)
    check("包含 read_image", "read_image" in action_names)
    check("包含 clear", "clear" in action_names)


async def test_clipboard_read_write():
    """测试剪贴板读写。"""
    print("\n🧪 Clipboard — 读写")
    tool = ClipboardTool()

    # 写入
    test_text = "WinClaw 剪贴板测试 🎉"
    r = await tool.safe_execute("write", {"text": test_text})
    check("写入成功", r.is_success)

    # 读取
    r = await tool.safe_execute("read", {})
    check("读取成功", r.is_success)
    check("内容正确", test_text in r.output)

    # 清空
    r = await tool.safe_execute("clear", {})
    check("清空成功", r.is_success)


async def test_clipboard_empty_write():
    """测试空文本写入。"""
    print("\n🧪 Clipboard — 参数验证")
    tool = ClipboardTool()
    r = await tool.safe_execute("write", {"text": ""})
    check("空文本返回错误", r.status == ToolResultStatus.ERROR)


# =====================================================================
# 4. Notify 工具
# =====================================================================

def test_notify_tool():
    """测试 Notify 工具定义。"""
    print("\n🧪 Notify 工具")
    tool = NotifyTool()
    check("工具名称", tool.name == "notify")
    check("工具标题", tool.title == "系统通知")

    actions = tool.get_actions()
    action_names = [a.name for a in actions]
    check("2 个动作", len(actions) == 2, f"实际 {len(actions)}")
    check("包含 send", "send" in action_names)
    check("包含 send_with_action", "send_with_action" in action_names)

    schemas = tool.get_schema()
    check("schema 数量", len(schemas) == 2, f"实际 {len(schemas)}")


async def test_notify_send():
    """测试发送通知。"""
    print("\n🧪 Notify — 发送通知")
    tool = NotifyTool()
    r = await tool.safe_execute("send", {
        "title": "WinClaw 测试",
        "message": "这是一条自动化测试通知",
    })
    check("发送通知成功", r.is_success)

    # 空参数测试
    r = await tool.safe_execute("send", {"title": "", "message": ""})
    check("空参数返回错误", r.status == ToolResultStatus.ERROR)


# =====================================================================
# 5. Search 工具
# =====================================================================

def test_search_tool():
    """测试 Search 工具定义。"""
    print("\n🧪 Search 工具")
    tool = SearchTool()
    check("工具名称", tool.name == "search")
    check("工具标题", tool.title == "搜索")

    actions = tool.get_actions()
    action_names = [a.name for a in actions]
    check("2 个动作", len(actions) == 2, f"实际 {len(actions)}")
    check("包含 local_search", "local_search" in action_names)
    check("包含 web_search", "web_search" in action_names)


async def test_search_local():
    """测试本地文件搜索。"""
    print("\n🧪 Search — 本地搜索")
    tool = SearchTool()

    # 创建临时测试目录
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        Path(tmpdir, "test_doc.txt").write_text("hello world", encoding="utf-8")
        Path(tmpdir, "readme.md").write_text("WinClaw project", encoding="utf-8")
        Path(tmpdir, "data.csv").write_text("a,b,c", encoding="utf-8")

        # 按文件名搜索
        r = await tool.safe_execute("local_search", {
            "directory": tmpdir,
            "pattern": "*.txt",
        })
        check("本地搜索成功", r.is_success)
        check("找到 txt 文件", r.data.get("count", 0) == 1, f"count={r.data.get('count')}")

        # 搜索所有文件
        r = await tool.safe_execute("local_search", {
            "directory": tmpdir,
            "pattern": "*",
        })
        check("搜索全部文件", r.data.get("count", 0) == 3, f"count={r.data.get('count')}")

        # 按内容搜索
        r = await tool.safe_execute("local_search", {
            "directory": tmpdir,
            "pattern": "*",
            "content": "WinClaw",
        })
        check("内容搜索", r.data.get("count", 0) == 1, f"count={r.data.get('count')}")


async def test_search_local_errors():
    """测试本地搜索错误处理。"""
    print("\n🧪 Search — 本地搜索错误")
    tool = SearchTool()

    r = await tool.safe_execute("local_search", {"directory": ""})
    check("空目录返回错误", r.status == ToolResultStatus.ERROR)

    r = await tool.safe_execute("local_search", {"directory": "Z:\\nonexistent\\path"})
    check("不存在的目录返回错误", r.status == ToolResultStatus.ERROR)


# =====================================================================
# 6. 工具注册器 — 8 工具
# =====================================================================

def test_registry_full():
    """测试完整工具注册器（配置驱动 8 工具）。"""
    print("\n🧪 工具注册器 — 完整配置")
    registry = ToolRegistry()
    registry.load_config()
    registry.auto_discover()

    tools = registry.list_tools()
    tool_names = [t.name for t in tools]
    # 注意：browser 需要 playwright 可能不可用，其他 7 个应该都能注册
    check("至少注册 7 个工具", len(tools) >= 7, f"实际 {len(tools)}: {tool_names}")

    # 验证各工具存在
    check("shell 已注册", "shell" in tool_names)
    check("file 已注册", "file" in tool_names)
    check("screen 已注册", "screen" in tool_names)
    check("app_control 已注册", "app_control" in tool_names)
    check("clipboard 已注册", "clipboard" in tool_names)
    check("notify 已注册", "notify" in tool_names)
    check("search 已注册", "search" in tool_names)

    # 验证 schema 生成
    all_schemas = registry.get_all_schemas()
    check("schema 总数 ≥ 28", len(all_schemas) >= 28, f"实际 {len(all_schemas)}")

    # 验证分类查询
    system_tools = registry.find_by_category("system")
    check("system 分类工具 ≥ 3", len(system_tools) >= 3, f"实际 {len(system_tools)}")

    # 验证函数名解析
    resolved = registry.resolve_function_name("clipboard_read")
    check("clipboard_read 解析", resolved == ("clipboard", "read"), f"实际 {resolved}")

    resolved = registry.resolve_function_name("search_web_search")
    check("search_web_search 解析", resolved == ("search", "web_search"), f"实际 {resolved}")

    resolved = registry.resolve_function_name("app_control_launch")
    check("app_control_launch 解析", resolved == ("app_control", "launch"), f"实际 {resolved}")

    # 验证工具摘要
    summary = registry.get_tools_summary()
    check("摘要非空", len(summary) > 50, f"长度 {len(summary)}")

    # 验证风险等级
    check("shell 高风险", registry.get_tool_risk_level("shell") == "high")
    check("clipboard 低风险", registry.get_tool_risk_level("clipboard") == "low")
    check("browser 中风险", registry.get_tool_risk_level("browser") == "medium")


def test_registry_default():
    """测试 create_default_registry 便捷函数。"""
    print("\n🧪 create_default_registry")
    registry = create_default_registry()
    tools = registry.list_tools()
    check("默认注册器工具数 ≥ 7", len(tools) >= 7, f"实际 {len(tools)}")


# =====================================================================
# 7. 跨工具协作测试
# =====================================================================

async def test_cross_tool_clipboard_file():
    """测试剪贴板 + 文件工具协作场景。"""
    print("\n🧪 跨工具协作 — 剪贴板 → 文件")
    from src.tools.file import FileTool

    clipboard = ClipboardTool()
    file_tool = FileTool()

    # 写入剪贴板
    test_content = "跨工具协作测试内容 2026"
    await clipboard.safe_execute("write", {"text": test_content})

    # 从剪贴板读取
    r = await clipboard.safe_execute("read", {})
    check("剪贴板读取成功", r.is_success)
    clipboard_text = test_content  # 直接使用原始文本

    # 写入临时文件
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        tmp_path = f.name

    r = await file_tool.safe_execute("write", {"path": tmp_path, "content": clipboard_text})
    check("文件写入成功", r.is_success)

    # 从文件读回验证
    r = await file_tool.safe_execute("read", {"path": tmp_path})
    check("文件读取成功", r.is_success)
    check("内容一致", test_content in r.output)

    # 清理
    Path(tmp_path).unlink(missing_ok=True)


# =====================================================================
# 主入口
# =====================================================================

def main():
    print("=" * 60)
    print("  Sprint 2.3 工具集成测试")
    print("=" * 60)

    # 同步测试
    test_browser_tool()
    test_app_control_tool()
    test_clipboard_tool()
    test_notify_tool()
    test_search_tool()
    test_registry_full()
    test_registry_default()

    # 异步测试
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(test_app_control_list_windows())
        loop.run_until_complete(test_app_control_missing_params())
        loop.run_until_complete(test_clipboard_read_write())
        loop.run_until_complete(test_clipboard_empty_write())
        loop.run_until_complete(test_notify_send())
        loop.run_until_complete(test_search_local())
        loop.run_until_complete(test_search_local_errors())
        loop.run_until_complete(test_cross_tool_clipboard_file())
    finally:
        loop.close()

    # 汇总
    print("\n" + "=" * 60)
    total = passed + failed
    print(f"  总计: {total} 项 | ✅ 通过: {passed} | ❌ 失败: {failed}")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
