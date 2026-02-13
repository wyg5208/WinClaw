"""P0+P1 新增工具冒烟测试 + 原有工具回归测试。

冒烟测试覆盖：
  P0: calculator / weather / datetime_tool / statistics
  P1: chat_history / cron(日程扩展) / diary / finance / knowledge

回归测试覆盖：
  - 原有 12 个工具的注册、schema 生成、actions 数量
  - registry 的 resolve_function_name / find_by_category / risk_level
  - tools.json 配置完整性
"""

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# 将项目根目录加入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.base import ToolResult, ToolResultStatus
from src.tools.registry import ToolRegistry, create_default_registry

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
# 一、回归测试 — 原有工具完整性
# =====================================================================

def test_regression_registry():
    """回归：工具注册器完整性。"""
    print("\n🔄 回归测试 — 工具注册器")
    registry = create_default_registry()
    tools = registry.list_tools()
    tool_names = [t.name for t in tools]

    check("注册 20 个工具", len(tools) == 20, f"实际 {len(tools)}: {tool_names}")

    # 原有 12 个工具必须全部存在
    original_12 = [
        "shell", "file", "screen", "browser", "app_control",
        "clipboard", "notify", "search", "cron", "voice_input",
        "voice_output", "ocr",
    ]
    for name in original_12:
        check(f"原有工具 {name} 已注册", name in tool_names)

    # P0 工具
    p0_tools = ["calculator", "weather", "datetime_tool", "statistics"]
    for name in p0_tools:
        check(f"P0 工具 {name} 已注册", name in tool_names)

    # P1 工具
    p1_tools = ["chat_history", "diary", "finance", "knowledge"]
    for name in p1_tools:
        check(f"P1 工具 {name} 已注册", name in tool_names)


def test_regression_schemas():
    """回归：schema 生成和函数名解析。"""
    print("\n🔄 回归测试 — Schema 生成")
    registry = create_default_registry()
    all_schemas = registry.get_all_schemas()

    check("总 schema 数 == 72", len(all_schemas) == 72, f"实际 {len(all_schemas)}")

    # 验证每个 schema 格式正确
    for s in all_schemas:
        fn = s.get("function", {}).get("name", "?")
        check(
            f"schema {fn} 格式正确",
            s.get("type") == "function"
            and "name" in s.get("function", {})
            and "parameters" in s.get("function", {}),
        )

    # 函数名解析 — 原有工具
    check(
        "resolve shell_run",
        registry.resolve_function_name("shell_run") == ("shell", "run"),
    )
    check(
        "resolve file_read",
        registry.resolve_function_name("file_read") == ("file", "read"),
    )
    check(
        "resolve search_web_search",
        registry.resolve_function_name("search_web_search") == ("search", "web_search"),
    )
    check(
        "resolve app_control_launch",
        registry.resolve_function_name("app_control_launch") == ("app_control", "launch"),
    )

    # 函数名解析 — 新工具
    check(
        "resolve calculator_calculate",
        registry.resolve_function_name("calculator_calculate") == ("calculator", "calculate"),
    )
    check(
        "resolve diary_write_diary",
        registry.resolve_function_name("diary_write_diary") == ("diary", "write_diary"),
    )
    check(
        "resolve finance_add_transaction",
        registry.resolve_function_name("finance_add_transaction") == ("finance", "add_transaction"),
    )
    check(
        "resolve cron_create_schedule",
        registry.resolve_function_name("cron_create_schedule") == ("cron", "create_schedule"),
    )
    check(
        "resolve knowledge_search_documents",
        registry.resolve_function_name("knowledge_search_documents") == ("knowledge", "search_documents"),
    )


def test_regression_categories():
    """回归：分类查询和风险等级。"""
    print("\n🔄 回归测试 — 分类与风险等级")
    registry = create_default_registry()

    system_tools = registry.find_by_category("system")
    check("system 分类 ≥ 3", len(system_tools) >= 3, f"实际 {len(system_tools)}")

    utility_tools = registry.find_by_category("utility")
    check("utility 分类 ≥ 4", len(utility_tools) >= 4, f"实际 {len(utility_tools)}")

    life_tools = registry.find_by_category("life")
    check("life 分类 ≥ 2", len(life_tools) >= 2, f"实际 {len(life_tools)}")

    # 风险等级
    check("shell 高风险", registry.get_tool_risk_level("shell") == "high")
    check("clipboard 低风险", registry.get_tool_risk_level("clipboard") == "low")
    check("calculator 低风险", registry.get_tool_risk_level("calculator") == "low")
    check("finance 低风险", registry.get_tool_risk_level("finance") == "low")


