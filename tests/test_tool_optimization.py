"""Phase 6 工具调用链路优化 — 单元测试。

覆盖:
1. 意图识别准确率（多场景）
2. Schema 动态优先级标注
3. 单次工具调用数量限制
4. 渐进式工具暴露引擎（分层 / 回退 / 依赖解析）
5. 分级错误反馈
6. 前置校验器
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# 保证项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.prompts import (
    IntentResult,
    INTENT_CATEGORIES,
    INTENT_TOOL_MAPPING,
    INTENT_PRIORITY_MAP,
    detect_intent_with_confidence,
    detect_intent,
    build_system_prompt,
    build_system_prompt_from_intent,
)
from src.core.tool_exposure import (
    annotate_schema_priority,
    ToolExposureEngine,
    _extract_tool_name,
)
from src.core.tool_validator import ToolCallValidator, ValidationResult
from src.tools.base import ToolResult, ToolResultStatus

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
# 1. 意图识别准确率测试
# =====================================================================

def test_intent_recognition():
    """基准场景意图识别测试。"""
    print("\n🧪 意图识别准确率")

    # 场景 1: CSDN 博客 → mcp_task
    r1 = detect_intent_with_confidence("帮我写一篇 CSDN 博客")
    check(
        "场景1: CSDN博客 → mcp_task",
        "mcp_task" in r1.intents,
        f"got intents={r1.intents}",
    )
    check(
        "场景1: 不应包含 document_assembly",
        "document_assembly" not in r1.intents,
        f"got intents={r1.intents}",
    )

    # 场景 2: 天气+文档 → daily_assistant + document_assembly
    r2 = detect_intent_with_confidence("查今天天气写成文档")
    check(
        "场景2: 天气文档 → daily_assistant 或 document_assembly",
        "daily_assistant" in r2.intents or "document_assembly" in r2.intents,
        f"got intents={r2.intents}",
    )

    # 场景 3: 截屏 → system_admin
    r3 = detect_intent_with_confidence("截个屏")
    check(
        "场景3: 截屏 → system_admin",
        "system_admin" in r3.intents,
        f"got intents={r3.intents}",
    )

    # 场景 4: 文件整理 → file_operation
    r4 = detect_intent_with_confidence("帮我整理下载文件夹")
    check(
        "场景4: 文件整理 → file_operation",
        "file_operation" in r4.intents,
        f"got intents={r4.intents}",
    )

    # 场景 5: 多意图组合 → 至少包含 daily_assistant 和 document_assembly
    r5 = detect_intent_with_confidence("帮我查天气然后生成文档再发邮件")
    check(
        "场景5: 多意图 → daily_assistant",
        "daily_assistant" in r5.intents,
        f"got intents={r5.intents}",
    )
    check(
        "场景5: 多意图 → document_assembly 或 email_task",
        "document_assembly" in r5.intents or "email_task" in r5.intents,
        f"got intents={r5.intents}",
    )


def test_intent_confidence():
    """测试置信度计算。"""
    print("\n🧪 意图置信度评估")

    # 单一明确意图 → 高置信度
    r_single = detect_intent_with_confidence("打开浏览器访问网站")
    check(
        "单一意图高置信度 (>=0.5)",
        r_single.confidence >= 0.5,
        f"got confidence={r_single.confidence:.2f}",
    )

    # 无法识别的输入 → 低置信度
    r_unknown = detect_intent_with_confidence("你好呀，今天心情好不好")
    check(
        "无法识别 → 低置信度 (<0.3)",
        r_unknown.confidence < 0.3,
        f"got confidence={r_unknown.confidence:.2f}",
    )

    # 置信度范围 0-1
    check(
        "置信度范围 [0, 1]",
        0.0 <= r_single.confidence <= 1.0 and 0.0 <= r_unknown.confidence <= 1.0,
        f"single={r_single.confidence:.2f}, unknown={r_unknown.confidence:.2f}",
    )


def test_intent_backward_compat():
    """测试向后兼容接口。"""
    print("\n🧪 意图识别向后兼容")

    # detect_intent() 仍然能正常工作
    modules = detect_intent("帮我查天气然后生成文档")
    check(
        "detect_intent 返回 set",
        isinstance(modules, set),
        f"got type={type(modules)}",
    )
    check(
        "detect_intent 包含 assembly",
        "assembly" in modules,
        f"got modules={modules}",
    )

    # build_system_prompt 返回字符串
    prompt = build_system_prompt("写一篇CSDN博客")
    check(
        "build_system_prompt 返回 str",
        isinstance(prompt, str) and len(prompt) > 100,
        f"got len={len(prompt)}",
    )

    # IntentResult 的 prompt_modules 向后兼容
    r = detect_intent_with_confidence("写博客")
    check(
        "IntentResult.prompt_modules 包含 mcp",
        "mcp" in r.prompt_modules,
        f"got prompt_modules={r.prompt_modules}",
    )


# =====================================================================
# 2. Schema 动态优先级标注测试
# =====================================================================

def test_schema_annotation():
    """测试 Schema 标注功能。"""
    print("\n🧪 Schema 动态优先级标注")

    # 构造测试 schema
    schemas = [
        {"type": "function", "function": {"name": "browser_open_url", "description": "打开URL"}},
        {"type": "function", "function": {"name": "browser_use_run_task", "description": "运行浏览器任务"}},
        {"type": "function", "function": {"name": "shell_run", "description": "执行命令"}},
        {"type": "function", "function": {"name": "file_read", "description": "读文件"}},
    ]

    # browser_automation 意图
    intent = IntentResult(
        intents={"browser_automation"},
        confidence=0.9,
        primary_intent="browser_automation",
    )

    annotated = annotate_schema_priority(schemas, intent)

    check(
        "标注不改变数量",
        len(annotated) == len(schemas),
        f"got {len(annotated)} schemas",
    )

    # browser 和 browser_use 应被标注为 [推荐]
    browser_desc = annotated[0]["function"]["description"]
    check(
        "browser → [推荐]",
        browser_desc.startswith("[推荐]"),
        f"got desc={browser_desc}",
    )

    browser_use_desc = annotated[1]["function"]["description"]
    check(
        "browser_use → [推荐]",
        browser_use_desc.startswith("[推荐]"),
        f"got desc={browser_use_desc}",
    )

    # shell 和 file 不应被标注
    shell_desc = annotated[2]["function"]["description"]
    check(
        "shell → 无标注",
        not shell_desc.startswith("[推荐]") and not shell_desc.startswith("[备选]"),
        f"got desc={shell_desc}",
    )


def test_schema_annotation_no_intent():
    """测试无意图时不标注。"""
    print("\n🧪 Schema 标注 - 无意图")

    schemas = [
        {"type": "function", "function": {"name": "shell_run", "description": "执行命令"}},
    ]
    empty_intent = IntentResult()
    annotated = annotate_schema_priority(schemas, empty_intent)

    check(
        "无意图时原样返回",
        annotated[0]["function"]["description"] == "执行命令",
        f"got desc={annotated[0]['function']['description']}",
    )


def test_extract_tool_name():
    """测试工具名提取。"""
    print("\n🧪 工具名提取")

    check("browser_open_url → browser", _extract_tool_name("browser_open_url") == "browser")
    check("browser_use_run_task → browser_use", _extract_tool_name("browser_use_run_task") == "browser_use")
    check("doc_generator_generate_document → doc_generator", _extract_tool_name("doc_generator_generate_document") == "doc_generator")
    check("mcp_browserbase-csdn_navigate → mcp_browserbase-csdn", _extract_tool_name("mcp_browserbase-csdn_navigate") == "mcp_browserbase-csdn")
    check("shell_run → shell", _extract_tool_name("shell_run") == "shell")
    check("file_read → file", _extract_tool_name("file_read") == "file")


# =====================================================================
# 3. 单次工具调用数量限制测试
# =====================================================================

def test_tool_call_validator():
    """测试前置校验器。"""
    print("\n🧪 前置校验器")

    validator = ToolCallValidator(max_per_call=3)

    # 3 个调用 → PASS
    calls_ok = [MagicMock() for _ in range(3)]
    result_ok = validator.validate(calls_ok)
    check(
        "3 个工具 → PASS",
        result_ok.is_passed,
        f"got status={result_ok.status}",
    )

    # 4 个调用 → REJECT
    calls_bad = [MagicMock() for _ in range(4)]
    result_bad = validator.validate(calls_bad)
    check(
        "4 个工具 → REJECT",
        result_bad.is_rejected,
        f"got status={result_bad.status}",
    )
    check(
        "REJECT 含错误信息",
        "超过限制" in result_bad.message,
        f"got message={result_bad.message}",
    )

    # 1 个调用 → PASS
    calls_one = [MagicMock()]
    result_one = validator.validate(calls_one)
    check("1 个工具 → PASS", result_one.is_passed)

    # 0 个调用 → PASS
    result_empty = validator.validate([])
    check("0 个工具 → PASS", result_empty.is_passed)


def test_validator_custom_limit():
    """测试自定义限制。"""
    print("\n🧪 自定义调用限制")

    validator = ToolCallValidator(max_per_call=1)
    check("max_per_call 属性", validator.max_per_call == 1)

    result = validator.validate([MagicMock(), MagicMock()])
    check("自定义限制1 → 2个调用被拒", result.is_rejected)


# =====================================================================
# 4. 渐进式工具暴露引擎测试
# =====================================================================

def _make_mock_registry():
    """创建 mock ToolRegistry。"""
    reg = MagicMock()

    # 创建模拟工具
    tool_names = [
        "shell", "file", "screen", "search", "browser", "browser_use",
        "notify", "clipboard", "app_control", "calculator", "datetime_tool",
        "doc_generator", "image_generator", "weather", "cron",
        "mcp_browserbase", "mcp_browserbase-csdn",
        "voice_input", "voice_output", "ocr", "knowledge_rag",
        "tool_info", "email",
    ]
    mock_tools = []
    for name in tool_names:
        tool = MagicMock()
        tool.name = name
        tool.get_schema.return_value = [
            {"type": "function", "function": {"name": f"{name}_action", "description": f"{name} desc"}}
        ]
        mock_tools.append(tool)

    reg.list_tools.return_value = mock_tools

    def get_schemas_by_names(names):
        return [
            {"type": "function", "function": {"name": f"{n}_action", "description": f"{n} desc"}}
            for n in names
            if n in tool_names
        ]

    reg.get_schemas_by_names.side_effect = get_schemas_by_names

    def get_all_schemas():
        return [
            {"type": "function", "function": {"name": f"{n}_action", "description": f"{n} desc"}}
            for n in tool_names
        ]

    reg.get_all_schemas.side_effect = get_all_schemas

    def get_tool_config(name):
        configs = {
            "doc_generator": {
                "dependencies": {"input_sources": ["weather", "image_generator", "file", "search"], "standalone": False}
            },
            "image_generator": {
                "dependencies": {"output_for": ["doc_generator"], "standalone": True}
            },
            "weather": {
                "dependencies": {"output_for": ["doc_generator"], "standalone": True}
            },
        }
        return configs.get(name, {})

    reg.get_tool_config.side_effect = get_tool_config

    return reg


def test_exposure_engine_tiers():
    """测试工具暴露引擎分层逻辑。"""
    print("\n🧪 暴露引擎 - 分层")

    reg = _make_mock_registry()
    engine = ToolExposureEngine(reg, enabled=True, enable_annotation=False)

    # 高置信度 → recommended 小集合
    high_intent = IntentResult(
        intents={"system_admin"},
        confidence=0.9,
        primary_intent="system_admin",
    )
    schemas_high = engine.get_schemas(high_intent)
    tool_names_high = {s["function"]["name"].replace("_action", "") for s in schemas_high}
    check(
        "高置信度: 包含核心工具 shell",
        "shell" in tool_names_high,
        f"got tools={tool_names_high}",
    )
    check(
        "高置信度: 包含意图工具 screen",
        "screen" in tool_names_high,
        f"got tools={tool_names_high}",
    )
    check(
        "高置信度: 工具数 < 全量",
        len(schemas_high) < 23,
        f"got {len(schemas_high)} schemas",
    )

    # 低置信度 → full 全量
    low_intent = IntentResult(
        intents=set(),
        confidence=0.1,
        primary_intent="",
    )
    schemas_low = engine.get_schemas(low_intent)
    check(
        "低置信度: 全量工具集",
        len(schemas_low) >= 20,
        f"got {len(schemas_low)} schemas",
    )


def test_exposure_engine_disabled():
    """测试暴露引擎禁用时返回全量。"""
    print("\n🧪 暴露引擎 - 禁用")

    reg = _make_mock_registry()
    engine = ToolExposureEngine(reg, enabled=False, enable_annotation=False)

    intent = IntentResult(intents={"system_admin"}, confidence=0.9, primary_intent="system_admin")
    schemas = engine.get_schemas(intent)

    check(
        "禁用时返回全量",
        len(schemas) >= 20,
        f"got {len(schemas)} schemas",
    )


def test_exposure_engine_auto_upgrade():
    """测试连续失败自动升级。"""
    print("\n🧪 暴露引擎 - 自动升级")

    reg = _make_mock_registry()
    engine = ToolExposureEngine(reg, enabled=True, enable_annotation=False, failures_to_upgrade=2)

    check("初始 tier = auto", engine.current_tier == "auto")

    # 报告 2 次失败
    engine.report_failure()
    check("1次失败 → 仍然 auto", engine.current_tier == "auto")
    engine.report_failure()
    check(
        "2次失败 → 升级",
        engine.current_tier in ("extended", "full"),
        f"got tier={engine.current_tier}",
    )

    # 报告成功 → 重置连续失败计数（但 forced_tier 不变）
    engine.report_success()
    check(
        "成功后保持已升级 tier",
        engine.current_tier in ("extended", "full"),
    )

    # reset 全部重置
    engine.reset()
    check("reset → auto", engine.current_tier == "auto")


def test_exposure_engine_dependencies():
    """测试工具依赖自动解析。"""
    print("\n🧪 暴露引擎 - 依赖解析")

    reg = _make_mock_registry()
    engine = ToolExposureEngine(reg, enabled=True, enable_annotation=False)

    # 文档组装意图 → 应自动包含 doc_generator 的依赖工具
    intent = IntentResult(
        intents={"document_assembly"},
        confidence=0.9,
        primary_intent="document_assembly",
    )
    schemas = engine.get_schemas(intent)
    tool_names = {s["function"]["name"].replace("_action", "") for s in schemas}

    check(
        "包含 doc_generator",
        "doc_generator" in tool_names,
        f"got tools={tool_names}",
    )
    check(
        "依赖解析: 包含 weather",
        "weather" in tool_names,
        f"got tools={tool_names}",
    )
    check(
        "依赖解析: 包含 image_generator",
        "image_generator" in tool_names,
        f"got tools={tool_names}",
    )


# =====================================================================
# 5. 分级错误反馈测试
# =====================================================================

def test_graded_error_feedback():
    """测试分级错误反馈。"""
    print("\n🧪 分级错误反馈")

    result = ToolResult(
        status=ToolResultStatus.ERROR,
        error="ConnectionError: 服务不可用",
        duration_ms=1500.0,
    )

    # 首次失败 → 简短版
    msg_short = result.to_message(failure_count=0)
    check(
        "首次失败: 简短版含 [错误]",
        "[错误]" in msg_short and "建议" not in msg_short,
        f"got: {msg_short[:80]}",
    )

    # 第二次失败 → 标准版
    msg_std = result.to_message(failure_count=2)
    check(
        "第2次失败: 标准版含建议",
        "建议" in msg_std and "类型" in msg_std,
        f"got: {msg_std[:80]}",
    )

    # 第三次+ → 详细版
    msg_detail = result.to_message(failure_count=3)
    check(
        "第3次失败: 详细版含操作步骤",
        "建议操作" in msg_detail and "耗时" in msg_detail,
        f"got: {msg_detail[:80]}",
    )


def test_graded_error_success():
    """测试成功时的消息。"""
    print("\n🧪 分级反馈 - 成功场景")

    result_ok = ToolResult(status=ToolResultStatus.SUCCESS, output="操作完成")
    check(
        "成功时返回原始输出",
        result_ok.to_message(failure_count=5) == "操作完成",
    )

    result_empty = ToolResult(status=ToolResultStatus.SUCCESS, output="")
    check(
        "成功但无输出",
        result_empty.to_message() == "(无输出)",
    )


def test_graded_error_timeout():
    """测试超时的分级消息。"""
    print("\n🧪 分级反馈 - 超时")

    result_timeout = ToolResult(status=ToolResultStatus.TIMEOUT, error="超时")
    msg1 = result_timeout.to_message(failure_count=0)
    check("超时首次: 简短", "[超时]" in msg1 and "建议" not in msg1)

    msg2 = result_timeout.to_message(failure_count=2)
    check("超时多次: 含建议", "[超时]" in msg2 and "建议" in msg2)


def test_error_type_extraction():
    """测试错误类型提取。"""
    print("\n🧪 错误类型提取")

    result = ToolResult(status=ToolResultStatus.ERROR, error="ValueError: 参数无效")
    check(
        "提取 ValueError",
        result._extract_error_type() == "ValueError",
    )

    result2 = ToolResult(status=ToolResultStatus.ERROR, error="未知错误")
    check(
        "无冒号格式 → status",
        result2._extract_error_type() == "error",
    )


# =====================================================================
# 6. 数据结构与映射表完整性检查
# =====================================================================

def test_intent_categories_completeness():
    """检查意图分类、工具映射、优先级映射的对齐。"""
    print("\n🧪 映射表完整性")

    # 所有 INTENT_CATEGORIES 中的意图都应在 TOOL_MAPPING 中有对应
    for intent in INTENT_CATEGORIES:
        check(
            f"TOOL_MAPPING 包含 {intent}",
            intent in INTENT_TOOL_MAPPING,
            f"missing in INTENT_TOOL_MAPPING",
        )

    # 所有 INTENT_CATEGORIES 中的意图都应在 PRIORITY_MAP 中有对应
    for intent in INTENT_CATEGORIES:
        check(
            f"PRIORITY_MAP 包含 {intent}",
            intent in INTENT_PRIORITY_MAP,
            f"missing in INTENT_PRIORITY_MAP",
        )

    # PRIORITY_MAP 结构检查
    for intent, mapping in INTENT_PRIORITY_MAP.items():
        check(
            f"PRIORITY_MAP[{intent}] 有 recommended",
            "recommended" in mapping,
        )
        check(
            f"PRIORITY_MAP[{intent}] 有 alternative",
            "alternative" in mapping,
        )


# =====================================================================
# 主入口
# =====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 6 工具调用链路优化 — 单元测试")
    print("=" * 60)

    # 1. 意图识别
    test_intent_recognition()
    test_intent_confidence()
    test_intent_backward_compat()

    # 2. Schema 标注
    test_schema_annotation()
    test_schema_annotation_no_intent()
    test_extract_tool_name()

    # 3. 前置校验
    test_tool_call_validator()
    test_validator_custom_limit()

    # 4. 暴露引擎
    test_exposure_engine_tiers()
    test_exposure_engine_disabled()
    test_exposure_engine_auto_upgrade()
    test_exposure_engine_dependencies()

    # 5. 分级错误反馈
    test_graded_error_feedback()
    test_graded_error_success()
    test_graded_error_timeout()
    test_error_type_extraction()

    # 6. 映射表完整性
    test_intent_categories_completeness()

    # 结果汇总
    print("\n" + "=" * 60)
    total = passed + failed
    print(f"结果: {passed}/{total} 通过, {failed} 失败")
    if failed == 0:
        print("🎉 全部测试通过!")
    else:
        print(f"⚠️ 有 {failed} 个测试失败")
    print("=" * 60)

    sys.exit(1 if failed else 0)
