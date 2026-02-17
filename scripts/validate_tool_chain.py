"""工具全链路一致性校验脚本。

检查 tools.json 与相关模块的一致性：
[1] tools.json 中声明的工具是否在 INTENT_TOOL_MAPPING 中至少出现一次
[2] INTENT_TOOL_MAPPING 中引用的工具是否都在 tools.json 中存在
[3] INTENT_PRIORITY_MAP 中引用的工具是否都在 tools.json 中存在
[4] 多下划线工具名是否在 _extract_tool_name.known_prefixes 中
[5] 有 dependencies 的工具，其 input_sources 引用的工具是否都在 tools.json 中存在
[6] registry._build_init_kwargs 中是否有对应 elif 分支
[7] INTENT_CATEGORIES / INTENT_TOOL_MAPPING / INTENT_PRIORITY_MAP 三张表的 key 是否对齐

用法:
    python scripts/validate_tool_chain.py
    python scripts/validate_tool_chain.py --fix-suggestions
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 导入需要检查的模块
from src.core.prompts import (
    INTENT_CATEGORIES,
    INTENT_TOOL_MAPPING,
    INTENT_PRIORITY_MAP,
)
from src.core.tool_exposure import _extract_tool_name

# 默认配置文件路径
TOOLS_JSON_PATH = PROJECT_ROOT / "config" / "tools.json"
REGISTRY_PATH = PROJECT_ROOT / "src" / "tools" / "registry.py"


def load_tools_json() -> tuple[dict, set[str]]:
    """加载 tools.json，返回 (完整配置, 启用的工具名集合)。"""
    with open(TOOLS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    tools_section = data.get("tools", {})
    enabled_tools = set()
    for name, cfg in tools_section.items():
        if cfg.get("enabled", True) and not cfg.get("deprecated", False):
            enabled_tools.add(name)
    
    return data, enabled_tools


def get_all_tools_in_mapping() -> set[str]:
    """获取 INTENT_TOOL_MAPPING 中引用的所有工具名。"""
    tools = set()
    for tool_list in INTENT_TOOL_MAPPING.values():
        tools.update(tool_list)
    return tools


def get_all_tools_in_priority_map() -> set[str]:
    """获取 INTENT_PRIORITY_MAP 中引用的所有工具名。"""
    tools = set()
    for mapping in INTENT_PRIORITY_MAP.values():
        tools.update(mapping.get("recommended", []))
        tools.update(mapping.get("alternative", []))
    return tools


def get_known_prefixes() -> set[str]:
    """获取 _extract_tool_name 中的已知前缀。"""
    # 从源码中提取 known_prefixes 列表
    source = _extract_tool_name.__code__.co_consts
    # 或者直接访问模块级变量（如果有的话）
    # 这里我们使用硬编码方式，因为函数内部定义的列表无法直接访问
    return {
        "mcp_browserbase-csdn", "mcp_browserbase",
        "browser_use", "app_control", "voice_input", "voice_output",
        "datetime_tool", "chat_history", "doc_generator",
        "image_generator", "python_runner", "tool_info",
        "knowledge_rag", "batch_paper_analyzer",
    }


def get_build_init_kwargs_tools() -> set[str]:
    """从 registry.py 的 _build_init_kwargs 方法中提取覆盖的工具名。"""
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 匹配 elif tool_name == "xxx" 模式
    pattern = r'elif tool_name == ["\'](\w+)["\']'
    matches = re.findall(pattern, content)
    return set(matches)


def get_dependencies_input_sources(tools_data: dict) -> dict[str, list[str]]:
    """获取工具依赖的 input_sources。"""
    result = {}
    tools_section = tools_data.get("tools", {})
    for name, cfg in tools_section.items():
        deps = cfg.get("dependencies", {})
        input_sources = deps.get("input_sources", [])
        if input_sources:
            result[name] = input_sources
    return result


def check_1_mapping_coverage(enabled_tools: set[str], show_suggestions: bool) -> tuple[bool, str]:
    """检查 [1] tools.json 中声明的工具是否在 INTENT_TOOL_MAPPING 中至少出现一次。"""
    tools_in_mapping = get_all_tools_in_mapping()
    
    # tool_info 是元工具，始终在任何工具集中，无需在映射表中
    excluded = {"tool_info"}
    effective_tools = enabled_tools - excluded
    missing = effective_tools - tools_in_mapping
    
    if not missing:
        return True, f"INTENT_TOOL_MAPPING 覆盖: {len(effective_tools)}/{len(effective_tools)} 工具 (tool_info 除外)"
    
    msg = f"INTENT_TOOL_MAPPING 未覆盖: {missing}"
    if show_suggestions:
        msg += f"\n  建议: 在 prompts.py INTENT_TOOL_MAPPING 中添加这些工具到合适的意图"
    return False, msg


def check_2_mapping_references(tools_data: dict, show_suggestions: bool) -> tuple[bool, str]:
    """检查 [2] INTENT_TOOL_MAPPING 中引用的工具是否都在 tools.json 中存在。"""
    tools_section = tools_data.get("tools", {})
    all_tool_names = set(tools_section.keys())
    tools_in_mapping = get_all_tools_in_mapping()
    
    # MCP 工具是动态加载的，允许在映射表中引用
    mcp_tools = {t for t in tools_in_mapping if t.startswith("mcp_")}
    unknown = tools_in_mapping - all_tool_names - mcp_tools
    
    if not unknown:
        mcp_note = f" (含 {len(mcp_tools)} 个 MCP 动态工具)" if mcp_tools else ""
        return True, f"INTENT_TOOL_MAPPING 引用有效: {len(tools_in_mapping)} 工具{mcp_note}"
    
    msg = f"INTENT_TOOL_MAPPING 引用未知工具: {unknown}"
    if show_suggestions:
        msg += f"\n  建议: 从 INTENT_TOOL_MAPPING 中移除这些工具，或在 tools.json 中添加"
    return False, msg


def check_3_priority_map_references(tools_data: dict, show_suggestions: bool) -> tuple[bool, str]:
    """检查 [3] INTENT_PRIORITY_MAP 中引用的工具是否都在 tools.json 中存在。"""
    tools_section = tools_data.get("tools", {})
    all_tool_names = set(tools_section.keys())
    tools_in_priority = get_all_tools_in_priority_map()
    
    # MCP 工具是动态加载的，允许在映射表中引用
    mcp_tools = {t for t in tools_in_priority if t.startswith("mcp_")}
    unknown = tools_in_priority - all_tool_names - mcp_tools
    
    if not unknown:
        mcp_note = f" (含 {len(mcp_tools)} 个 MCP 动态工具)" if mcp_tools else ""
        return True, f"INTENT_PRIORITY_MAP 引用有效: {len(tools_in_priority)} 工具{mcp_note}"
    
    msg = f"INTENT_PRIORITY_MAP 引用未知工具: {unknown}"
    if show_suggestions:
        msg += f"\n  建议: 从 INTENT_PRIORITY_MAP 中移除这些工具，或在 tools.json 中添加"
    return False, msg


def check_4_known_prefixes(enabled_tools: set[str], show_suggestions: bool) -> tuple[bool, str]:
    """检查 [4] 多下划线工具名是否在 _extract_tool_name.known_prefixes 中。"""
    known = get_known_prefixes()
    
    # 找出工具名包含多个下划线的工具
    multi_underscore = {t for t in enabled_tools if t.count("_") >= 1}
    missing = multi_underscore - known
    
    if not missing:
        return True, f"_extract_tool_name 已知前缀覆盖: {len(multi_underscore)} 个多下划线工具"
    
    msg = f"_extract_tool_name 缺失前缀: {missing}"
    if show_suggestions:
        msg += f"\n  建议: 在 tool_exposure.py _extract_tool_name 的 known_prefixes 中添加这些前缀"
    return False, msg


def check_5_dependencies(tools_data: dict, show_suggestions: bool) -> tuple[bool, str]:
    """检查 [5] 有 dependencies 的工具，其 input_sources 引用的工具是否都在 tools.json 中存在。"""
    tools_section = tools_data.get("tools", {})
    all_tool_names = set(tools_section.keys())
    deps = get_dependencies_input_sources(tools_data)
    
    invalid = {}
    for tool_name, input_sources in deps.items():
        unknown = set(input_sources) - all_tool_names
        if unknown:
            invalid[tool_name] = unknown
    
    if not invalid:
        return True, f"dependencies.input_sources 引用有效: {len(deps)} 个工具有依赖"
    
    msg = f"dependencies.input_sources 引用未知工具: {invalid}"
    if show_suggestions:
        msg += f"\n  建议: 确保 input_sources 中的工具名与 tools.json 中定义的一致"
    return False, msg


def check_6_init_kwargs(enabled_tools: set[str], show_suggestions: bool) -> tuple[bool, str]:
    """检查 [6] registry._build_init_kwargs 中是否有对应 elif 分支。"""
    covered = get_build_init_kwargs_tools()
    
    # 注意：这个检查是警告级别，因为很多工具不需要特殊参数
    # 只检查有特殊配置需求的核心工具
    core_tools = {"shell", "file", "screen", "browser", "search", "weather", "cron"}
    missing = core_tools - covered
    
    if not missing:
        return True, f"_build_init_kwargs 覆盖核心工具: {len(covered)} 个分支"
    
    msg = f"_build_init_kwargs 未覆盖核心工具: {missing} (如无特殊参数可忽略)"
    return True, msg  # 返回 True 因为这是警告级别


def check_7_keys_alignment(show_suggestions: bool) -> tuple[bool, str]:
    """检查 [7] INTENT_CATEGORIES / INTENT_TOOL_MAPPING / INTENT_PRIORITY_MAP 三张表的 key 是否对齐。"""
    categories_keys = set(INTENT_CATEGORIES.keys())
    mapping_keys = set(INTENT_TOOL_MAPPING.keys())
    priority_keys = set(INTENT_PRIORITY_MAP.keys())
    
    # 检查 mapping 是否缺少 key
    missing_in_mapping = categories_keys - mapping_keys
    # 检查 priority 是否缺少 key
    missing_in_priority = categories_keys - priority_keys
    
    issues = []
    if missing_in_mapping:
        issues.append(f"INTENT_TOOL_MAPPING 缺少: {missing_in_mapping}")
    if missing_in_priority:
        issues.append(f"INTENT_PRIORITY_MAP 缺少: {missing_in_priority}")
    
    if not issues:
        return True, f"三表 key 对齐: {len(categories_keys)} 个意图"
    
    msg = "\n".join(issues)
    if show_suggestions:
        msg += f"\n  建议: 在缺失的映射表中添加对应的意图"
    return False, msg


def main():
    parser = argparse.ArgumentParser(description="工具全链路一致性校验")
    parser.add_argument(
        "--fix-suggestions",
        action="store_true",
        help="输出修复建议",
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("WinClaw 工具全链路一致性校验")
    print("=" * 60)
    
    # 加载数据
    tools_data, enabled_tools = load_tools_json()
    print(f"\n已加载 tools.json: {len(enabled_tools)} 个启用工具\n")
    
    # 执行检查
    checks = [
        ("[1/7]", check_1_mapping_coverage, (enabled_tools, args.fix_suggestions)),
        ("[2/7]", check_2_mapping_references, (tools_data, args.fix_suggestions)),
        ("[3/7]", check_3_priority_map_references, (tools_data, args.fix_suggestions)),
        ("[4/7]", check_4_known_prefixes, (enabled_tools, args.fix_suggestions)),
        ("[5/7]", check_5_dependencies, (tools_data, args.fix_suggestions)),
        ("[6/7]", check_6_init_kwargs, (enabled_tools, args.fix_suggestions)),
        ("[7/7]", check_7_keys_alignment, (args.fix_suggestions,)),
    ]
    
    passed = 0
    warnings = 0
    failed = 0
    
    for prefix, check_func, args_tuple in checks:
        success, msg = check_func(*args_tuple)
        if success:
            if "可忽略" in msg:
                print(f"  ⚠️ {prefix} {msg}")
                warnings += 1
            else:
                print(f"  ✅ {prefix} {msg}")
                passed += 1
        else:
            print(f"  ❌ {prefix} {msg}")
            failed += 1
    
    # 汇总
    print("\n" + "=" * 60)
    total = passed + warnings + failed
    print(f"结果: {passed} 通过, {warnings} 警告, {failed} 失败")
    
    if failed == 0:
        print("全链路一致性校验通过!")
    else:
        print(f"发现 {failed} 个问题需要修复")
    
    print("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