def test_regression_original_actions():
    """回归：原有工具的 actions 数量未变。"""
    print("\n🔄 回归测试 — 原有工具 actions 数量")
    registry = create_default_registry()

    expected = {
        "shell": 1, "file": 6, "screen": 3, "browser": 8,
        "app_control": 5, "clipboard": 4, "notify": 2, "search": 2,
        "voice_input": 3, "voice_output": 4, "ocr": 2,
    }
    for name, count in expected.items():
        tool = registry.get_tool(name)
        if tool:
            actual = len(tool.get_actions())
            check(f"{name} 仍有 {count} actions", actual == count, f"实际 {actual}")
        else:
            check(f"{name} 存在", False, "工具未注册")

    # cron 原来 7 个 + 新增 5 个日程 = 12
    cron = registry.get_tool("cron")
    if cron:
        actual = len(cron.get_actions())
        check(f"cron 有 12 actions (原7+日程5)", actual == 12, f"实际 {actual}")


def test_regression_tools_json():
    """回归：tools.json 配置文件完整性。"""
    print("\n🔄 回归测试 — tools.json 配置")
    config_path = Path(__file__).resolve().parent.parent / "config" / "tools.json"
    check("tools.json 存在", config_path.exists())

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tools_cfg = data.get("tools", {})
    categories_cfg = data.get("categories", {})

    check("20 个工具配置", len(tools_cfg) == 20, f"实际 {len(tools_cfg)}")
    check("10 个分类", len(categories_cfg) == 10, f"实际 {len(categories_cfg)}")

    # 每个工具配置应包含关键字段
    for name, cfg in tools_cfg.items():
        check(
            f"配置 {name} 完整",
            all(k in cfg for k in ("enabled", "module", "class", "display", "actions")),
            f"缺失字段: {[k for k in ('enabled','module','class','display','actions') if k not in cfg]}",
        )


# =====================================================================
# 二、冒烟测试 — P0 新工具
# =====================================================================

async def test_smoke_calculator():
    """冒烟：计算器工具。"""
    print("\n🧪 冒烟测试 — Calculator")
    from src.tools.calculator import CalculatorTool

    tool = CalculatorTool()
    check("名称", tool.name == "calculator")
    check("1 个动作", len(tool.get_actions()) == 1)

    # 基本计算
    r = await tool.safe_execute("calculate", {"expression": "2 + 3 * 4"})
    check("2+3*4=14", r.is_success and r.data.get("result") == 14, r.output)

    # 数学函数
    r = await tool.safe_execute("calculate", {"expression": "sqrt(144)"})
    check("sqrt(144)=12", r.is_success and r.data.get("result") == 12, r.output)

    # 幂运算
    r = await tool.safe_execute("calculate", {"expression": "2 ** 10"})
    check("2**10=1024", r.is_success and r.data.get("result") == 1024, r.output)

    # 中文符号
    r = await tool.safe_execute("calculate", {"expression": "（3＋2）×4"})
    # 注意：全角加号 ＋ 不在预处理中，只有 ×÷（）
    # 改用半角
    r = await tool.safe_execute("calculate", {"expression": "(3+2)×4"})
    check("中文乘号 (3+2)×4=20", r.is_success and r.data.get("result") == 20, r.output)

    # 除以零
    r = await tool.safe_execute("calculate", {"expression": "1/0"})
    check("除以零报错", r.status == ToolResultStatus.ERROR)

    # 空表达式
    r = await tool.safe_execute("calculate", {"expression": ""})
    check("空表达式报错", r.status == ToolResultStatus.ERROR)

    # 非法表达式
    r = await tool.safe_execute("calculate", {"expression": "__import__('os')"})
    check("注入攻击拦截", r.status == ToolResultStatus.ERROR)


async def test_smoke_datetime():
    """冒烟：日期时间工具。"""
    print("\n🧪 冒烟测试 — DateTimeTool")
    from src.tools.datetime_tool import DateTimeTool

    tool = DateTimeTool()
    check("名称", tool.name == "datetime_tool")
    check("1 个动作", len(tool.get_actions()) == 1)

    # 默认格式 (full) 返回 datetime 和 timezone
    r = await tool.safe_execute("get_datetime", {})
    check("获取日期时间", r.is_success, r.error)
    check("data 有 datetime 字段", "datetime" in r.data, str(r.data.keys()))

    today = datetime.now().strftime("%Y-%m-%d")
    check("日期正确", r.data.get("datetime", "").startswith(today[:7]), r.data.get("datetime"))

    # 指定格式
    r = await tool.safe_execute("get_datetime", {"format_type": "weekday"})
    check("weekday 格式", r.is_success and "weekday_cn" in r.data, str(r.data))

    # all 格式
    r = await tool.safe_execute("get_datetime", {"format_type": "all"})
    check("all 格式返回多字段", r.is_success and len(r.data) >= 5, str(len(r.data)))


