"""国际化支持模块。

Phase 4.9 实现：
- Qt 翻译加载
- 语言切换支持
- 翻译文件管理
"""

from __future__ import annotations

import logging
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


class I18nManager:
    """国际化管理器。"""

    def __init__(self):
        """初始化管理器。"""
        self._translator = QTranslator()
        self._qt_translator = QTranslator()
        self._current_language = "zh_CN"

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
        if self._qt_translator.load(qt_locale, "qtbase", "_", qt_trans_path):
            if app:
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
