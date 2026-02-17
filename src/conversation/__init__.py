"""对话模式模块。"""

from .ask_parser import AskParser, AskIntent, AskType, TimeoutStrategy
from .ask_widget import AskDialog, AskWidget
from .manager import ConversationManager, ConversationMode, ConversationState
from .task_notification import TaskNotificationHandler, TaskResultHandler
from .task_scheduler import TaskPriority, TaskScheduler, TaskStatus, get_scheduler
from .timeout_manager import TimeoutManager
from .tts_player import TTSEngine, TTSPlayer
from .voice_recognizer import RecognizerEngine, VoiceRecognizer, WhisperRecognizer
from .wake_word_detector import SimpleWakeWordDetector, WakeWordDetector, WakeWordEngine

__all__ = [
    # 管理器
    "ConversationManager",
    "ConversationMode",
    "ConversationState",
    # 追问解析
    "AskParser",
    "AskIntent",
    "AskType",
    "TimeoutStrategy",
    # 追问UI
    "AskWidget",
    "AskDialog",
    # 任务调度
    "TaskScheduler",
    "TaskPriority",
    "TaskStatus",
    "get_scheduler",
    # 任务通知
    "TaskNotificationHandler",
    "TaskResultHandler",
    # 超时管理
    "TimeoutManager",
    # TTS
    "TTSPlayer",
    "TTSEngine",
    # 语音识别
    "VoiceRecognizer",
    "WhisperRecognizer",
    "RecognizerEngine",
    # 唤醒词
    "WakeWordDetector",
    "SimpleWakeWordDetector",
    "WakeWordEngine",
]
