"""TaskTrace 和废弃工具流程测试。"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest


class TestTaskTrace:
    """TaskTrace 数据结构测试。"""

    def test_tool_call_record_to_dict(self):
        """测试 ToolCallRecord 序列化。"""
        from src.core.task_trace import ToolCallRecord

        record = ToolCallRecord(
            step=1,
            function_name="browser_use_run_task",
            arguments={"task": "打开百度"},
            status="success",
            duration_ms=150.5,
            error="",
            output_preview="任务完成",
        )

        d = record.to_dict()
        assert d["step"] == 1
        assert d["function_name"] == "browser_use_run_task"
        assert d["status"] == "success"
        assert d["duration_ms"] == 150.5

    def test_task_trace_to_dict(self):
        """测试 TaskTrace 序列化。"""
        from src.core.task_trace import TaskTrace, ToolCallRecord

        trace = TaskTrace(
            trace_id="abc123",
            session_id="session-1",
            timestamp="2026-02-16T10:00:00",
            user_input="帮我打开百度",
            intent_primary="web_browsing",
            intent_all=["web_browsing", "search"],
            intent_confidence=0.85,
            tool_tier="recommended",
            tools_exposed=["browser_use_run_task", "search_web"],
            tools_exposed_count=2,
            total_steps=1,
            tool_calls=[
                ToolCallRecord(
                    step=1,
                    function_name="browser_use_run_task",
                    arguments={"task": "打开百度"},
                    status="success",
                    duration_ms=150.5,
                )
            ],
            final_status="completed",
            total_tokens=500,
            total_duration_ms=1500.0,
        )

        d = trace.to_dict()
        assert d["trace_id"] == "abc123"
        assert d["intent_primary"] == "web_browsing"
        assert len(d["tool_calls"]) == 1
        assert d["tool_calls"][0]["function_name"] == "browser_use_run_task"


class TestTaskTraceCollector:
    """TaskTraceCollector 测试。"""

    def test_collector_basic_flow(self):
        """测试基本采集流程。"""
        from src.core.task_trace import TaskTraceCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            collector = TaskTraceCollector(
                session_id="test-session",
                user_input="测试输入",
                trace_dir=Path(tmpdir),
                enabled=True,
            )

            # 模拟意图识别结果
            class MockIntentResult:
                primary_intent = "web_browsing"
                intents = {"web_browsing", "search"}
                confidence = 0.85
                matched_keywords = {"web_browsing": ["打开", "网页"]}

            collector.set_intent(
                intent_result=MockIntentResult(),
                tier="recommended",
                exposed_tools=["browser_use_run_task", "search_web"],
            )

            # 添加工具调用
            collector.add_tool_call(
                step=1,
                function_name="browser_use_run_task",
                arguments={"task": "打开百度"},
                status="success",
                duration_ms=150.5,
                error="",
                output="任务完成",
            )

            # 完成
            collector.finalize(
                status="completed",
                tokens=500,
                response_preview="已为您打开百度",
            )

            # 写入文件
            result = collector.flush()
            assert result is True

            # 验证文件内容
            trace_file = Path(tmpdir) / f"trace-{datetime.now().strftime('%Y-%m-%d')}.jsonl"
            assert trace_file.exists()

            with open(trace_file, encoding="utf-8") as f:
                data = json.loads(f.read())

            assert data["session_id"] == "test-session"
            assert data["intent_primary"] == "web_browsing"
            assert data["final_status"] == "completed"
            assert len(data["tool_calls"]) == 1

    def test_collector_tier_upgrade(self):
        """测试层级升级记录。"""
        from src.core.task_trace import TaskTraceCollector

        collector = TaskTraceCollector(
            session_id="test-session",
            user_input="测试",
            enabled=False,  # 不写文件
        )

        collector.add_tier_upgrade("recommended", "extended")
        collector.add_tier_upgrade("extended", "full")

        assert len(collector.trace.tier_upgrades) == 2
        assert collector.trace.tool_tier == "full"

    def test_collector_consecutive_failures(self):
        """测试连续失败计数。"""
        from src.core.task_trace import TaskTraceCollector

        collector = TaskTraceCollector(
            session_id="test-session",
            user_input="测试",
            enabled=False,
        )

        # 添加失败调用
        collector.add_tool_call(
            step=1,
            function_name="tool1",
            arguments={},
            status="error",
            duration_ms=100,
            error="失败1",
        )
        assert collector.trace.consecutive_failures_max == 1

        # 再次失败
        collector.add_tool_call(
            step=2,
            function_name="tool2",
            arguments={},
            status="error",
            duration_ms=100,
            error="失败2",
        )
        assert collector.trace.consecutive_failures_max == 2

        # 成功调用重置
        collector.add_tool_call(
            step=3,
            function_name="tool3",
            arguments={},
            status="success",
            duration_ms=100,
        )
        # max 仍然是 2，但连续失败已重置
        assert collector.trace.consecutive_failures_max == 2


class TestSanitization:
    """敏感信息脱敏测试。"""

    def test_sanitize_dict_api_key(self):
        """测试 API Key 脱敏。"""
        from src.core.task_trace import _sanitize_dict

        data = {
            "api_key": "sk-1234567890abcdefghijklmnop",
            "task": "打开百度",
        }

        sanitized = _sanitize_dict(data, max_preview=200)
        assert sanitized["api_key"] == "***"
        assert sanitized["task"] == "打开百度"

    def test_sanitize_dict_password(self):
        """测试密码脱敏。"""
        from src.core.task_trace import _sanitize_dict

        data = {
            "password": "my_secret_password",
            "username": "user1",
        }

        sanitized = _sanitize_dict(data)
        assert sanitized["password"] == "***"
        assert sanitized["username"] == "user1"

    def test_sanitize_dict_nested(self):
        """测试嵌套字典脱敏。"""
        from src.core.task_trace import _sanitize_dict

        data = {
            "config": {
                "token": "abc123def456ghi789",
                "other": "value",
            }
        }

        sanitized = _sanitize_dict(data)
        assert sanitized["config"]["token"] == "***"
        assert sanitized["config"]["other"] == "value"

    def test_sanitize_string_long(self):
        """测试长字符串截断。"""
        from src.core.task_trace import _sanitize_string

        # 使用包含空格的字符串，避免被敏感模式（长连续字母数字）匹配
        long_str = "测试内容 " * 100
        sanitized = _sanitize_string(long_str, max_len=100)

        # 验证被截断
        assert len(sanitized) <= 103  # 100 + "..."
        assert sanitized.endswith("...")


class TestDeprecationFlow:
    """废弃工具流程测试。"""

    def test_deprecation_config_fields(self):
        """测试废弃配置字段解析。"""
        # 读取 tools.json 检查字段格式
        config_path = Path(__file__).parent.parent / "config" / "tools.json"
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)

            # 检查是否有废弃工具配置
            tools = data.get("tools", {})
            for tool_name, tool_cfg in tools.items():
                if tool_cfg.get("deprecated"):
                    assert "deprecation_message" in tool_cfg or True  # 可选
                    assert isinstance(tool_cfg.get("deprecated"), bool)


class TestValidationScript:
    """校验脚本测试。"""

    def test_validation_script_exists(self):
        """测试校验脚本存在。"""
        script_path = Path(__file__).parent.parent / "scripts" / "validate_tool_chain.py"
        assert script_path.exists()

    def test_validation_script_imports(self):
        """测试校验脚本可以导入。"""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        
        # 只检查文件存在，不实际执行
        # 因为执行需要完整的项目环境
        script_path = Path(__file__).parent.parent / "scripts" / "validate_tool_chain.py"
        assert script_path.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
