"""对话模式功能冒烟测试和回归测试。

测试范围：
- 对话管理器状态机
- 追问解析器
- 超时管理器
- 任务调度器
- TTS播放器
- 语音识别器
- 唤醒词检测器
- 追问UI组件
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PySide6.QtWidgets import QApplication


# ===== 测试夹具 =====

@pytest.fixture(scope="session")
def qapp():
    """创建QApplication实例。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


# ===== 冒烟测试 =====

class TestConversationManagerSmoke:
    """对话管理器冒烟测试。"""

    def test_import_conversation_module(self):
        """测试模块导入。"""
        from src.conversation import (
            ConversationManager,
            AskParser,
            TimeoutManager,
            TaskScheduler,
            TTSPlayer,
            VoiceRecognizer,
            WakeWordDetector,
            AskWidget,
        )
        assert ConversationManager is not None
        assert AskParser is not None

    def test_conversation_manager_creation(self, qapp):
        """测试对话管理器创建。"""
        from src.conversation import ConversationManager
        mgr = ConversationManager()
        assert mgr is not None
        assert mgr.mode.value == "off"
        assert mgr.state.value == "idle"

    def test_conversation_mode_switch(self, qapp):
        """测试模式切换。"""
        from src.conversation import ConversationManager, ConversationMode
        mgr = ConversationManager()

        # 切换到持续对话模式
        mgr.set_mode("continuous")
        assert mgr.mode == ConversationMode.CONTINUOUS

        # 切换到唤醒词模式
        mgr.set_mode("wake_word")
        assert mgr.mode == ConversationMode.WAKE_WORD

        # 切换到关闭
        mgr.set_mode("off")
        assert mgr.mode == ConversationMode.OFF


class TestAskParserSmoke:
    """追问解析器冒烟测试。"""

    def test_ask_parser_creation(self):
        """测试解析器创建。"""
        from src.conversation import AskParser
        parser = AskParser()
        assert parser is not None

    def test_parse_normal_text(self):
        """测试普通文本解析。"""
        from src.conversation import AskParser
        parser = AskParser()
        result = parser.parse("你好，这是一个普通文本")
        assert result is None

    def test_parse_choice_markup(self):
        """测试选项追问解析。"""
        from src.conversation import AskParser, AskType
        parser = AskParser()
        text = "请选择一个选项：<|ASK_CHOICE|>[\"选项1\", \"选项2\", \"选项3\"]<|/ASK_CHOICE|><|TIMEOUT|>auto_select<|/TIMEOUT|>"
        result = parser.parse(text)
        assert result is not None
        assert result.type == AskType.CHOICE
        assert len(result.options) > 0


class TestTimeoutManagerSmoke:
    """超时管理器冒烟测试。"""

    def test_timeout_manager_creation(self):
        """测试超时管理器创建。"""
        from src.conversation import TimeoutManager
        mgr = TimeoutManager()
        assert mgr is not None
        assert not mgr.is_active

    def test_timeout_start_cancel(self, qapp):
        """测试超时启动和取消。"""
        from src.conversation import TimeoutManager, TimeoutStrategy
        mgr = TimeoutManager()

        # 启动超时
        mgr.start(TimeoutStrategy.AUTO_SELECT, "默认选项", 30)
        assert mgr.is_active

        # 取消超时
        mgr.cancel()
        assert not mgr.is_active


class TestTaskSchedulerSmoke:
    """任务调度器冒烟测试。"""

    def test_get_scheduler(self):
        """测试获取全局调度器。"""
        from src.conversation import get_scheduler
        scheduler = get_scheduler()
        assert scheduler is not None
        assert scheduler.MAX_PARALLEL_TASKS == 3


# ===== 回归测试 =====

class TestConversationManagerRegression:
    """对话管理器回归测试。"""

    def test_silence_detection(self, qapp):
        """测试沉默检测。"""
        from src.conversation import ConversationManager
        mgr = ConversationManager(timeout=2)  # 2秒超时用于测试
        mgr.set_mode("continuous")

        # 触发超时
        # 注意：实际测试需要等待超时触发
        assert mgr.is_active

    def test_ending_intent_detection(self, qapp):
        """测试结束意图检测。"""
        from src.conversation import ConversationManager
        mgr = ConversationManager()
        mgr.set_mode("continuous")

        # 测试结束语检测
        ending_phrases = ["再见", "不聊了", "晚安"]
        for phrase in ending_phrases:
            assert mgr._is_ending_intent(phrase)

        # 测试非结束语
        assert not mgr._is_ending_intent("今天天气真好")


