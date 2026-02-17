#!/usr/bin/env python
"""TaskTrace 离线分析脚本。

用法:
    python scripts/analyze_traces.py                    # 分析今天的 trace
    python scripts/analyze_traces.py --last 7           # 分析最近 7 天
    python scripts/analyze_traces.py --date 2026-02-16  # 分析指定日期
    python scripts/analyze_traces.py --all              # 分析所有 trace
    python scripts/analyze_traces.py --output report.md # 输出到文件

功能:
    - 意图识别准确率统计
    - 工具使用频率分析
    - 失败模式识别
    - 层级升级频率统计
    - 性能指标分析
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 默认 trace 目录
DEFAULT_TRACE_DIR = Path.home() / ".winclaw" / "traces"


def load_traces(trace_dir: Path, days: int = 1, date_str: str | None = None, all_days: bool = False) -> list[dict[str, Any]]:
    """加载 trace 文件。

    Args:
        trace_dir: trace 目录
        days: 加载最近 N 天
        date_str: 指定日期 (YYYY-MM-DD)
        all_days: 加载所有文件

    Returns:
        trace 记录列表
    """
    traces = []

    if date_str:
        # 指定日期
        trace_file = trace_dir / f"trace-{date_str}.jsonl"
        if trace_file.exists():
            traces.extend(_load_jsonl(trace_file))
    elif all_days:
        # 所有文件
        for f in trace_dir.glob("trace-*.jsonl"):
            traces.extend(_load_jsonl(f))
    else:
        # 最近 N 天
        for i in range(days):
            d = datetime.now() - timedelta(days=i)
            trace_file = trace_dir / f"trace-{d.strftime('%Y-%m-%d')}.jsonl"
            if trace_file.exists():
                traces.extend(_load_jsonl(trace_file))

    return traces


def _load_jsonl(file_path: Path) -> list[dict[str, Any]]:
    """加载 JSONL 文件。"""
    records = []
    try:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        pass
    return records


def analyze_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """分析 trace 数据。

    Returns:
        分析结果字典
    """
    if not traces:
        return {"error": "没有找到 trace 数据"}

    result = {
        "total_traces": len(traces),
        "time_range": _get_time_range(traces),
        "intent_analysis": _analyze_intents(traces),
        "tool_analysis": _analyze_tools(traces),
        "failure_analysis": _analyze_failures(traces),
        "tier_analysis": _analyze_tiers(traces),
        "performance": _analyze_performance(traces),
    }

    return result


def _get_time_range(traces: list[dict[str, Any]]) -> dict[str, str]:
    """获取时间范围。"""
    timestamps = [t.get("timestamp", "") for t in traces if t.get("timestamp")]
    if not timestamps:
        return {"start": "N/A", "end": "N/A"}

    timestamps.sort()
    return {
        "start": timestamps[0][:19] if timestamps else "N/A",
        "end": timestamps[-1][:19] if timestamps else "N/A",
    }


def _analyze_intents(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """分析意图识别。"""
    intent_counter = Counter()
    confidence_sum = 0.0
    confidence_count = 0

    for t in traces:
        primary = t.get("intent_primary", "")
        if primary:
            intent_counter[primary] += 1

        confidence = t.get("intent_confidence", 0)
        if confidence > 0:
            confidence_sum += confidence
            confidence_count += 1

    return {
        "distribution": dict(intent_counter.most_common(10)),
        "avg_confidence": round(confidence_sum / confidence_count, 3) if confidence_count > 0 else 0,
        "unique_intents": len(intent_counter),
    }


def _analyze_tools(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """分析工具使用。"""
    tool_counter = Counter()
    tool_success = defaultdict(int)
    tool_fail = defaultdict(int)
    tool_duration = defaultdict(list)

    for t in traces:
        for tc in t.get("tool_calls", []):
            func_name = tc.get("function_name", "unknown")
            tool_counter[func_name] += 1

            status = tc.get("status", "")
            if status == "success":
                tool_success[func_name] += 1
            else:
                tool_fail[func_name] += 1

            duration = tc.get("duration_ms", 0)
            if duration:
                tool_duration[func_name].append(duration)

    # 计算平均耗时
    avg_duration = {}
    for tool, durations in tool_duration.items():
        if durations:
            avg_duration[tool] = round(sum(durations) / len(durations), 1)

    return {
        "usage_count": dict(tool_counter.most_common(15)),
        "success_rate": {
            tool: round(tool_success[tool] / (tool_success[tool] + tool_fail[tool]), 2)
            for tool in tool_counter
            if tool_success[tool] + tool_fail[tool] > 0
        },
        "avg_duration_ms": avg_duration,
        "total_calls": sum(tool_counter.values()),
        "unique_tools": len(tool_counter),
    }


def _analyze_failures(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """分析失败模式。"""
    error_counter = Counter()
    consecutive_failures = Counter()
    failed_traces = 0

    for t in traces:
        # 统计错误信息
        for tc in t.get("tool_calls", []):
            if tc.get("status") in ("error", "timeout", "denied"):
                error_msg = tc.get("error", "unknown")[:50]  # 截取前 50 字符
                error_counter[error_msg] += 1

        # 统计连续失败
        max_fail = t.get("consecutive_failures_max", 0)
        if max_fail > 0:
            consecutive_failures[max_fail] += 1

        # 统计失败 trace
        if t.get("final_status") in ("error", "max_steps"):
            failed_traces += 1

    return {
        "common_errors": dict(error_counter.most_common(10)),
        "consecutive_failures_distribution": dict(sorted(consecutive_failures.items())),
        "failed_traces": failed_traces,
        "failure_rate": round(failed_traces / len(traces), 3) if traces else 0,
    }


def _analyze_tiers(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """分析层级使用和升级。"""
    tier_counter = Counter()
    upgrade_counter = Counter()

    for t in traces:
        tier = t.get("tool_tier", "")
        if tier:
            tier_counter[tier] += 1

        for upgrade in t.get("tier_upgrades", []):
            upgrade_counter[upgrade] += 1

    return {
        "tier_distribution": dict(tier_counter),
        "upgrade_count": dict(upgrade_counter),
        "upgrade_rate": round(sum(upgrade_counter.values()) / len(traces), 3) if traces else 0,
    }


def _analyze_performance(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """分析性能指标。"""
    durations = []
    tokens = []
    steps = []

    for t in traces:
        if t.get("total_duration_ms"):
            durations.append(t["total_duration_ms"])
        if t.get("total_tokens"):
            tokens.append(t["total_tokens"])
        if t.get("total_steps"):
            steps.append(t["total_steps"])

    def _stats(values: list[float]) -> dict[str, float]:
        if not values:
            return {"avg": 0, "min": 0, "max": 0, "median": 0}
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return {
            "avg": round(sum(values) / n, 1),
            "min": round(min(values), 1),
            "max": round(max(values), 1),
            "median": round(sorted_vals[n // 2], 1),
        }

    return {
        "duration_ms": _stats(durations),
        "tokens": _stats(tokens),
        "steps": _stats(steps),
    }


def print_report(analysis: dict[str, Any], output_file: str | None = None) -> None:
    """打印分析报告。"""
    lines = []

    lines.append("=" * 60)
    lines.append("WinClaw TaskTrace 分析报告")
    lines.append("=" * 60)

    if "error" in analysis:
        lines.append(f"\n❌ {analysis['error']}")
        print("\n".join(lines))
        return

    # 基本信息
    lines.append(f"\n📊 总计: {analysis['total_traces']} 条记录")
    lines.append(f"📅 时间范围: {analysis['time_range']['start']} ~ {analysis['time_range']['end']}")

    # 意图分析
    lines.append("\n" + "-" * 40)
    lines.append("🎯 意图识别分析")
    lines.append("-" * 40)
    intent = analysis["intent_analysis"]
    lines.append(f"  唯一意图数: {intent['unique_intents']}")
    lines.append(f"  平均置信度: {intent['avg_confidence']}")
    lines.append("  分布:")
    for k, v in intent["distribution"].items():
        lines.append(f"    - {k}: {v}")

    # 工具分析
    lines.append("\n" + "-" * 40)
    lines.append("🔧 工具使用分析")
    lines.append("-" * 40)
    tool = analysis["tool_analysis"]
    lines.append(f"  总调用次数: {tool['total_calls']}")
    lines.append(f"  唯一工具数: {tool['unique_tools']}")
    lines.append("  使用频率:")
    for k, v in tool["usage_count"].items():
        rate = tool["success_rate"].get(k, "N/A")
        lines.append(f"    - {k}: {v} 次 (成功率: {rate})")

    # 失败分析
    lines.append("\n" + "-" * 40)
    lines.append("❌ 失败分析")
    lines.append("-" * 40)
    fail = analysis["failure_analysis"]
    lines.append(f"  失败 trace 数: {fail['failed_traces']}")
    lines.append(f"  失败率: {fail['failure_rate']}")
    if fail["common_errors"]:
        lines.append("  常见错误:")
        for k, v in fail["common_errors"].items():
            lines.append(f"    - {k}: {v} 次")

    # 层级分析
    lines.append("\n" + "-" * 40)
    lines.append("📈 层级分析")
    lines.append("-" * 40)
    tier = analysis["tier_analysis"]
    lines.append(f"  层级分布: {tier['tier_distribution']}")
    lines.append(f"  升级次数: {tier['upgrade_count']}")
    lines.append(f"  升级率: {tier['upgrade_rate']}")

    # 性能分析
    lines.append("\n" + "-" * 40)
    lines.append("⚡ 性能指标")
    lines.append("-" * 40)
    perf = analysis["performance"]
    lines.append(f"  耗时(ms): avg={perf['duration_ms']['avg']}, median={perf['duration_ms']['median']}")
    lines.append(f"  Token数: avg={perf['tokens']['avg']}, median={perf['tokens']['median']}")
    lines.append(f"  步骤数: avg={perf['steps']['avg']}, median={perf['steps']['median']}")

    lines.append("\n" + "=" * 60)

    report = "\n".join(lines)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"报告已保存到: {output_file}")
    else:
        print(report)


def main():
    parser = argparse.ArgumentParser(description="WinClaw TaskTrace 离线分析")
    parser.add_argument(
        "--trace-dir",
        type=str,
        default=str(DEFAULT_TRACE_DIR),
        help=f"trace 目录 (默认: {DEFAULT_TRACE_DIR})",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=1,
        help="分析最近 N 天 (默认: 1)",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="分析指定日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="分析所有 trace 文件",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="输出报告到文件",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式",
    )

    args = parser.parse_args()

    trace_dir = Path(args.trace_dir)

    # 加载 traces
    traces = load_traces(
        trace_dir,
        days=args.last,
        date_str=args.date,
        all_days=args.all,
    )

    # 分析
    analysis = analyze_traces(traces)

    # 输出
    if args.json:
        output = json.dumps(analysis, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"JSON 已保存到: {args.output}")
        else:
            print(output)
    else:
        print_report(analysis, args.output)


if __name__ == "__main__":
    main()