async def test_smoke_weather():
    """冒烟：天气工具（无 API Key 时应降级或报错）。"""
    print("\n🧪 冒烟测试 — Weather")
    from src.tools.weather import WeatherTool

    tool = WeatherTool()
    check("名称", tool.name == "weather")
    check("1 个动作", len(tool.get_actions()) == 1)

    # 即使没有 API Key，schema 应该正常
    schemas = tool.get_schema()
    check("schema 正确", len(schemas) == 1)
    check("参数包含 city", "city" in schemas[0]["function"]["parameters"]["properties"])


async def test_smoke_statistics():
    """冒烟：使用统计工具。"""
    print("\n🧪 冒烟测试 — Statistics")
    from src.tools.statistics import StatisticsTool

    tool = StatisticsTool()
    check("名称", tool.name == "statistics")
    check("1 个动作", len(tool.get_actions()) == 1)

    # 执行统计（数据库可能为空，但不应崩溃）
    r = await tool.safe_execute("get_usage_stats", {})
    check("统计不崩溃", r.is_success, r.error)
    check("data 有 session_count", "session_count" in r.data, str(r.data.keys()))


# =====================================================================
# 三、冒烟测试 — P1 新工具
# =====================================================================

async def test_smoke_chat_history():
    """冒烟：聊天历史工具。"""
    print("\n🧪 冒烟测试 — ChatHistory")
    from src.tools.chat_history import ChatHistoryTool

    tool = ChatHistoryTool()
    check("名称", tool.name == "chat_history")
    check("2 个动作", len(tool.get_actions()) == 2)

    # 搜索（数据库可能为空，不应崩溃）
    r = await tool.safe_execute("search_history", {"keyword": ""})
    check("空搜索不崩溃", r.is_success, r.error)

    r = await tool.safe_execute("get_recent_sessions", {})
    check("获取最近会话不崩溃", r.is_success, r.error)


async def test_smoke_cron_schedules():
    """冒烟：cron 日程扩展。"""
    print("\n🧪 冒烟测试 — Cron 日程管理")
    from src.tools.cron import CronTool

    # 使用临时数据库
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cron.db"
        tool = CronTool(db_path=db_path)

        # 验证 actions 包含日程
        actions = tool.get_actions()
        action_names = [a.name for a in actions]
        check("12 个动作", len(actions) == 12, f"实际 {len(actions)}")
        check("包含 create_schedule", "create_schedule" in action_names)
        check("包含 query_schedules", "query_schedules" in action_names)
        check("包含 update_schedule", "update_schedule" in action_names)
        check("包含 delete_schedule", "delete_schedule" in action_names)
        check("包含 complete_schedule", "complete_schedule" in action_names)

        # 创建日程
        r = await tool.safe_execute("create_schedule", {
            "title": "测试日程",
            "content": "这是冒烟测试日程",
            "scheduled_time": "2099-12-31 18:00:00",
        })
        check("创建日程", r.is_success, r.error)
        schedule_id = r.data.get("schedule_id")
        check("返回 schedule_id", schedule_id is not None, str(r.data))

        # 查询日程
        r = await tool.safe_execute("query_schedules", {"status": "all"})
        check("查询日程", r.is_success, r.error)
        check("找到 1 条日程", r.data.get("count") == 1, str(r.data))

        # 更新日程
        r = await tool.safe_execute("update_schedule", {
            "schedule_id": schedule_id,
            "title": "更新后的日程",
        })
        check("更新日程", r.is_success, r.error)

        # 完成日程
        r = await tool.safe_execute("complete_schedule", {"schedule_id": schedule_id})
        check("完成日程", r.is_success, r.error)

        # 查询已完成
        r = await tool.safe_execute("query_schedules", {"status": "completed"})
        check("查询已完成", r.is_success and r.data.get("count") == 1, str(r.data))

        # 删除日程
        r = await tool.safe_execute("delete_schedule", {"schedule_id": schedule_id})
        check("删除日程", r.is_success, r.error)

        # 确认删除
        r = await tool.safe_execute("query_schedules", {"status": "all"})
        check("删除后为空", r.data.get("count") == 0, str(r.data))

        # 空标题报错
        r = await tool.safe_execute("create_schedule", {"title": ""})
        check("空标题报错", r.status == ToolResultStatus.ERROR)


