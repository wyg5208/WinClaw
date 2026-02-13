"""Phase 1 模型管理单元测试 — 覆盖 registry / selector / cost / config。"""

import asyncio
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

# 将项目根目录加入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import AppConfig, _deep_merge, _coerce_value
from src.models.registry import ModelConfig, ModelRegistry, UsageRecord
from src.models.selector import (
    ModelSelector,
    SelectionCriteria,
    SelectionStrategy,
)
from src.models.cost import CostTracker, SessionCost, DailyCost, ModelCost

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
# 配置系统测试
# =====================================================================

def test_config_load():
    """测试配置加载。"""
    print("\n🧪 测试配置系统 (AppConfig)")

    config = AppConfig.load()
    check("加载默认配置", config is not None)
    check("app.name 正确", config.app_name == "WinClaw", config.app_name)
    check("app.version 存在", len(config.app_version) > 0)
    check("agent.default_model 为 deepseek-chat", config.default_model == "deepseek-chat")
    check("agent.max_steps 为 15", config.max_steps == 15, str(config.max_steps))
    check("shell.timeout 为 30", config.shell_timeout == 30, str(config.shell_timeout))
    check("screen.quality 为 85", config.screen_quality == 85, str(config.screen_quality))


def test_config_get_set():
    """测试配置 get/set。"""
    print("\n🧪 测试配置 get/set")

    config = AppConfig.load()

    # get 嵌套路径
    val = config.get("agent.default_model")
    check("get 嵌套路径", val == "deepseek-chat", str(val))

    # get 不存在的路径
    val = config.get("nonexistent.path", "fallback")
    check("get 不存在路径返回默认值", val == "fallback")

    # set 运行时修改
    config.set("agent.max_steps", 20)
    check("set 修改生效", config.get("agent.max_steps") == 20)
    check("set 属性同步", config.max_steps == 20)

    # set 创建新路径
    config.set("custom.new_key", "hello")
    check("set 创建新路径", config.get("custom.new_key") == "hello")


def test_config_env_override():
    """测试环境变量覆盖。"""
    print("\n🧪 测试环境变量覆盖")

    os.environ["WINCLAW_AGENT_DEFAULT_MODEL"] = "gpt-4o"
    os.environ["WINCLAW_SHELL_TIMEOUT"] = "60"
    try:
        config = AppConfig.load()
        check("环境变量覆盖 default_model", config.default_model == "gpt-4o", config.default_model)
        check("环境变量覆盖 shell.timeout", config.shell_timeout == 60, str(config.shell_timeout))
    finally:
        del os.environ["WINCLAW_AGENT_DEFAULT_MODEL"]
        del os.environ["WINCLAW_SHELL_TIMEOUT"]


def test_config_deep_merge():
    """测试深度合并。"""
    print("\n🧪 测试深度合并")

    base = {"a": {"b": 1, "c": 2}, "d": 3}
    override = {"a": {"b": 10, "e": 5}, "f": 6}
    result = _deep_merge(base, override)
    check("保留 base.a.c", result["a"]["c"] == 2)
    check("覆盖 base.a.b", result["a"]["b"] == 10)
    check("新增 base.a.e", result["a"]["e"] == 5)
    check("保留 base.d", result["d"] == 3)
    check("新增 base.f", result["f"] == 6)


def test_config_coerce():
    """测试类型转换。"""
    print("\n🧪 测试类型转换")

    check("true → True", _coerce_value("true") is True)
    check("false → False", _coerce_value("false") is False)
    check("42 → int", _coerce_value("42") == 42)
    check("3.14 → float", _coerce_value("3.14") == 3.14)
    check("hello → str", _coerce_value("hello") == "hello")
    # 参考已有类型
    check("'60' + int参考 → int", _coerce_value("60", 30) == 60)


def test_config_get_section():
    """测试获取整个配置节。"""
    print("\n🧪 测试 get_section")

    config = AppConfig.load()
    agent_section = config.get_section("agent")
    check("get_section 返回 dict", isinstance(agent_section, dict))
    check("section 包含 default_model", "default_model" in agent_section)
    check("section 包含 max_steps", "max_steps" in agent_section)

    # 修改返回值不影响原配置
    agent_section["max_steps"] = 999
    check("get_section 返回副本", config.max_steps != 999)


# =====================================================================
# 模型注册中心测试
# =====================================================================

