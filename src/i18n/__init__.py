"""国际化支持模块。

Phase 4.9 实现：
- Qt 翻译加载
- 语言切换支持
- 翻译文件管理
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTranslator, QLocale, QLibraryInfo

logger = logging.getLogger(__name__)

# 翻译文件目录
TRANSLATIONS_DIR = Path(__file__).parent.parent.parent / "translations"

# 支持的语言
SUPPORTED_LANGUAGES = {
    "zh_CN": "简体中文",
    "en_US": "English",
}

# 翻译字典：{语言代码: {原文: 译文}}
TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh_CN": {},  # 中文无需翻译
    "en_US": {
        # 主窗口
        "文件": "File",
        "编辑": "Edit",
        "显示": "View",
        "工具": "Tools",
        "帮助": "Help",
        "发送": "Send",
        "新建会话": "New Session",
        "设置": "Settings",
        "帮助": "Help",
        "关于": "About",
        "退出": "Exit",
        "连接": "Connect",
        "断开": "Disconnect",
        "连接中...": "Connecting...",
        "已连接": "Connected",
        "未连接": "Disconnected",
        "AI 助手": "AI Assistant",
        "请输入消息...": "Please enter message...",
        "发送消息": "Send Message",
        "清空对话": "Clear Chat",
        "确认清空": "Clear Chat",
        "确定要清空当前对话吗？": "Are you sure you want to clear the current chat?",
        "取消": "Cancel",
        "确定": "OK",
        "清空": "Clear",
        "模型": "Model",
        "未选择": "Not Selected",

        # 工具栏按钮
        "📋 历史对话": "📋 History",
        "查看历史对话记录": "View chat history",
        "🎤 录音": "🎤 Record",
        "按住录音,松开发送": "Hold to record, release to send",
        "🔇 TTS": "🔇 TTS",
        "切换 AI 回复自动朗读": "Toggle AI response auto-readout",
        "📂 生成空间": "📂 Generated Files",
        "查看 AI 生成的所有文件": "View all AI-generated files",
        "🧠 知识库": "🧠 Knowledge Base",
        "管理知识库文档": "Manage knowledge base documents",
        "📂 生成空间": "📂 Generated Space",
        "复制工具执行状态": "Copy tool execution status",

        # 设置对话框
        "外观": "Appearance",
        "主题": "Theme",
        "亮色": "Light",
        "暗色": "Dark",
        "跟随系统": "System",
        "语言": "Language",
        "语言切换": "Language Switch",
        "语言已切换为": "Language changed to",
        "部分界面需要重启后生效。": "Some interfaces need restart to take effect.",
        "设置": "Settings",
        "关闭": "Close",
        "API 密钥": "API Keys",
        "通用": "General",
        "更新": "Update",

        # API Key 管理
        "保存": "Save",
        "删除": "Delete",
        "提示": "Hint",
        "成功": "Success",
        "错误": "Error",
        "确认": "Confirm",
        "已存储": "Stored",
        "请输入密钥值": "Please enter the key value",
        "已安全存储": "has been securely stored",
        "保存失败，请重试": "Save failed, please retry",
        "确定删除": "Delete",
        "显示/隐藏密钥": "Show/Hide key",
        "删除密钥": "Delete key",

        # 模型设置
        "AI 模型": "AI Model",
        "默认模型": "Default Model",

        # 语音识别
        "语音识别 (Whisper)": "Voice Recognition (Whisper)",
        "识别模型": "Recognition Model",
        "提示: 模型越大准确度越高，但需要更多内存和计算时间。": "Hint: Larger models are more accurate but require more memory and computation time.",
        "首次使用时会自动下载模型（需要网络）。": "The model will be automatically downloaded on first use (requires internet).",

        # 快捷键
        "快捷键": "Hotkey",
        "唤起窗口": "Invoke Window",
        "应用": "Apply",
        "快捷键已更新为": "Hotkey updated to",

        # 语音识别提示
        "提示: 模型越大准确度越高，但需要更多内存和计算时间。": "Hint: Larger models are more accurate but require more memory and computation time.",
        "首次使用时会自动下载模型（需要网络）。": "The model will be automatically downloaded on first use (requires internet).",

        # 系统托盘
        "显示窗口": "Show Window",
        "新会话": "New Session",
        "打开设置": "Open Settings",

        # 其他
        "加载中...": "Loading...",
        "错误": "Error",
        "警告": "Warning",
        "信息": "Information",
        "成功": "Success",
        "失败": "Failed",

        # 录音弹窗
        "语音录入": "Voice Input",
        "准备录音...": "Preparing...",
        "即将开始，请准备说话": "Ready, please prepare to speak",
        "录音中...": "Recording...",
        "请开始说话": "Please start speaking",
        "识别中...": "Recognizing...",
        "正在将语音转为文字，请稍候...": "Converting speech to text, please wait...",
        "识别完成": "Recognition Complete",
        "识别失败": "Recognition Failed",
        "未检测到语音": "No Speech Detected",
        "请确认麦克风是否正常工作，然后重试": "Please check your microphone and try again",
        "✘ 停止录音": "Stop Recording",
        "✘ 停止监听": "Stop Listening",
        "取消": "Cancel",
        "关闭": "Close",
        "监听中...": "Listening...",
        "请说话，系统会自动识别": "Speak, the system will recognize automatically",
    },
}


def tr(key: str) -> str:
    """翻译函数：将字符串翻译为当前语言。

    Args:
        key: 要翻译的原文（中文）

    Returns:
        翻译后的字符串
    """
    lang = "en_US" if _i18n_manager and _i18n_manager.current_language == "en_US" else "zh_CN"
    return TRANSLATIONS.get(lang, {}).get(key, key)


class I18nManager:
    """国际化管理器。"""

    def __init__(self):
        """初始化管理器。"""
        self._translator = QTranslator()
        self._qt_translator = QTranslator()
        # 检测系统语言并自动选择
        self._current_language = self._detect_system_language()
        # 初始化时自动加载默认语言
        self.load_language(self._current_language)

    def _detect_system_language(self) -> str:
        """检测系统语言并返回匹配的语言代码。"""
        # 首先尝试从配置文件读取
        config_path = Path(__file__).parent.parent.parent / "config" / "default.toml"
        if config_path.exists():
            try:
                # Python 3.11+ 内置 tomllib，否则使用 tomli
                try:
                    import tomllib
                except ImportError:
                    import tomli as tomllib
                with open(config_path, "rb") as f:
                    config = tomllib.load(f)
                lang = config.get("app", {}).get("language", "")
                if lang and lang in SUPPORTED_LANGUAGES:
                    logger.info("从配置文件读取语言: %s", lang)
                    return lang
            except Exception as e:
                logger.debug("读取配置文件失败: %s", e)

        # 检测系统语言并返回匹配的语言代码
        system_locale = QLocale.system().name()

        # 尝试精确匹配
        if system_locale in SUPPORTED_LANGUAGES:
            return system_locale

        # 尝试匹配前缀（如 "zh" 匹配 "zh_CN"）
        lang_prefix = system_locale.split("_")[0]
        for lang_code in SUPPORTED_LANGUAGES:
            if lang_code.startswith(lang_prefix):
                logger.info("检测到系统语言: %s, 使用: %s", system_locale, lang_code)
                return lang_code

        # 默认返回中文
        return "zh_CN"

    def load_language(self, language: str) -> bool:
        """加载指定语言的翻译。

        Args:
            language: 语言代码（如 zh_CN, en_US）

        Returns:
            是否加载成功
        """
        if language not in SUPPORTED_LANGUAGES:
            logger.warning("不支持的语言: %s", language)
            return False

        # 移除旧翻译
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.removeTranslator(self._translator)
            app.removeTranslator(self._qt_translator)

        # 加载 Qt 内置翻译
        qt_locale = QLocale(language.replace("_", "-"))
        qt_trans_path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)

        # 尝试多个可能的 Qt 翻译路径
        qt_trans_loaded = False
        if qt_trans_path:
            qt_trans_loaded = self._qt_translator.load(qt_locale, "qtbase", "_", qt_trans_path)

        # 如果 Qt 翻译加载失败，尝试备选路径
        if not qt_trans_loaded:
            import PySide6
            pyside6_path = Path(PySide6.__file__).parent
            alt_paths = [
                pyside6_path / "translations",
                pyside6_path / ".." / "translations",
                Path(sys.prefix) / "Lib" / "site-packages" / "PySide6" / "translations",
            ]
            for alt_path in alt_paths:
                if alt_path.exists():
                    if self._qt_translator.load(qt_locale, "qtbase", "_", str(alt_path)):
                        qt_trans_loaded = True
                        break

        if qt_trans_loaded and app:
            app.installTranslator(self._qt_translator)

        # 加载应用翻译
        ts_file = TRANSLATIONS_DIR / f"{language}.qm"
        if ts_file.exists():
            if self._translator.load(str(ts_file)):
                if app:
                    app.installTranslator(self._translator)
                self._current_language = language
                logger.info("已加载翻译: %s", language)
                return True
        else:
            # 如果翻译文件不存在，使用源语言
            self._current_language = language
            logger.info("翻译文件不存在，使用源语言: %s", language)
            return True

        return False

    @property
    def current_language(self) -> str:
        """当前语言。"""
        return self._current_language

    def get_supported_languages(self) -> dict[str, str]:
        """获取支持的语言列表。"""
        return SUPPORTED_LANGUAGES.copy()

    def get_language_name(self, code: str) -> str:
        """获取语言显示名称。"""
        return SUPPORTED_LANGUAGES.get(code, code)


# 全局单例
_i18n_manager: I18nManager | None = None


def get_i18n_manager() -> I18nManager:
    """获取国际化管理器单例。"""
    global _i18n_manager
    if _i18n_manager is None:
        _i18n_manager = I18nManager()
    return _i18n_manager