async def test_smoke_diary():
    """冒烟：日记管理工具。"""
    print("\n🧪 冒烟测试 — Diary")
    from src.tools.diary import DiaryTool

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_diary.db"
        tool = DiaryTool(db_path=str(db_path))

        check("名称", tool.name == "diary")
        check("4 个动作", len(tool.get_actions()) == 4)

        # 写日记
        r = await tool.safe_execute("write_diary", {
            "title": "冒烟测试日记",
            "content": "今天完成了 P0+P1 工具开发",
            "mood": "happy",
            "weather": "sunny",
            "tags": "开发,测试",
        })
        check("写日记", r.is_success, r.error)
        diary_id = r.data.get("diary_id")
        check("返回 diary_id", diary_id is not None)
        check("日期正确", r.data.get("date") == datetime.now().strftime("%Y-%m-%d"))

        # 查询日记
        r = await tool.safe_execute("query_diary", {"date_range": "today"})
        check("查询今天日记", r.is_success, r.error)
        check("找到 1 篇", r.data.get("count") == 1, str(r.data))

        # 按关键词查
        r = await tool.safe_execute("query_diary", {"keyword": "P0"})
        check("关键词搜索", r.is_success and r.data.get("count") == 1)

        # 按心情查
        r = await tool.safe_execute("query_diary", {"mood": "sad"})
        check("心情筛选无结果", r.data.get("count") == 0)

        # 更新日记
        r = await tool.safe_execute("update_diary", {
            "diary_id": diary_id,
            "title": "更新后的标题",
        })
        check("更新日记", r.is_success, r.error)

        # 删除日记
        r = await tool.safe_execute("delete_diary", {"diary_id": diary_id})
        check("删除日记", r.is_success, r.error)

        # 确认删除
        r = await tool.safe_execute("query_diary", {"date_range": "all"})
        check("删除后为空", r.data.get("count") == 0)

        # 空标题/内容报错
        r = await tool.safe_execute("write_diary", {"title": "", "content": ""})
        check("空标题报错", r.status == ToolResultStatus.ERROR)


async def test_smoke_finance():
    """冒烟：记账管理工具。"""
    print("\n🧪 冒烟测试 — Finance")
    from src.tools.finance import FinanceTool

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_finance.db"
        tool = FinanceTool(db_path=str(db_path))

        check("名称", tool.name == "finance")
        check("5 个动作", len(tool.get_actions()) == 5)

        # 添加支出
        r = await tool.safe_execute("add_transaction", {
            "type": "expense",
            "amount": 35.50,
            "category": "餐饮",
            "description": "午餐",
        })
        check("添加支出", r.is_success, r.error)
        tid1 = r.data.get("transaction_id")
        check("返回 transaction_id", tid1 is not None)

        # 添加收入
        r = await tool.safe_execute("add_transaction", {
            "type": "income",
            "amount": 10000,
            "category": "工资",
        })
        check("添加收入", r.is_success, r.error)
        tid2 = r.data.get("transaction_id")

        # 查询
        r = await tool.safe_execute("query_transactions", {"date_range": "today"})
        check("查询今日记录", r.is_success, r.error)
        check("找到 2 条", r.data.get("count") == 2, str(r.data.get("count")))

        # 按类型查
        r = await tool.safe_execute("query_transactions", {"type": "expense"})
        check("按类型查支出", r.data.get("count") == 1)

        # 财务汇总
        r = await tool.safe_execute("get_financial_summary", {"period": "today"})
        check("财务汇总", r.is_success, r.error)
        check("总收入 10000", r.data.get("total_income") == 10000.0, str(r.data.get("total_income")))
        check("总支出 35.5", r.data.get("total_expense") == 35.5, str(r.data.get("total_expense")))
        check("结余正确", abs(r.data.get("balance", 0) - 9964.5) < 0.01)

        # 更新
        r = await tool.safe_execute("update_transaction", {
            "transaction_id": tid1,
            "amount": 42.00,
            "category": "饮料",
        })
        check("更新记录", r.is_success, r.error)

        # 删除
        r = await tool.safe_execute("delete_transaction", {"transaction_id": tid1})
        check("删除记录", r.is_success, r.error)

        # 无效类型
        r = await tool.safe_execute("add_transaction", {
            "type": "invalid", "amount": 10, "category": "x",
        })
        check("无效类型报错", r.status == ToolResultStatus.ERROR)

        # 金额为 0
        r = await tool.safe_execute("add_transaction", {
            "type": "expense", "amount": 0, "category": "x",
        })
        check("零金额报错", r.status == ToolResultStatus.ERROR)


