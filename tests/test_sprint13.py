"""Sprint 1.3 集成验收测试 — 工具增强 / 权限管理 / 审计日志。

覆盖：
- 工具注册器重构（配置驱动、自动发现、分类查询）
- Shell 增强（黑名单/白名单/工作目录/环境变量）
- File 增强（edit/search/tree/分页读取）
- Screen 增强（多显示器列表）
- 权限管理器（规则匹配、风险检查）
- 审计日志（记录/查询/导出）
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.event_bus import EventBus
from src.core.events import EventType, ToolCallEvent, ToolResultEvent
from src.permissions.audit import AuditLogger, AuditEntry
from src.permissions.manager import (
    ConfirmPolicy,
    PermissionManager,
    PermissionRequest,
    PermissionRule,
    RiskLevel,
)
from src.tools.base import ToolResultStatus
from src.tools.file import FileTool
from src.tools.registry import ToolRegistry, create_default_registry
from src.tools.screen import ScreenTool
from src.tools.shell import ShellTool

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
# 工具注册器重构测试
# =====================================================================

def test_registry_config_load():
    """测试配置驱动的工具注册。"""
    print("\n🧪 测试工具注册器 - 配置加载")

    registry = create_default_registry()
    tools = registry.list_tools()
    check("加载 3 个工具", len(tools) == 3, f"实际 {len(tools)} 个")

    # 验证配置元数据
    check("shell 配置存在", bool(registry.get_tool_config("shell")))
    check("file 配置存在", bool(registry.get_tool_config("file")))
    check("screen 配置存在", bool(registry.get_tool_config("screen")))


def test_registry_risk_query():
    """测试按风险等级查询。"""
    print("\n🧪 测试工具注册器 - 风险等级查询")

    registry = create_default_registry()

    check("shell 风险等级 = high", registry.get_tool_risk_level("shell") == "high")
    check("file 风险等级 = medium", registry.get_tool_risk_level("file") == "medium")
    check("screen 风险等级 = low", registry.get_tool_risk_level("screen") == "low")

    high_tools = registry.find_by_risk_level("high")
    check("高危工具 = 1 (shell)", len(high_tools) == 1)

    low_tools = registry.find_by_risk_level("low")
    check("低危工具 = 1 (screen)", len(low_tools) == 1)


def test_registry_category_query():
    """测试按分类查询。"""
    print("\n🧪 测试工具注册器 - 分类查询")

    registry = create_default_registry()

    system_tools = registry.find_by_category("system")
    check("system 分类 = 1 (shell)", len(system_tools) == 1)

    fs_tools = registry.find_by_category("filesystem")
    check("filesystem 分类 = 1 (file)", len(fs_tools) == 1)

    visual_tools = registry.find_by_category("visual")
    check("visual 分类 = 1 (screen)", len(visual_tools) == 1)


def test_registry_unregister():
    """测试注销工具。"""
    print("\n🧪 测试工具注册器 - 注销")

    registry = create_default_registry()
    check("注销前 3 个工具", len(registry.list_tools()) == 3)

    result = registry.unregister("shell")
    check("注销 shell 成功", result is True)
    check("注销后 2 个工具", len(registry.list_tools()) == 2)
    check("shell 已不存在", registry.get_tool("shell") is None)
    check("shell_run 已不可解析", registry.resolve_function_name("shell_run") is None)

    result = registry.unregister("nonexistent")
    check("注销不存在工具返回 False", result is False)


def test_registry_global_settings():
    """测试全局设置。"""
    print("\n🧪 测试工具注册器 - 全局设置")

    registry = create_default_registry()
    settings = registry.global_settings
    check("有全局设置", bool(settings))
    check("audit_all_calls = true", settings.get("audit_all_calls") is True)
    check("confirmation_for_high_risk = true", settings.get("confirmation_for_high_risk") is True)


# =====================================================================
# Shell 增强测试
# =====================================================================

async def test_shell_blacklist_config():
    """测试 Shell 黑名单配置化。"""
    print("\n🧪 测试 Shell 工具 - 黑名单配置化")

    # 自定义黑名单
    shell = ShellTool(blacklist=["test-block", "another-block"])

    result = await shell.safe_execute("run", {"command": "test-block something"})
    check("自定义黑名单拦截", result.status == ToolResultStatus.DENIED)

    result = await shell.safe_execute("run", {"command": "echo safe"})
    check("非黑名单通过", result.is_success)


async def test_shell_whitelist_mode():
    """测试 Shell 白名单模式。"""
    print("\n🧪 测试 Shell 工具 - 白名单模式")

    shell = ShellTool(
        whitelist=["echo", "get-date", "get-process"],
        whitelist_mode=True,
    )

    result = await shell.safe_execute("run", {"command": "echo hello"})
    check("白名单命令通过", result.is_success, result.error)

    result = await shell.safe_execute("run", {"command": "Remove-Item test.txt"})
    check("非白名单命令拦截", result.status == ToolResultStatus.DENIED)


async def test_shell_working_directory():
    """测试 Shell 工作目录。"""
    print("\n🧪 测试 Shell 工具 - 工作目录")

    with tempfile.TemporaryDirectory() as tmpdir:
        shell = ShellTool(working_directory=tmpdir)

        result = await shell.safe_execute("run", {"command": "(Get-Location).Path"})
        check("工作目录正确", tmpdir.replace("/", "\\") in result.output or tmpdir in result.output,
              result.output[:200])

        # 参数级别的 working_dir 覆盖
        result = await shell.safe_execute("run", {
            "command": "(Get-Location).Path",
            "working_dir": tmpdir,
        })
        check("参数工作目录生效", tmpdir.replace("/", "\\") in result.output or tmpdir in result.output)

    # 不存在的工作目录
    shell_bad = ShellTool()
    result = await shell_bad.safe_execute("run", {
        "command": "echo test",
        "working_dir": "C:\\nonexistent_dir_12345",
    })
    check("不存在工作目录报错", not result.is_success)


async def test_shell_env_vars():
    """测试 Shell 环境变量注入。"""
    print("\n🧪 测试 Shell 工具 - 环境变量注入")

    shell = ShellTool(env_vars={"WINCLAW_TEST_VAR": "hello_winclaw"})

    result = await shell.safe_execute("run", {
        "command": "echo $env:WINCLAW_TEST_VAR",
    })
    check("环境变量注入生效", "hello_winclaw" in result.output, result.output[:200])


# =====================================================================
# File 增强测试
# =====================================================================

async def test_file_edit():
    """测试 File 行级编辑。"""
    print("\n🧪 测试 File 工具 - 行级编辑")

    file_tool = FileTool()

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = str(Path(tmpdir) / "edit_test.txt")

        # 创建测试文件
        await file_tool.safe_execute("write", {
            "path": test_file,
            "content": "第一行\n第二行\n第三行\n第四行\n第五行\n",
        })

        # 替换第2-3行
        result = await file_tool.safe_execute("edit", {
            "path": test_file,
            "start_line": 2,
            "end_line": 3,
            "new_content": "新的第二行\n新的第三行\n",
        })
        check("编辑成功", result.is_success, result.error)

        read_result = await file_tool.safe_execute("read", {"path": test_file})
        check("替换内容正确", "新的第二行" in read_result.output)
        check("保留第一行", "第一行" in read_result.output)
        check("保留第四行", "第四行" in read_result.output)

        # 删除第1行（new_content 为空）
        result = await file_tool.safe_execute("edit", {
            "path": test_file,
            "start_line": 1,
            "end_line": 1,
            "new_content": "",
        })
        check("删除行成功", result.is_success, result.error)

        read_result = await file_tool.safe_execute("read", {"path": test_file})
        check("删除后第一行是新的第二行", "新的第二行" in read_result.output.split("\n")[0])


async def test_file_search():
    """测试 File 文件内搜索。"""
    print("\n🧪 测试 File 工具 - 搜索")

    file_tool = FileTool()

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = str(Path(tmpdir) / "search_test.txt")

        content = "\n".join([
            "Hello World",
            "hello python",
            "HELLO WINCLAW",
            "nothing here",
            "hello again",
        ])
        await file_tool.safe_execute("write", {"path": test_file, "content": content})

        # 搜索（大小写不敏感）
        result = await file_tool.safe_execute("search", {
            "path": test_file,
            "pattern": "hello",
        })
        check("搜索成功", result.is_success, result.error)
        check("搜索结果 = 4 处", result.data.get("matches") == 4,
              str(result.data.get("matches")))

        # 搜索正则
        result = await file_tool.safe_execute("search", {
            "path": test_file,
            "pattern": "^hello",
        })
        check("正则搜索成功", result.is_success)
        check("正则匹配 ≥ 2", result.data.get("matches", 0) >= 2,
              str(result.data.get("matches")))

        # 空模式
        result = await file_tool.safe_execute("search", {
            "path": test_file,
            "pattern": "",
        })
        check("空模式报错", not result.is_success)


async def test_file_tree():
    """测试 File 目录树。"""
    print("\n🧪 测试 File 工具 - 目录树")

    file_tool = FileTool()

    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建目录结构
        (Path(tmpdir) / "subdir1").mkdir()
        (Path(tmpdir) / "subdir1" / "file1.txt").write_text("test")
        (Path(tmpdir) / "subdir2").mkdir()
        (Path(tmpdir) / "subdir2" / "file2.txt").write_text("test")
        (Path(tmpdir) / "root.txt").write_text("root content")

        result = await file_tool.safe_execute("tree", {"path": tmpdir})
        check("目录树成功", result.is_success, result.error)
        check("包含 subdir1", "subdir1" in result.output)
        check("包含 file1.txt", "file1.txt" in result.output)
        check("包含 root.txt", "root.txt" in result.output)
        check("有树形符号", "├──" in result.output or "└──" in result.output)

        # 深度限制
        result = await file_tool.safe_execute("tree", {
            "path": tmpdir,
            "max_depth": 1,
        })
        check("深度限制生效", result.is_success)


async def test_file_paged_read():
    """测试 File 分页读取。"""
    print("\n🧪 测试 File 工具 - 分页读取")

    file_tool = FileTool()

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = str(Path(tmpdir) / "paged.txt")

        # 创建多行文件
        lines = [f"Line {i}: content here" for i in range(1, 101)]
        await file_tool.safe_execute("write", {
            "path": test_file,
            "content": "\n".join(lines) + "\n",
        })

        # 读取前10行
        result = await file_tool.safe_execute("read", {
            "path": test_file,
            "start_line": 1,
            "end_line": 10,
        })
        check("分页读取成功", result.is_success, result.error)
        check("包含行范围头", "[行 1-10" in result.output)
        check("包含 Line 1", "Line 1:" in result.output)
        check("不包含 Line 11", "Line 11:" not in result.output)

        # 读取中间部分
        result = await file_tool.safe_execute("read", {
            "path": test_file,
            "start_line": 50,
            "end_line": 55,
        })
        check("中间读取成功", result.is_success)
        check("包含 Line 50", "Line 50:" in result.output)


async def test_file_denied_extension():
    """测试 File 扩展名过滤。"""
    print("\n🧪 测试 File 工具 - 扩展名过滤")

    file_tool = FileTool(denied_extensions=[".exe", ".dll"])

    with tempfile.TemporaryDirectory() as tmpdir:
        exe_path = str(Path(tmpdir) / "test.exe")
        Path(exe_path).write_text("fake exe")

        result = await file_tool.safe_execute("read", {"path": exe_path})
        check("禁止读取 .exe", result.status == ToolResultStatus.DENIED, result.error)

        # 写入也被禁止
        result = await file_tool.safe_execute("write", {
            "path": str(Path(tmpdir) / "new.dll"),
            "content": "test",
        })
        check("禁止写入 .dll", result.status == ToolResultStatus.DENIED)


# =====================================================================
# Screen 增强测试
# =====================================================================

async def test_screen_list_monitors():
    """测试 Screen 列出显示器。"""
    print("\n🧪 测试 Screen 工具 - 列出显示器")

    screen = ScreenTool()
    result = await screen.safe_execute("list_monitors", {})
    check("列出显示器成功", result.is_success, result.error)
    check("有显示器数量", result.data.get("count", 0) >= 1, str(result.data))
    check("输出包含显示器信息", "显示器" in result.output)


async def test_screen_for_model():
    """测试 Screen for_model 压缩。"""
    print("\n🧪 测试 Screen 工具 - 模型优化压缩")

    screen = ScreenTool(max_width=1920, model_max_width=800)

    # for_model=True（默认）
    result = await screen.safe_execute("capture", {"for_model": True})
    check("模型优化截图成功", result.is_success, result.error)
    check("压缩到 ≤800 宽", result.data.get("width", 9999) <= 800,
          str(result.data.get("width")))

    # for_model=False
    result = await screen.safe_execute("capture", {"for_model": False})
    check("原始截图成功", result.is_success, result.error)
    check("原始宽度 ≤1920", result.data.get("width", 9999) <= 1920)


# =====================================================================
# 权限管理器测试
# =====================================================================

def test_permission_basic():
    """测试权限管理器基础。"""
    print("\n🧪 测试权限管理器 - 基础")

    pm = PermissionManager()

    # 低危操作：自动通过
    result = pm.check(PermissionRequest(
        tool_name="screen",
        action_name="capture",
    ))
    check("低危操作自动通过", result.approved is True)
    check("风险等级 = low", result.risk_level == RiskLevel.LOW)

    # 高危操作：LOG_ONLY 策略
    result = pm.check(PermissionRequest(
        tool_name="shell",
        action_name="run",
    ))
    check("高危操作通过(LOG_ONLY)", result.approved is True)
    check("风险等级 = high", result.risk_level == RiskLevel.HIGH)


def test_permission_rules():
    """测试权限规则管理。"""
    print("\n🧪 测试权限管理器 - 规则管理")

    pm = PermissionManager()
    rules = pm.list_rules()
    check("有默认规则", len(rules) > 0, str(len(rules)))

    # 添加规则
    pm.add_rule(PermissionRule(
        tool_name="custom_tool",
        action_name="dangerous",
        risk_level=RiskLevel.HIGH,
        policy=ConfirmPolicy.REQUIRE_CONFIRM,
    ))
    check("添加规则成功", pm.get_rule("custom_tool", "dangerous") is not None)

    # 移除规则
    result = pm.remove_rule("custom_tool", "dangerous")
    check("移除规则成功", result is True)
    check("规则已移除", pm.get_rule("custom_tool", "dangerous") is None)


def test_permission_wildcard():
    """测试权限通配符规则。"""
    print("\n🧪 测试权限管理器 - 通配符")

    pm = PermissionManager()

    # screen 用通配符 "*" 规则
    result = pm.check(PermissionRequest(
        tool_name="screen",
        action_name="capture_window",
    ))
    check("通配符规则匹配", result.approved is True)
    check("通配符风险等级", result.risk_level == RiskLevel.LOW)


def test_permission_require_confirm():
    """测试需要确认的操作。"""
    print("\n🧪 测试权限管理器 - 确认策略")

    # 高危自动通过 = False
    pm = PermissionManager(high_risk_auto_approve=False)
    pm.add_rule(PermissionRule(
        tool_name="dangerous_tool",
        action_name="delete",
        risk_level=RiskLevel.HIGH,
        policy=ConfirmPolicy.REQUIRE_CONFIRM,
    ))

    result = pm.check(PermissionRequest(
        tool_name="dangerous_tool",
        action_name="delete",
    ))
    check("需确认操作被拒绝", result.approved is False)
    check("需要确认标记", result.requires_confirmation is True)

    # 高危自动通过 = True
    pm2 = PermissionManager(high_risk_auto_approve=True)
    pm2.add_rule(PermissionRule(
        tool_name="dangerous_tool",
        action_name="delete",
        risk_level=RiskLevel.HIGH,
        policy=ConfirmPolicy.REQUIRE_CONFIRM,
    ))

    result2 = pm2.check(PermissionRequest(
        tool_name="dangerous_tool",
        action_name="delete",
    ))
    check("自动通过模式通过", result2.approved is True)


def test_permission_callback():
    """测试确认回调。"""
    print("\n🧪 测试权限管理器 - 确认回调")

    # 回调始终拒绝
    pm = PermissionManager(
        high_risk_auto_approve=False,
        confirm_callback=lambda req: False,
    )
    pm.add_rule(PermissionRule(
        tool_name="test",
        action_name="action",
        risk_level=RiskLevel.HIGH,
        policy=ConfirmPolicy.REQUIRE_CONFIRM,
    ))

    result = pm.check(PermissionRequest(tool_name="test", action_name="action"))
    check("回调拒绝生效", result.approved is False)

    # 回调始终通过
    pm2 = PermissionManager(
        confirm_callback=lambda req: True,
    )
    pm2.add_rule(PermissionRule(
        tool_name="test",
        action_name="action",
        risk_level=RiskLevel.HIGH,
        policy=ConfirmPolicy.REQUIRE_CONFIRM,
    ))

    result2 = pm2.check(PermissionRequest(tool_name="test", action_name="action"))
    check("回调通过生效", result2.approved is True)


def test_permission_stats():
    """测试权限统计。"""
    print("\n🧪 测试权限管理器 - 统计")

    pm = PermissionManager()
    pm.check(PermissionRequest(tool_name="shell", action_name="run"))
    pm.check(PermissionRequest(tool_name="screen", action_name="capture"))

    stats = pm.get_stats()
    check("检查次数 = 2", stats["total_checks"] == 2)
    check("高危次数 = 1", stats["high_risk"] == 1)

    pm.reset_stats()
    check("重置后检查次数 = 0", pm.check_count == 0)


# =====================================================================
# 审计日志测试
# =====================================================================

def test_audit_basic():
    """测试审计日志基础。"""
    print("\n🧪 测试审计日志 - 基础")

    audit = AuditLogger(write_to_file=False)

    # 手动记录
    audit.log_call("shell", "run", {"command": "dir"}, risk_level="high")
    audit.log_result("shell", "run", "success", output="file list...", duration_ms=150)

    check("总调用 = 1", audit.total_calls == 1)
    check("总错误 = 0", audit.total_errors == 0)

    recent = audit.get_recent(10)
    check("有记录", len(recent) == 1)
    check("工具名正确", recent[0].tool_name == "shell")
    check("动作名正确", recent[0].action_name == "run")
    check("状态正确", recent[0].status == "success")
    check("耗时正确", recent[0].duration_ms == 150)
    check("已完成", recent[0].completed is True)


def test_audit_errors():
    """测试审计日志错误记录。"""
    print("\n🧪 测试审计日志 - 错误")

    audit = AuditLogger(write_to_file=False)

    audit.log_call("file", "write", {"path": "test.txt"})
    audit.log_result("file", "write", "error", error="权限不足")

    audit.log_call("shell", "run", {"command": "shutdown"})
    audit.log_result("shell", "run", "denied", error="安全策略拦截")

    check("总错误 = 1", audit.total_errors == 1)
    check("总拒绝 = 1", audit.total_denied == 1)

    errors = audit.get_errors()
    check("错误记录 = 2", len(errors) == 2)


def test_audit_query():
    """测试审计日志查询。"""
    print("\n🧪 测试审计日志 - 查询")

    audit = AuditLogger(write_to_file=False)

    for i in range(5):
        audit.log_call("shell", "run", {"command": f"cmd{i}"}, session_id="s1")
        audit.log_result("shell", "run", "success", session_id="s1")

    for i in range(3):
        audit.log_call("file", "read", {"path": f"f{i}"}, session_id="s2")
        audit.log_result("file", "read", "success", session_id="s2")

    by_tool = audit.get_by_tool("shell")
    check("按工具查询 = 5", len(by_tool) == 5)

    by_session = audit.get_by_session("s1")
    check("按会话查询 = 5", len(by_session) == 5)

    recent = audit.get_recent(3)
    check("最近 3 条", len(recent) == 3)


def test_audit_export():
    """测试审计日志导出。"""
    print("\n🧪 测试审计日志 - 导出")

    audit = AuditLogger(write_to_file=False)

    audit.log_call("shell", "run", {"command": "dir"})
    audit.log_result("shell", "run", "success", output="files", duration_ms=50)

    with tempfile.TemporaryDirectory() as tmpdir:
        export_path = Path(tmpdir) / "audit_export.json"
        count = audit.export_json(export_path)
        check("导出 1 条", count == 1)
        check("导出文件存在", export_path.exists())

        with open(export_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        check("JSON 格式正确", isinstance(data, list))
        check("JSON 内容正确", data[0]["tool_name"] == "shell")


async def test_audit_eventbus_integration():
    """测试审计日志与事件总线集成。"""
    print("\n🧪 测试审计日志 - 事件总线集成")

    bus = EventBus()
    audit = AuditLogger(write_to_file=False)
    audit.connect(bus)

    # 模拟事件发布
    await bus.emit(EventType.TOOL_CALL, ToolCallEvent(
        tool_name="shell",
        action_name="run",
        arguments={"command": "dir"},
        function_name="shell_run",
        session_id="test-session",
    ))

    await bus.emit(EventType.TOOL_RESULT, ToolResultEvent(
        tool_name="shell",
        action_name="run",
        status="success",
        output="directory listing...",
        duration_ms=100,
        session_id="test-session",
    ))

    check("事件记录总调用 = 1", audit.total_calls == 1)
    recent = audit.get_recent(1)
    check("有事件记录", len(recent) == 1)
    check("事件记录状态", recent[0].status == "success")
    check("事件记录耗时", recent[0].duration_ms == 100)


def test_audit_clear():
    """测试审计日志清空。"""
    print("\n🧪 测试审计日志 - 清空")

    audit = AuditLogger(write_to_file=False)
    audit.log_call("shell", "run")
    audit.log_result("shell", "run", "success")

    check("清空前有记录", audit.total_calls == 1)
    audit.clear()
    check("清空后无记录", audit.total_calls == 0)
    check("清空后无条目", len(audit.get_recent(100)) == 0)


def test_audit_stats():
    """测试审计日志统计。"""
    print("\n🧪 测试审计日志 - 统计")

    audit = AuditLogger(write_to_file=False)
    audit.log_call("shell", "run")
    audit.log_result("shell", "run", "success")
    audit.log_call("file", "write")
    audit.log_result("file", "write", "error", error="fail")

    stats = audit.get_stats()
    check("统计总调用 = 2", stats["total_calls"] == 2)
    check("统计总错误 = 1", stats["total_errors"] == 1)
    check("内存条目 = 2", stats["entries_in_memory"] == 2)


# =====================================================================
# 主入口
# =====================================================================

async def main():
    print("=" * 60)
    print("  WinClaw Sprint 1.3 集成验收测试")
    print("=" * 60)

    # 工具注册器
    test_registry_config_load()
    test_registry_risk_query()
    test_registry_category_query()
    test_registry_unregister()
    test_registry_global_settings()

    # Shell 增强
    await test_shell_blacklist_config()
    await test_shell_whitelist_mode()
    await test_shell_working_directory()
    await test_shell_env_vars()

    # File 增强
    await test_file_edit()
    await test_file_search()
    await test_file_tree()
    await test_file_paged_read()
    await test_file_denied_extension()

    # Screen 增强
    await test_screen_list_monitors()
    await test_screen_for_model()

    # 权限管理器
    test_permission_basic()
    test_permission_rules()
    test_permission_wildcard()
    test_permission_require_confirm()
    test_permission_callback()
    test_permission_stats()

    # 审计日志
    test_audit_basic()
    test_audit_errors()
    test_audit_query()
    test_audit_export()
    await test_audit_eventbus_integration()
    test_audit_clear()
    test_audit_stats()

    print("\n" + "=" * 60)
    print(f"  结果: ✅ {passed} 通过  ❌ {failed} 失败")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