async def test_registry_load():
    """测试模型注册中心加载。"""
    print("\n🧪 测试模型注册中心 (ModelRegistry)")

    reg = ModelRegistry()
    models = reg.list_models()
    check("加载 ≥8 个模型", len(models) >= 8, f"只加载了 {len(models)} 个")

    # DeepSeek
    ds = reg.get("deepseek-chat")
    check("获取 deepseek-chat", ds is not None)
    check("DeepSeek id 正确", ds.id == "deepseek-chat" if ds else False)
    check("DeepSeek base_url 正确", ds.base_url == "https://api.deepseek.com" if ds else False)
    check("DeepSeek api_key_env 正确", ds.api_key_env == "DEEPSEEK_API_KEY" if ds else False)
    check("DeepSeek 支持 FC", ds.supports_function_calling if ds else False)
    check("DeepSeek 有 tags", "default" in ds.tags if ds else False)

    # GPT-4o
    gpt = reg.get("gpt-4o")
    check("获取 gpt-4o", gpt is not None)
    check("GPT-4o 支持图片", gpt.supports_image if gpt else False)

    # Gemini
    gemini = reg.get("gemini-2-flash")
    check("获取 gemini-2-flash", gemini is not None)
    check("Gemini 支持 FC", gemini.supports_function_calling if gemini else False)

    # Ollama local
    local = reg.get("local-qwen")
    check("获取 local-qwen", local is not None)
    check("Qwen 是本地模型", local.is_local if local else False)
    check("Qwen 是免费的", local.is_free if local else False)


async def test_registry_query():
    """测试注册中心查询方法。"""
    print("\n🧪 测试注册中心查询")

    reg = ModelRegistry()

    # 按能力筛选
    fc_models = reg.find_by_capability(needs_function_calling=True)
    check("FC 模型 ≥6", len(fc_models) >= 6, f"仅 {len(fc_models)} 个")

    img_models = reg.find_by_capability(needs_image=True)
    check("图片模型 ≥4", len(img_models) >= 4, f"仅 {len(img_models)} 个")

    # 按 Provider
    deepseek_models = reg.find_by_provider("deepseek")
    check("DeepSeek 模型 = 2", len(deepseek_models) == 2, str(len(deepseek_models)))

    google_models = reg.find_by_provider("google")
    check("Google 模型 ≥1", len(google_models) >= 1, str(len(google_models)))

    # 按 Tag
    cheap_models = reg.find_by_tag("cheap")
    check("cheap 标签 ≥3", len(cheap_models) >= 3, str(len(cheap_models)))

    local_models = reg.find_local_models()
    check("本地模型 ≥2", len(local_models) >= 2, str(len(local_models)))

    free_models = reg.find_free_models()
    check("免费模型 ≥2", len(free_models) >= 2, str(len(free_models)))


async def test_registry_validation():
    """测试配置校验（缺少必填字段的模型被跳过）。"""
    print("\n🧪 测试配置校验")

    # 用字典直接构建，其中一个缺少 name
    models_data = {
        "good-model": {
            "id": "test-model",
            "name": "Test Model",
            "provider": "test",
            "api_type": "openai",
        },
        "bad-model": {
            "id": "bad",
            # 缺少 name, provider, api_type
        },
    }
    reg = ModelRegistry(models_data=models_data)
    check("好模型被加载", reg.get("good-model") is not None)
    check("坏模型被跳过", reg.get("bad-model") is None)
    check("总共 1 个模型", len(reg.list_models()) == 1, str(len(reg.list_models())))


# =====================================================================
# 模型选择器测试
# =====================================================================

async def test_selector_specified():
    """测试指定模型策略。"""
    print("\n🧪 测试模型选择器 - 指定策略")

    reg = ModelRegistry()
    selector = ModelSelector(reg, default_model="deepseek-chat")

    # 指定存在的模型
    cfg = selector.select(SelectionStrategy.SPECIFIED, model_key="gpt-4o")
    check("指定 gpt-4o", cfg.key == "gpt-4o")

    # 不指定时用默认模型
    cfg = selector.select(SelectionStrategy.SPECIFIED)
    check("默认模型 deepseek-chat", cfg.key == "deepseek-chat")

    # 指定不存在的模型抛异常
    try:
        selector.select(SelectionStrategy.SPECIFIED, model_key="nonexistent")
        check("不存在模型抛异常", False, "没有抛出异常")
    except ValueError:
        check("不存在模型抛异常", True)


