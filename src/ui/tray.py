"""系统托盘图标。

功能：
- 托盘图标 + 右键菜单（显示/隐藏窗口、新建会话、设置、退出）
- 关闭窗口时最小化到托盘（而非退出）
- 托盘图标双击恢复窗口
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication, QMainWindow

logger = logging.getLogger(__name__)


def _create_default_icon() -> QIcon:
    """创建默认的 WinClaw 托盘图标（程序内绘制，无需外部文件）。"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 120, 212))  # Windows 蓝
    painter = QPainter(pixmap)
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Segoe UI", 26, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), 0x0084, "W")  # AlignCenter
    painter.end()
    return QIcon(pixmap)


class SystemTray(QSystemTrayIcon):
    """系统托盘图标。"""

    # 信号
    show_requested = Signal()
    new_session_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(
        self,
        window: QMainWindow,
        app: QApplication,
        icon: QIcon | None = None,
    ) -> None:
        super().__init__(icon or _create_default_icon(), app)
        self._window = window
        self._app = app
        self._setup_menu()
        self._connect_signals()
        self.setToolTip("WinClaw - AI 桌面智能体")

    def _setup_menu(self) -> None:
        """设置右键菜单。"""
        menu = QMenu()

        # 显示/隐藏窗口
        self._show_action = QAction("显示窗口", self)
        self._show_action.triggered.connect(self._toggle_window)
        menu.addAction(self._show_action)

        menu.addSeparator()

        # 新建会话
        new_action = QAction("新建会话", self)
        new_action.triggered.connect(self.new_session_requested.emit)
        menu.addAction(new_action)

        # 设置
        settings_action = QAction("设置...", self)
        settings_action.triggered.connect(self.settings_requested.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        # 退出
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._on_quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def _connect_signals(self) -> None:
        """连接信号。"""
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """处理托盘图标激活事件。"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _toggle_window(self) -> None:
        """切换窗口显示/隐藏。"""
        if self._window.isVisible():
            self._window.hide()
            self._show_action.setText("显示窗口")
        else:
            self._show_window()

    def _show_window(self) -> None:
        """显示并激活窗口。"""
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()
        self._show_action.setText("隐藏窗口")
        self.show_requested.emit()

    def _on_quit(self) -> None:
        """退出应用。"""
        self.quit_requested.emit()
        self.hide()
        self._app.quit()

    def update_show_action(self, visible: bool) -> None:
        """更新菜单中的显示/隐藏文本。"""
        self._show_action.setText("隐藏窗口" if visible else "显示窗口")
