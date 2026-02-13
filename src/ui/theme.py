"""亮/暗主题支持。

提供 Light / Dark 两套主题样式表，支持：
- 手动切换
- 跟随 Windows 系统设置自动切换
- 所有 UI 组件样式统一

主题通过 Qt StyleSheet 实现，覆盖所有自定义组件。
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class Theme(Enum):
    """主题枚举。"""
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


# ====================================================================
# 亮色主题
# ====================================================================
LIGHT_STYLE = """
QMainWindow {
    background-color: #f5f5f5;
}
QDialog {
    background-color: #f5f5f5;
    color: #333;
}
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e0e0e0;
    padding: 5px;
}
QComboBox {
    padding: 5px;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: white;
    color: #333;
}
QComboBox QAbstractItemView {
    background: white;
    color: #333;
    selection-background-color: #0078d4;
    selection-color: white;
}
QPushButton {
    padding: 6px 16px;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: #f8f8f8;
    color: #333;
}
QPushButton:hover {
    background: #e8e8e8;
}
QPushButton:default {
    background: #0078d4;
    color: white;
    border-color: #0078d4;
}
QPushButton:default:hover {
    background: #006cbd;
}
QTextEdit {
    border: 1px solid #ccc;
    border-radius: 4px;
    background: white;
    padding: 8px;
    color: #333;
}
QLineEdit {
    border: 1px solid #ccc;
    border-radius: 4px;
    background: white;
    padding: 5px;
    color: #333;
}
QLabel {
    color: #333;
}
QGroupBox {
    border: 1px solid #ccc;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 8px;
    color: #333;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 4px;
    color: #333;
}
QTabWidget::pane {
    border: 1px solid #ccc;
    background: #f5f5f5;
}
QTabBar::tab {
    background: #e8e8e8;
    color: #333;
    padding: 8px 16px;
    border: 1px solid #ccc;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #f5f5f5;
}
QMessageBox {
    background-color: #f5f5f5;
    color: #333;
}
QProgressBar {
    border: 1px solid #ccc;
    border-radius: 3px;
    background: #e8e8e8;
}
QProgressBar::chunk {
    background: #0078d4;
}
QStatusBar {
    background-color: #f0f0f0;
    border-top: 1px solid #ddd;
    color: #333;
}
QMenuBar {
    background-color: #ffffff;
    color: #333;
}
QMenuBar::item:selected {
    background-color: #e8e8e8;
}
QMenu {
    background-color: #ffffff;
    color: #333;
    border: 1px solid #ddd;
}
QMenu::item:selected {
    background-color: #0078d4;
    color: white;
}
QScrollArea {
    border: none;
    background-color: #f8f9fa;
}
"""

# ====================================================================
# 暗色主题
# ====================================================================
DARK_STYLE = """
QMainWindow {
    background-color: #1e1e1e;
}
QDialog {
    background-color: #2d2d2d;
    color: #e0e0e0;
}
QToolBar {
    background-color: #2d2d2d;
    border-bottom: 1px solid #3e3e3e;
    padding: 5px;
}
QComboBox {
    padding: 5px;
    border: 1px solid #555;
    border-radius: 4px;
    background: #3c3c3c;
    color: #e0e0e0;
}
QComboBox QAbstractItemView {
    background: #3c3c3c;
    color: #e0e0e0;
    selection-background-color: #0078d4;
    selection-color: white;
}
QPushButton {
    padding: 6px 16px;
    border: 1px solid #555;
    border-radius: 4px;
    background: #3c3c3c;
    color: #e0e0e0;
}
QPushButton:hover {
    background: #4a4a4a;
}
QPushButton:default {
    background: #0078d4;
    color: white;
    border-color: #0078d4;
}
QPushButton:default:hover {
    background: #006cbd;
}
QTextEdit {
    border: 1px solid #555;
    border-radius: 4px;
    background: #2d2d2d;
    padding: 8px;
    color: #e0e0e0;
}
QLineEdit {
    border: 1px solid #555;
    border-radius: 4px;
    background: #3c3c3c;
    padding: 5px;
    color: #e0e0e0;
}
QLabel {
    color: #e0e0e0;
}
QGroupBox {
    border: 1px solid #555;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 8px;
    color: #e0e0e0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 4px;
    color: #e0e0e0;
}
QTabWidget::pane {
    border: 1px solid #555;
    background: #2d2d2d;
}
QTabBar::tab {
    background: #3c3c3c;
    color: #e0e0e0;
    padding: 8px 16px;
    border: 1px solid #555;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #2d2d2d;
}
QMessageBox {
    background-color: #2d2d2d;
    color: #e0e0e0;
}
QProgressBar {
    border: 1px solid #555;
    border-radius: 3px;
    background: #3c3c3c;
}
QProgressBar::chunk {
    background: #0078d4;
}
QStatusBar {
    background-color: #2d2d2d;
    border-top: 1px solid #3e3e3e;
    color: #e0e0e0;
}
QMenuBar {
    background-color: #2d2d2d;
    color: #e0e0e0;
}
QMenuBar::item:selected {
    background-color: #3e3e3e;
}
QMenu {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3e3e3e;
}
QMenu::item:selected {
    background-color: #0078d4;
    color: white;
}
QScrollArea {
    border: none;
    background-color: #252525;
}
"""

# 聊天组件专用颜色（供 chat.py 使用）
THEME_COLORS = {
    Theme.LIGHT: {
        # 背景色
        "chat_bg": "#f8f9fa",
        "chat_bg_gradient": "linear-gradient(180deg, #f8f9fa 0%, #ffffff 100%)",
        # 用户气泡
        "user_bubble_bg": "#0078d4",
        "user_bubble_bg_gradient": "linear-gradient(135deg, #0078d4 0%, #005a9e 100%)",
        "user_bubble_text": "white",
        # AI气泡
        "ai_bubble_bg": "white",
        "ai_bubble_text": "#333",
        "ai_bubble_border": "#e0e0e0",
        "ai_bubble_shadow": "0 2px 8px rgba(0,0,0,0.08)",
        # 代码块
        "code_bg": "#f4f4f4",
        "code_border": "#e1e4e8",
        "code_header_bg": "#f6f8fa",
        # 语法高亮
        "syntax_keyword": "#cf222e",
        "syntax_string": "#0a3069",
        "syntax_comment": "#6e7781",
        "syntax_function": "#8250df",
        "syntax_number": "#0550ae",
        "syntax_builtin": "#953800",
        # 特殊块
        "think_bg": "#f0f4ff",
        "think_border": "#6366f1",
        "think_text": "#6366f1",
        "tool_card_bg": "linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)",
        "tool_card_border": "#cbd5e1",
        "tool_name_color": "#0078d4",
        "blockquote_border": "#0078d4",
        "blockquote_text": "#555",
        # 链接
        "link_color": "#0078d4",
        # 滚动条
        "scrollbar_bg": "#f0f0f0",
        "scrollbar_handle": "#c0c0c0",
        "scrollbar_handle_hover": "#a0a0a0",
    },
    Theme.DARK: {
        # 背景色
        "chat_bg": "#1a1a2e",
        "chat_bg_gradient": "linear-gradient(180deg, #1a1a2e 0%, #16213e 100%)",
        # 用户气泡
        "user_bubble_bg": "#0078d4",
        "user_bubble_bg_gradient": "linear-gradient(135deg, #0078d4 0%, #005a9e 100%)",
        "user_bubble_text": "white",
        # AI气泡
        "ai_bubble_bg": "#2d2d3a",
        "ai_bubble_text": "#e0e0e0",
        "ai_bubble_border": "#3e3e4e",
        "ai_bubble_shadow": "0 2px 12px rgba(0,0,0,0.3)",
        # 代码块
        "code_bg": "#1e1e2e",
        "code_border": "#3e3e4e",
        "code_header_bg": "#252535",
        # 语法高亮
        "syntax_keyword": "#ff7b72",
        "syntax_string": "#a5d6ff",
        "syntax_comment": "#8b949e",
        "syntax_function": "#d2a8ff",
        "syntax_number": "#79c0ff",
        "syntax_builtin": "#ffa657",
        # 特殊块
        "think_bg": "#1e1e3e",
        "think_border": "#8b5cf6",
        "think_text": "#a5b4fc",
        "tool_card_bg": "linear-gradient(135deg, #2d2d3a 0%, #1e1e2e 100%)",
        "tool_card_border": "#4e4e5e",
        "tool_name_color": "#4da6ff",
        "blockquote_border": "#4da6ff",
        "blockquote_text": "#a0a0a0",
        # 链接
        "link_color": "#4da6ff",
        # 滚动条
        "scrollbar_bg": "#2d2d2d",
        "scrollbar_handle": "#555",
        "scrollbar_handle_hover": "#777",
    },
}


def detect_system_theme() -> Theme:
    """检测 Windows 系统当前主题设置。"""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return Theme.LIGHT if value == 1 else Theme.DARK
    except Exception:
        return Theme.LIGHT


def resolve_theme(theme: Theme) -> Theme:
    """解析主题（将 SYSTEM 解析为具体主题）。"""
    if theme == Theme.SYSTEM:
        return detect_system_theme()
    return theme


def get_stylesheet(theme: Theme) -> str:
    """获取指定主题的样式表。"""
    resolved = resolve_theme(theme)
    return LIGHT_STYLE if resolved == Theme.LIGHT else DARK_STYLE


def get_theme_colors(theme: Theme) -> dict[str, str]:
    """获取指定主题的颜色配置。"""
    resolved = resolve_theme(theme)
    return THEME_COLORS.get(resolved, THEME_COLORS[Theme.LIGHT])


def apply_theme(app: QApplication, theme: Theme) -> Theme:
    """应用主题到 QApplication。

    Returns:
        实际应用的主题（SYSTEM 时返回解析后的主题）
    """
    resolved = resolve_theme(theme)
    app.setStyleSheet(get_stylesheet(resolved))
    logger.info("已应用主题: %s", resolved.value)
    return resolved