async def test_selector_capability():
    """测试能力匹配策略。"""
    print("\n🧪 测试模型选择器 - 能力匹配策略")

    reg = ModelRegistry()
    selector = ModelSelector(reg)

    # 需要 FC 能力 → 应选择 FC 中最便宜的
    cfg = selector.select(
        SelectionStrategy.CAPABILITY,
        criteria=SelectionCriteria(needs_function_calling=True),
    )
    check("能力匹配返回模型", cfg is not None)
    check("选中模型支持 FC", cfg.supports_function_calling)

    # 需要图片 → 不应选到纯文本模型
    cfg = selector.select(
        SelectionStrategy.CAPABILITY,
        criteria=SelectionCriteria(needs_image=True),
    )
    check("图片匹配返回模型", cfg is not None)
    check("选中模型支持图片", cfg.supports_image)

    # 优先 Provider
    cfg = selector.select(
        SelectionStrategy.CAPABILITY,
        criteria=SelectionCriteria(
            needs_function_calling=True,
            preferred_provider="anthropic",
        ),
    )
    check("优先 anthropic", cfg.provider == "anthropic", cfg.provider)


async def test_selector_cost_first():
    """测试成本优先策略。"""
    print("\n🧪 测试模型选择器 - 成本优先策略")

    reg = ModelRegistry()
    selector = ModelSelector(reg)

    # 成本优先（含本地模型） → 应选免费模型
    cfg = selector.select(SelectionStrategy.COST_FIRST)
    check("成本优先选择模型", cfg is not None)
    check("选中最便宜模型是免费的", cfg.is_free, f"cost={cfg.cost_input}/{cfg.cost_output}")

    # 排除本地后
    cfg = selector.select(
        SelectionStrategy.COST_FIRST,
        criteria=SelectionCriteria(exclude_local=True),
    )
    check("排除本地后选择模型", cfg is not None)
    check("排除本地后不是 ollama", cfg.provider != "ollama", cfg.provider)


async def test_selector_for_task():
    """测试便捷方法 select_for_task。"""
    print("\n🧪 测试 select_for_task 便捷方法")

    reg = ModelRegistry()
    selector = ModelSelector(reg, default_model="deepseek-chat")

    # 指定模型
    cfg = selector.select_for_task(model_key="gpt-4o")
    check("指定 model_key 生效", cfg.key == "gpt-4o")

    # 不指定 → 用默认
    cfg = selector.select_for_task(needs_function_calling=True)
    check("默认选择 deepseek-chat", cfg.key == "deepseek-chat")

    # 修改默认模型
    selector.default_model = "gpt-4o-mini"
    cfg = selector.select_for_task()
    check("修改默认后生效", cfg.key == "gpt-4o-mini")

    # 设置无效默认模型
    try:
        selector.default_model = "nonexistent"
        check("无效默认模型抛异常", False)
    except ValueError:
        check("无效默认模型抛异常", True)


# =====================================================================
# 成本追踪器测试
# =====================================================================

def test_cost_tracker_basic():
    """测试成本追踪器基础功能。"""
    print("\n🧪 测试成本追踪器 (CostTracker)")

    tracker = CostTracker()

    # 记录一次调用
    usage1 = UsageRecord(
        model_key="deepseek-chat",
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        cost=0.000280,
    )
    tracker.record(usage1, session_id="s1")

    check("总调用次数 = 1", tracker.total_calls == 1)
    check("总 token = 1500", tracker.total_tokens == 1500)
    check("总费用正确", abs(tracker.total_cost - 0.000280) < 1e-8)


def test_cost_tracker_session():
    """测试按会话统计。"""
    print("\n🧪 测试成本追踪器 - 会话统计")

    tracker = CostTracker()

    # 会话1: 两次调用
    tracker.record(UsageRecord("deepseek-chat", 1000, 500, 1500, 0.001), session_id="s1")
    tracker.record(UsageRecord("deepseek-chat", 2000, 800, 2800, 0.002), session_id="s1")

    # 会话2: 一次调用
    tracker.record(UsageRecord("gpt-4o", 500, 200, 700, 0.01), session_id="s2")

    s1 = tracker.get_session_cost("s1")
    check("会话1 存在", s1 is not None)
    check("会话1 调用次数 = 2", s1.call_count == 2 if s1 else False)
    check("会话1 总 token = 4300", s1.total_tokens == 4300 if s1 else False)

    s2 = tracker.get_session_cost("s2")
    check("会话2 调用次数 = 1", s2.call_count == 1 if s2 else False)

    s3 = tracker.get_session_cost("nonexistent")
    check("不存在的会话返回 None", s3 is None)