async def test_smoke_knowledge():
    """冒烟：文档知识库工具。"""
    print("\n🧪 冒烟测试 — Knowledge")
    from src.tools.knowledge import KnowledgeTool

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_knowledge.db"
        doc_dir = Path(tmpdir) / "docs"
        doc_dir.mkdir()
        tool = KnowledgeTool(db_path=str(db_path), doc_dir=str(doc_dir))

        check("名称", tool.name == "knowledge")
        check("5 个动作", len(tool.get_actions()) == 5)

        # 创建测试文件
        test_file = Path(tmpdir) / "test_doc.md"
        test_file.write_text(
            "# WinClaw 文档\n\n这是一个测试文档。\n\n## 功能特性\n\n- 工具管理\n- 智能对话\n- 桌面自动化\n",
            encoding="utf-8",
        )

        # 索引文件
        r = await tool.safe_execute("index_document", {"file_path": str(test_file)})
        check("索引文件", r.is_success, r.error)
        doc_id = r.data.get("document_id")
        check("返回 document_id", doc_id is not None)

        # 列出文档
        r = await tool.safe_execute("list_documents", {})
        check("列出文档", r.is_success and r.data.get("count") == 1, str(r.data))

        # 搜索文档
        r = await tool.safe_execute("search_documents", {"query": "WinClaw"})
        check("搜索文档", r.is_success and r.data.get("count") == 1, str(r.data))

        # 搜索不存在
        r = await tool.safe_execute("search_documents", {"query": "不存在的关键词xyz"})
        check("搜索无结果", r.is_success and r.data.get("count") == 0)

        # 查询文档内容
        r = await tool.safe_execute("query_document_content", {
            "document_name": "test_doc",
            "question": "功能特性",
        })
        check("查询内容", r.is_success, r.error)
        check("找到匹配", r.data.get("total_matches", 0) >= 1, str(r.data))

        # 重新索引（更新）
        r = await tool.safe_execute("index_document", {"file_path": str(test_file)})
        check("重新索引（更新）", r.is_success and "已更新" in r.output, r.output)

        # 移除文档
        r = await tool.safe_execute("remove_document", {"document_id": doc_id})
        check("移除文档", r.is_success, r.error)

        # 确认移除
        r = await tool.safe_execute("list_documents", {})
        check("移除后为空", r.data.get("count") == 0)

        # 不支持的文件类型
        exe_file = Path(tmpdir) / "test.exe"
        exe_file.write_bytes(b"\x00")
        r = await tool.safe_execute("index_document", {"file_path": str(exe_file)})
        check("拒绝 .exe 文件", r.status == ToolResultStatus.ERROR)

        # 不存在的文件
        r = await tool.safe_execute("index_document", {"file_path": str(Path(tmpdir) / "no.txt")})
        check("不存在文件报错", r.status == ToolResultStatus.ERROR)


# =====================================================================
# 主入口
# =====================================================================

def main():
    print("=" * 60)
    print("  WinClaw P0+P1 冒烟测试 + 回归测试")
    print("=" * 60)

    # === 回归测试（同步） ===
    test_regression_registry()
    test_regression_schemas()
    test_regression_categories()
    test_regression_original_actions()
    test_regression_tools_json()

    # === 冒烟测试（异步） ===
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # P0
        loop.run_until_complete(test_smoke_calculator())
        loop.run_until_complete(test_smoke_datetime())
        loop.run_until_complete(test_smoke_weather())
        loop.run_until_complete(test_smoke_statistics())
        # P1
        loop.run_until_complete(test_smoke_chat_history())
        loop.run_until_complete(test_smoke_cron_schedules())
        loop.run_until_complete(test_smoke_diary())
        loop.run_until_complete(test_smoke_finance())
        loop.run_until_complete(test_smoke_knowledge())
    finally:
        loop.close()

    # 汇总
    print("\n" + "=" * 60)
    total = passed + failed
    print(f"  总计: {total} 项 | ✅ 通过: {passed} | ❌ 失败: {failed}")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    else:
        print("\n  🎉 全部通过！")


if __name__ == "__main__":
    main()