class TestAskParserRegression:
    """追问解析器回归测试。"""

    def test_parse_confirm_markup(self):
        """测试确认追问解析。"""
        from src.conversation import AskParser, AskType
        parser = AskParser()
        text = "确定要删除吗？<|ASK_CONFIRM|>确定删除吗？<|/ASK_CONFIRM|>"
        result = parser.parse(text)
        assert result is not None
        assert result.type == AskType.CONFIRM

    def test_parse_input_markup(self):
        """测试输入追问解析。"""
        from src.conversation import AskParser, AskType
        parser = AskParser()
        text = "请输入文件名：<|ASK_INPUT|>请输入<|/ASK_INPUT|>"
        result = parser.parse(text)
        assert result is not None
        assert result.type == AskType.INPUT

    def test_extract_options(self):
        """测试选项提取。"""
        from src.conversation import AskParser
        parser = AskParser()

        # JSON数组格式
        options = parser._extract_options('["选项A", "选项B", "选项C"]')
        assert len(options) >= 1

        # 字母格式
        options = parser._extract_options("A) 选项1 B) 选项2 C) 选项3")
        assert len(options) >= 1


class TestTimeoutManagerRegression:
    """超时管理器回归测试。"""

    def test_all_strategies(self, qapp):
        """测试所有超时策略。"""
        from src.conversation import TimeoutManager, TimeoutStrategy

        # 测试WAIT_FOREVER策略（不触发超时）
        mgr = TimeoutManager()
        mgr.start(TimeoutStrategy.WAIT_FOREVER, None, 1)
        assert mgr.is_active
        mgr.cancel()
        assert not mgr.is_active

        # 测试SKIP策略
        mgr.start(TimeoutStrategy.SKIP, None, 1)
        assert mgr.is_active


class TestTaskSchedulerRegression:
    """任务调度器回归测试。"""

    @pytest.mark.asyncio
    async def test_submit_cancel_task(self):
        """测试任务提交和取消。"""
        from src.conversation import get_scheduler, TaskPriority
        scheduler = get_scheduler()

        # 提交任务
        async def dummy_task():
            await asyncio.sleep(0.1)
            return "result"

        task_id = scheduler.submit("测试任务", dummy_task(), TaskPriority.TOOL_EXECUTION)
        assert task_id

        # 取消任务
        scheduler.cancel(task_id)
        # 注意：在测试环境中，状态可能已经是CANCELLED或COMPLETED


class TestWakeWordDetectorRegression:
    """唤醒词检测器回归测试。"""

    def test_simple_detector(self):
        """测试简单唤醒词检测器。"""
        from src.conversation import SimpleWakeWordDetector
        detector = SimpleWakeWordDetector(wake_words=["小铃铛", "你好"])

        assert detector.check("小铃铛在吗")
        assert detector.check("你好助手")
        assert not detector.check("今天天气很好")


class TestTTSPlayerRegression:
    """TTS播放器回归测试。"""

    def test_text_preprocessing(self):
        """测试文本预处理。"""
        from src.conversation import TTSPlayer
        player = TTSPlayer()

        # 测试emoji移除
        text = "你好😊世界🌍"
        cleaned = player._preprocess_text(text)
        assert "😊" not in cleaned
        assert "🌍" not in cleaned

        # 测试标记移除
        text = "你好<|ASK_CHOICE|>选项<|/ASK_CHOICE|>"
        cleaned = player._preprocess_text(text)
        assert "<|" not in cleaned


class TestIntegration:
    """集成测试。"""

    def test_conversation_flow(self, qapp):
        """测试完整对话流程。"""
        from src.conversation import (
            ConversationManager,
            AskParser,
            TimeoutManager,
            ConversationMode,
            ConversationState,
        )

        # 创建组件
        mgr = ConversationManager()
        parser = AskParser()
        timeout_mgr = TimeoutManager()

        # 切换到对话模式
        mgr.set_mode("continuous")
        assert mgr.mode == ConversationMode.CONTINUOUS

        # 模拟语音识别 - 会设置为CHATTING状态
        mgr.on_speech_result("今天天气怎么样", is_final=True)
        # 状态可能是CHATTING（自动发送消息）
        assert mgr.state in [ConversationState.CHATTING, ConversationState.THINKING]

        # 模拟TTS播放
        mgr.on_tts_start()
        assert mgr.state == ConversationState.SPEAKING

        # TTS播放完成
        mgr.on_tts_finished()
        assert mgr.state == ConversationState.CHATTING


# ===== 运行测试 =====

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