def test_cost_tracker_daily():
    """测试按日统计。"""
    print("\n🧪 测试成本追踪器 - 日统计")

    tracker = CostTracker()

    # 记录今天的调用
    tracker.record(UsageRecord("deepseek-chat", 1000, 500, 1500, 0.001))
    tracker.record(UsageRecord("gpt-4o", 500, 200, 700, 0.005))

    today = tracker.get_today_cost()
    check("今日调用次数 = 2", today.call_count == 2)
    check("今日 token = 2200", today.total_tokens == 2200)
    check("今日费用正确", abs(today.total_cost - 0.006) < 1e-8)


def test_cost_tracker_model():
    """测试按模型统计。"""
    print("\n🧪 测试成本追踪器 - 模型统计")

    tracker = CostTracker()
    tracker.record(UsageRecord("deepseek-chat", 1000, 500, 1500, 0.001))
    tracker.record(UsageRecord("deepseek-chat", 2000, 800, 2800, 0.002))
    tracker.record(UsageRecord("gpt-4o", 500, 200, 700, 0.01))

    ds = tracker.get_model_cost("deepseek-chat")
    check("DeepSeek 统计存在", ds is not None)
    check("DeepSeek 调用 2 次", ds.call_count == 2 if ds else False)
    check("DeepSeek prompt=3000", ds.prompt_tokens == 3000 if ds else False)
    check("DeepSeek completion=1300", ds.completion_tokens == 1300 if ds else False)

    all_models = tracker.get_all_model_costs()
    check("模型列表按费用降序", all_models[0].total_cost >= all_models[-1].total_cost)


def test_cost_tracker_budget():
    """测试预算限制。"""
    print("\n🧪 测试成本追踪器 - 预算限制")

    tracker = CostTracker(budget_limit=0.005)
    check("预算上限 = 0.005", tracker.budget_limit == 0.005)
    check("初始未超预算", not tracker.is_over_budget())

    tracker.record(UsageRecord("gpt-4o", 1000, 500, 1500, 0.003))
    check("3毫未超预算", not tracker.is_over_budget())

    tracker.record(UsageRecord("gpt-4o", 1000, 500, 1500, 0.003))
    check("6毫已超预算", tracker.is_over_budget())


def test_cost_tracker_summary():
    """测试汇总报告。"""
    print("\n🧪 测试成本追踪器 - 汇总报告")

    tracker = CostTracker(budget_limit=1.0)
    tracker.record(UsageRecord("deepseek-chat", 1000, 500, 1500, 0.001))

    summary = tracker.get_summary()
    check("汇总有 total_calls", summary["total_calls"] == 1)
    check("汇总有 today", "calls" in summary["today"])
    check("汇总有 budget_limit", summary["budget_limit_usd"] == 1.0)

    report = tracker.format_report()
    check("报告包含总调用", "总调用" in report)
    check("报告包含总费用", "总费用" in report)


def test_cost_tracker_clear():
    """测试清空。"""
    print("\n🧪 测试成本追踪器 - 清空")

    tracker = CostTracker()
    tracker.record(UsageRecord("deepseek-chat", 1000, 500, 1500, 0.001))
    check("清空前有数据", tracker.total_calls == 1)

    tracker.clear()
    check("清空后总调用 = 0", tracker.total_calls == 0)
    check("清空后总 token = 0", tracker.total_tokens == 0)
    check("清空后总费用 = 0", tracker.total_cost == 0.0)


# =====================================================================
# 主入口
# =====================================================================

async def main():
    print("=" * 60)
    print("  WinClaw Phase 1 模型管理单元测试")
    print("=" * 60)

    # 配置系统
    test_config_load()
    test_config_get_set()
    test_config_env_override()
    test_config_deep_merge()
    test_config_coerce()
    test_config_get_section()

    # 模型注册中心
    await test_registry_load()
    await test_registry_query()
    await test_registry_validation()

    # 模型选择器
    await test_selector_specified()
    await test_selector_capability()
    await test_selector_cost_first()
    await test_selector_for_task()

    # 成本追踪器
    test_cost_tracker_basic()
    test_cost_tracker_session()
    test_cost_tracker_daily()
    test_cost_tracker_model()
    test_cost_tracker_budget()
    test_cost_tracker_summary()
    test_cost_tracker_clear()

    print("\n" + "=" * 60)
    print(f"  结果: ✅ {passed} 通过  ❌ {failed} 失败")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
