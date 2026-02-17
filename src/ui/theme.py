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
    # 时尚渐变主题
    OCEAN_BLUE = "ocean_blue"
    FOREST_GREEN = "forest_green"
    SUNSET_ORANGE = "sunset_orange"
    PURPLE_DREAM = "purple_dream"
    PINK_ROSE = "pink_rose"
    MINIMAL_WHITE = "minimal_white"
    # 深色系主题
    DEEP_BLUE = "deep_blue"
    DEEP_BROWN = "deep_brown"


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
/* 定时任务卡片 - 亮色主题 */
#cronJobCard, CronJobCard {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 8px;
    margin: 2px 0px;
}
#cronJobCard:hover, CronJobCard:hover {
    border-color: #0078d4;
    background-color: #f8f8f8;
}
#cronJobCard QLabel, CronJobCard QLabel {
    background-color: transparent;
    color: #333333;
}
#cronJobCard QPushButton, CronJobCard QPushButton {
    background-color: #f0f0f0;
    color: #333333;
    border: 1px solid #ccc;
    border-radius: 4px;
}
#cronJobCard QPushButton:hover, CronJobCard QPushButton:hover {
    background-color: #e0e0e0;
}
/* 任务状态标签 */
#cronJobCard #statusLabel, CronJobCard #statusLabel {
    padding: 2px 8px;
    border-radius: 4px;
}
#cronJobCard #statusLabel[status="active"], CronJobCard #statusLabel[status="active"] {
    background-color: #4caf50;
    color: white;
}
#cronJobCard #statusLabel[status="paused"], CronJobCard #statusLabel[status="paused"] {
    background-color: #ff9800;
    color: white;
}
/* 详细文字 */
#cronJobCard #detailLabel, CronJobCard #detailLabel {
    color: #666666;
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
/* 通用容器组件 - 深色主题 */
QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
}
QFrame, QLabeledStackedWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
}
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    /* QFrame::Box = 4, QFrame::Panel = 5 */
    background-color: #2d2d2d;
    border: 1px solid #3e3e3e;
    border-radius: 4px;
}
/* 列表组件 */
QListWidget, QListView, QTreeWidget, QTreeView, QTableWidget, QTableView {
    background-color: #1e1a1a;
    color: #e0e0e0;
    border: 1px solid #3e3e3e;
    border-radius: 4px;
}
QListWidget::item, QListView::item, QTreeWidget::item {
    background-color: transparent;
    padding: 4px;
}
QListWidget::item:selected, QListView::item:selected,
QTreeWidget::item:selected, QTreeView::item:selected {
    background-color: #0078d4;
    color: white;
}
QListWidget::item:hover, QListView::item:hover,
QTreeWidget::item:hover, QTreeView::item:hover {
    background-color: #3e3e3e;
}
/* 表头 */
QHeaderView::section {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3e3e3e;
    padding: 4px;
}
/* 分隔器 */
QSplitter::handle {
    background-color: #3e3e3e;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}
/* 停靠窗口 */
QDockWidget {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3e3e3e;
    titlebar-close-icon: url(close.png);
    titlebar-normal-icon: url(undock.png);
}
QDockWidget::title {
    background-color: #252525;
    padding: 4px;
    border: 1px solid #3e3e3e;
}
/* 工具箱 */
QToolBox::tab {
    background-color: #2d2d2d;
    color: #e0e0e0;
    padding: 6px;
    border: 1px solid #3e3e3e;
}
QToolBox::tab:selected {
    background-color: #1e1e1e;
    border-bottom: 2px solid #0078d4;
}
QToolBox::tab:hover {
    background-color: #3e3e3e;
}
/* 堆叠窗口 */
QStackedWidget {
    background-color: #1e1e1e;
}
/* 输入区域容器 */
QWidget#inputContainer, QWidget#attachmentContainer,
QWidget#toolOutputContainer, QWidget#workflowOutputContainer {
    background-color: #2d2d2d;
    border: 1px solid #3e3e3e;
    border-radius: 4px;
}
/* 卡片容器 */
QFrame#cardFrame, QFrame[card="true"] {
    background-color: #2d2d2d;
    border: 1px solid #3e3e3e;
    border-radius: 6px;
}
"""

# ====================================================================
# 海洋蓝主题 - 清新现代的蓝色渐变
# ====================================================================
OCEAN_BLUE_STYLE = """
QMainWindow {
    background-color: #e8f4fc;
}
QDialog {
    background-color: #e8f4fc;
    color: #1a3a4a;
}
QToolBar {
    background-color: linear-gradient(90deg, #0288d1 0%, #26c6da 100%);
    border-bottom: 1px solid #b3e5fc;
    padding: 5px;
}
QComboBox {
    padding: 6px;
    border: 1px solid #81d4fa;
    border-radius: 6px;
    background: white;
    color: #0277bd;
}
QComboBox:hover {
    border-color: #0288d1;
}
QComboBox QAbstractItemView {
    background: white;
    color: #0277bd;
    selection-background-color: #0288d1;
    selection-color: white;
    border-radius: 4px;
}
QPushButton {
    padding: 8px 20px;
    border: 1px solid #81d4fa;
    border-radius: 6px;
    background: linear-gradient(180deg, #ffffff 0%, #e1f5fe 100%);
    color: #0277bd;
    font-weight: 500;
}
QPushButton:hover {
    background: linear-gradient(180deg, #e1f5fe 0%, #b3e5fc 100%);
    border-color: #0288d1;
}
QPushButton:default {
    background: linear-gradient(180deg, #29b6f6 0%, #0288d1 100%);
    color: white;
    border-color: #0277bd;
}
QPushButton:default:hover {
    background: linear-gradient(180deg, #4fc3f7 0%, #0292d8 100%);
}
QTextEdit {
    border: 1px solid #81d4fa;
    border-radius: 6px;
    background: white;
    padding: 10px;
    color: #1a3a4a;
}
QLineEdit {
    border: 1px solid #81d4fa;
    border-radius: 6px;
    background: white;
    padding: 6px;
    color: #1a3a4a;
}
QLineEdit:focus {
    border-color: #0288d1;
    background: #f5fbff;
}
QLabel {
    color: #01579b;
    font-weight: 500;
}
QGroupBox {
    border: 1px solid #b3e5fc;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    background: rgba(255,255,255,0.7);
    color: #01579b;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: #0277bd;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #b3e5fc;
    border-radius: 8px;
    background: white;
}
QTabBar::tab {
    background: linear-gradient(180deg, #e1f5fe 0%, #b3e5fc 100%);
    color: #0277bd;
    padding: 10px 20px;
    border: 1px solid #81d4fa;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background: linear-gradient(180deg, #ffffff 0%, #e1f5fe 100%);
    border-bottom: 2px solid #0288d1;
}
QTabBar::tab:hover:!selected {
    background: linear-gradient(180deg, #b3e5fc 0%, #81d4fa 100%);
}
QMessageBox {
    background-color: white;
    color: #1a3a4a;
}
QProgressBar {
    border: 1px solid #81d4fa;
    border-radius: 6px;
    background: #e1f5fe;
}
QProgressBar::chunk {
    background: linear-gradient(90deg, #29b6f6 0%, #0288d1 100%);
    border-radius: 4px;
}
QStatusBar {
    background-color: linear-gradient(180deg, #e1f5fe 0%, #b3e5fc 100%);
    border-top: 1px solid #81d4fa;
    color: #01579b;
}
QMenuBar {
    background-color: linear-gradient(180deg, #ffffff 0%, #e1f5fe 100%);
    color: #01579b;
    border-bottom: 1px solid #b3e5fc;
}
QMenuBar::item:selected {
    background-color: #81d4fa;
    color: #01579b;
}
QMenu {
    background-color: white;
    color: #01579b;
    border: 1px solid #b3e5fc;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #0288d1;
    color: white;
    border-radius: 4px;
}
QScrollArea {
    border: none;
    background-color: #f5fbff;
}
QScrollBar:vertical {
    background: #e1f5fe;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: linear-gradient(180deg, #81d4fa 0%, #29b6f6 100%);
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: linear-gradient(180deg, #4fc3f7 0%, #0288d1 100%);
}
"""

# ====================================================================
# 森林绿主题 - 自然清新的绿色
# ====================================================================
FOREST_GREEN_STYLE = """
QMainWindow {
    background-color: #e8f5e9;
}
QDialog {
    background-color: #e8f5e9;
    color: #1b5e20;
}
QToolBar {
    background-color: linear-gradient(90deg, #2e7d32 0%, #66bb6a 100%);
    border-bottom: 1px solid #c8e6c9;
    padding: 5px;
}
QComboBox {
    padding: 6px;
    border: 1px solid #a5d6a7;
    border-radius: 6px;
    background: white;
    color: #2e7d32;
}
QComboBox QAbstractItemView {
    background: white;
    color: #2e7d32;
    selection-background-color: #4caf50;
    selection-color: white;
}
QPushButton {
    padding: 8px 20px;
    border: 1px solid #a5d6a7;
    border-radius: 6px;
    background: linear-gradient(180deg, #ffffff 0%, #e8f5e9 100%);
    color: #2e7d32;
    font-weight: 500;
}
QPushButton:hover {
    background: linear-gradient(180deg, #e8f5e9 0%, #c8e6c9 100%);
    border-color: #4caf50;
}
QPushButton:default {
    background: linear-gradient(180deg, #66bb6a 0%, #2e7d32 100%);
    color: white;
    border-color: #2e7d32;
}
QPushButton:default:hover {
    background: linear-gradient(180deg, #81c784 0%, #388e3c 100%);
}
QTextEdit {
    border: 1px solid #a5d6a7;
    border-radius: 6px;
    background: white;
    padding: 10px;
    color: #1b5e20;
}
QLineEdit {
    border: 1px solid #a5d6a7;
    border-radius: 6px;
    background: white;
    padding: 6px;
    color: #1b5e20;
}
QLineEdit:focus {
    border-color: #4caf50;
    background: #f1f8e9;
}
QLabel {
    color: #1b5e20;
    font-weight: 500;
}
QGroupBox {
    border: 1px solid #c8e6c9;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    background: rgba(255,255,255,0.7);
    color: #1b5e20;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: #2e7d32;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #c8e6c9;
    border-radius: 8px;
    background: white;
}
QTabBar::tab {
    background: linear-gradient(180deg, #e8f5e9 0%, #c8e6c9 100%);
    color: #2e7d32;
    padding: 10px 20px;
    border: 1px solid #a5d6a7;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background: linear-gradient(180deg, #ffffff 0%, #e8f5e9 100%);
    border-bottom: 2px solid #4caf50;
}
QMessageBox {
    background-color: white;
    color: #1b5e20;
}
QProgressBar {
    border: 1px solid #a5d6a7;
    border-radius: 6px;
    background: #e8f5e9;
}
QProgressBar::chunk {
    background: linear-gradient(90deg, #66bb6a 0%, #2e7d32 100%);
    border-radius: 4px;
}
QStatusBar {
    background-color: linear-gradient(180deg, #e8f5e9 0%, #c8e6c9 100%);
    border-top: 1px solid #a5d6a7;
    color: #1b5e20;
}
QMenuBar {
    background-color: linear-gradient(180deg, #ffffff 0%, #e8f5e9 100%);
    color: #1b5e20;
    border-bottom: 1px solid #c8e6c9;
}
QMenuBar::item:selected {
    background-color: #c8e6c9;
    color: #1b5e20;
}
QMenu {
    background-color: white;
    color: #1b5e20;
    border: 1px solid #c8e6c9;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #4caf50;
    color: white;
    border-radius: 4px;
}
QScrollArea {
    border: none;
    background-color: #f1f8e9;
}
QScrollBar:vertical {
    background: #e8f5e9;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: linear-gradient(180deg, #a5d6a7 0%, #66bb6a 100%);
    border-radius: 5px;
    min-height: 30px;
}
"""

# ====================================================================
# 日落橙主题 - 温暖活力的橙红渐变
# ====================================================================
SUNSET_ORANGE_STYLE = """
QMainWindow {
    background-color: #fff3e0;
}
QDialog {
    background-color: #fff3e0;
    color: #bf360c;
}
QToolBar {
    background-color: linear-gradient(90deg, #f57c00 0%, #ff7043 100%);
    border-bottom: 1px solid #ffccbc;
    padding: 5px;
}
QComboBox {
    padding: 6px;
    border: 1px solid #ffab91;
    border-radius: 6px;
    background: white;
    color: #e65100;
}
QComboBox QAbstractItemView {
    background: white;
    color: #e65100;
    selection-background-color: #ff5722;
    selection-color: white;
}
QPushButton {
    padding: 8px 20px;
    border: 1px solid #ffab91;
    border-radius: 6px;
    background: linear-gradient(180deg, #ffffff 0%, #fff3e0 100%);
    color: #e65100;
    font-weight: 500;
}
QPushButton:hover {
    background: linear-gradient(180deg, #fff3e0 0%, #ffe0b2 100%);
    border-color: #ff7043;
}
QPushButton:default {
    background: linear-gradient(180deg, #ff7043 0%, #f57c00 100%);
    color: white;
    border-color: #e65100;
}
QPushButton:default:hover {
    background: linear-gradient(180deg, #ff8a65 0%, #fb8c00 100%);
}
QTextEdit {
    border: 1px solid #ffab91;
    border-radius: 6px;
    background: white;
    padding: 10px;
    color: #bf360c;
}
QLineEdit {
    border: 1px solid #ffab91;
    border-radius: 6px;
    background: white;
    padding: 6px;
    color: #bf360c;
}
QLineEdit:focus {
    border-color: #ff5722;
    background: #fff8e1;
}
QLabel {
    color: #bf360c;
    font-weight: 500;
}
QGroupBox {
    border: 1px solid #ffccbc;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    background: rgba(255,255,255,0.7);
    color: #bf360c;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: #e65100;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #ffccbc;
    border-radius: 8px;
    background: white;
}
QTabBar::tab {
    background: linear-gradient(180deg, #fff3e0 0%, #ffccbc 100%);
    color: #e65100;
    padding: 10px 20px;
    border: 1px solid #ffab91;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background: linear-gradient(180deg, #ffffff 0%, #fff3e0 100%);
    border-bottom: 2px solid #ff5722;
}
QMessageBox {
    background-color: white;
    color: #bf360c;
}
QProgressBar {
    border: 1px solid #ffab91;
    border-radius: 6px;
    background: #fff3e0;
}
QProgressBar::chunk {
    background: linear-gradient(90deg, #ff7043 0%, #f57c00 100%);
    border-radius: 4px;
}
QStatusBar {
    background-color: linear-gradient(180deg, #fff3e0 0%, #ffccbc 100%);
    border-top: 1px solid #ffab91;
    color: #bf360c;
}
QMenuBar {
    background-color: linear-gradient(180deg, #ffffff 0%, #fff3e0 100%);
    color: #bf360c;
    border-bottom: 1px solid #ffccbc;
}
QMenuBar::item:selected {
    background-color: #ffccbc;
    color: #bf360c;
}
QMenu {
    background-color: white;
    color: #bf360c;
    border: 1px solid #ffccbc;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #ff5722;
    color: white;
    border-radius: 4px;
}
QScrollArea {
    border: none;
    background-color: #fff8e1;
}
"""

# ====================================================================
# 紫色梦幻主题 - 优雅神秘的紫色渐变
# ====================================================================
PURPLE_DREAM_STYLE = """
QMainWindow {
    background-color: #f3e5f5;
}
QDialog {
    background-color: #f3e5f5;
    color: #4a148c;
}
QToolBar {
    background-color: linear-gradient(90deg, #7b1fa2 0%, #ab47bc 100%);
    border-bottom: 1px solid #e1bee7;
    padding: 5px;
}
QComboBox {
    padding: 6px;
    border: 1px solid #ce93d8;
    border-radius: 6px;
    background: white;
    color: #6a1b9a;
}
QComboBox QAbstractItemView {
    background: white;
    color: #6a1b9a;
    selection-background-color: #9c27b0;
    selection-color: white;
}
QPushButton {
    padding: 8px 20px;
    border: 1px solid #ce93d8;
    border-radius: 6px;
    background: linear-gradient(180deg, #ffffff 0%, #f3e5f5 100%);
    color: #6a1b9a;
    font-weight: 500;
}
QPushButton:hover {
    background: linear-gradient(180deg, #f3e5f5 0%, #e1bee7 100%);
    border-color: #ab47bc;
}
QPushButton:default {
    background: linear-gradient(180deg, #ab47bc 0%, #7b1fa2 100%);
    color: white;
    border-color: #6a1b9a;
}
QPushButton:default:hover {
    background: linear-gradient(180deg, #ba68c8 0%, #8e24aa 100%);
}
QTextEdit {
    border: 1px solid #ce93d8;
    border-radius: 6px;
    background: white;
    padding: 10px;
    color: #4a148c;
}
QLineEdit {
    border: 1px solid #ce93d8;
    border-radius: 6px;
    background: white;
    padding: 6px;
    color: #4a148c;
}
QLineEdit:focus {
    border-color: #9c27b0;
    background: #faf0ff;
}
QLabel {
    color: #4a148c;
    font-weight: 500;
}
QGroupBox {
    border: 1px solid #e1bee7;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    background: rgba(255,255,255,0.7);
    color: #4a148c;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: #6a1b9a;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #e1bee7;
    border-radius: 8px;
    background: white;
}
QTabBar::tab {
    background: linear-gradient(180deg, #f3e5f5 0%, #e1bee7 100%);
    color: #6a1b9a;
    padding: 10px 20px;
    border: 1px solid #ce93d8;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background: linear-gradient(180deg, #ffffff 0%, #f3e5f5 100%);
    border-bottom: 2px solid #9c27b0;
}
QMessageBox {
    background-color: white;
    color: #4a148c;
}
QProgressBar {
    border: 1px solid #ce93d8;
    border-radius: 6px;
    background: #f3e5f5;
}
QProgressBar::chunk {
    background: linear-gradient(90deg, #ab47bc 0%, #7b1fa2 100%);
    border-radius: 4px;
}
QStatusBar {
    background-color: linear-gradient(180deg, #f3e5f5 0%, #e1bee7 100%);
    border-top: 1px solid #ce93d8;
    color: #4a148c;
}
QMenuBar {
    background-color: linear-gradient(180deg, #ffffff 0%, #f3e5f5 100%);
    color: #4a148c;
    border-bottom: 1px solid #e1bee7;
}
QMenuBar::item:selected {
    background-color: #e1bee7;
    color: #4a148c;
}
QMenu {
    background-color: white;
    color: #4a148c;
    border: 1px solid #e1bee7;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #9c27b0;
    color: white;
    border-radius: 4px;
}
QScrollArea {
    border: none;
    background-color: #faf0ff;
}
"""

# ====================================================================
# 玫瑰粉主题 - 甜美温柔的粉色渐变
# ====================================================================
PINK_ROSE_STYLE = """
QMainWindow {
    background-color: #fce4ec;
}
QDialog {
    background-color: #fce4ec;
    color: #880e4f;
}
QToolBar {
    background-color: linear-gradient(90deg, #ec407a 0%, #f48fb1 100%);
    border-bottom: 1px solid #f8bbd9;
    padding: 5px;
}
QComboBox {
    padding: 6px;
    border: 1px solid #f48fb1;
    border-radius: 6px;
    background: white;
    color: #c2185b;
}
QComboBox QAbstractItemView {
    background: white;
    color: #c2185b;
    selection-background-color: #e91e63;
    selection-color: white;
}
QPushButton {
    padding: 8px 20px;
    border: 1px solid #f8bbd9;
    border-radius: 6px;
    background: linear-gradient(180deg, #ffffff 0%, #fce4ec 100%);
    color: #c2185b;
    font-weight: 500;
}
QPushButton:hover {
    background: linear-gradient(180deg, #fce4ec 0%, #f8bbd9 100%);
    border-color: #f48fb1;
}
QPushButton:default {
    background: linear-gradient(180deg, #f48fb1 0%, #ec407a 100%);
    color: white;
    border-color: #c2185b;
}
QPushButton:default:hover {
    background: linear-gradient(180deg, #f06292 0%, #d81b60 100%);
}
QTextEdit {
    border: 1px solid #f48fb1;
    border-radius: 6px;
    background: white;
    padding: 10px;
    color: #880e4f;
}
QLineEdit {
    border: 1px solid #f48fb1;
    border-radius: 6px;
    background: white;
    padding: 6px;
    color: #880e4f;
}
QLineEdit:focus {
    border-color: #e91e63;
    background: #fdf0f5;
}
QLabel {
    color: #880e4f;
    font-weight: 500;
}
QGroupBox {
    border: 1px solid #f8bbd9;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    background: rgba(255,255,255,0.7);
    color: #880e4f;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: #c2185b;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #f8bbd9;
    border-radius: 8px;
    background: white;
}
QTabBar::tab {
    background: linear-gradient(180deg, #fce4ec 0%, #f8bbd9 100%);
    color: #c2185b;
    padding: 10px 20px;
    border: 1px solid #f48fb1;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background: linear-gradient(180deg, #ffffff 0%, #fce4ec 100%);
    border-bottom: 2px solid #e91e63;
}
QMessageBox {
    background-color: white;
    color: #880e4f;
}
QProgressBar {
    border: 1px solid #f48fb1;
    border-radius: 6px;
    background: #fce4ec;
}
QProgressBar::chunk {
    background: linear-gradient(90deg, #f48fb1 0%, #ec407a 100%);
    border-radius: 4px;
}
QStatusBar {
    background-color: linear-gradient(180deg, #fce4ec 0%, #f8bbd9 100%);
    border-top: 1px solid #f48fb1;
    color: #880e4f;
}
QMenuBar {
    background-color: linear-gradient(180deg, #ffffff 0%, #fce4ec 100%);
    color: #880e4f;
    border-bottom: 1px solid #f8bbd9;
}
QMenuBar::item:selected {
    background-color: #f8bbd9;
    color: #880e4f;
}
QMenu {
    background-color: white;
    color: #880e4f;
    border: 1px solid #f8bbd9;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #e91e63;
    color: white;
    border-radius: 4px;
}
QScrollArea {
    border: none;
    background-color: #fdf0f5;
}
"""

# ====================================================================
# 极简白主题 - 纯净高端的现代极简风格
# ====================================================================
MINIMAL_WHITE_STYLE = """
QMainWindow {
    background-color: #fafafa;
}
QDialog {
    background-color: #fafafa;
    color: #212121;
}
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #eeeeee;
    padding: 8px;
}
QComboBox {
    padding: 8px 12px;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    background: white;
    color: #424242;
    font-size: 13px;
}
QComboBox:hover {
    border-color: #9e9e9e;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #757575;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background: white;
    color: #424242;
    selection-background-color: #212121;
    selection-color: white;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 4px;
}
QComboBox QAbstractItemView::item {
    padding: 8px 12px;
    border-radius: 4px;
}
QPushButton {
    padding: 10px 24px;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    background: white;
    color: #424242;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.3px;
}
QPushButton:hover {
    background: #f5f5f5;
    border-color: #bdbdbd;
}
QPushButton:default {
    background: #212121;
    color: white;
    border-color: #212121;
}
QPushButton:default:hover {
    background: #424242;
}
QTextEdit {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    background: white;
    padding: 12px;
    color: #212121;
    font-size: 13px;
}
QLineEdit {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    background: white;
    padding: 8px 12px;
    color: #212121;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: #212121;
    background: #fafafa;
}
QLineEdit::placeholder {
    color: #9e9e9e;
}
QLabel {
    color: #424242;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #eeeeee;
    border-radius: 12px;
    margin-top: 16px;
    padding-top: 12px;
    background: rgba(255,255,255,0.8);
    color: #424242;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 12px;
    color: #212121;
    font-size: 14px;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #eeeeee;
    border-radius: 12px;
    background: white;
}
QTabBar::tab {
    background: #f5f5f5;
    color: #757575;
    padding: 12px 24px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background: white;
    color: #212121;
    border-bottom: 2px solid #212121;
}
QTabBar::tab:hover:!selected {
    background: #eeeeee;
    color: #424242;
}
QMessageBox {
    background-color: white;
    color: #212121;
}
QProgressBar {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    background: #f5f5f5;
    height: 6px;
}
QProgressBar::chunk {
    background: #212121;
    border-radius: 3px;
}
QStatusBar {
    background-color: #ffffff;
    border-top: 1px solid #eeeeee;
    color: #757575;
    font-size: 12px;
}
QMenuBar {
    background-color: #ffffff;
    color: #424242;
    border-bottom: 1px solid #eeeeee;
    font-size: 13px;
}
QMenuBar::item:selected {
    background-color: #f5f5f5;
    color: #212121;
}
QMenu {
    background-color: white;
    color: #424242;
    border: 1px solid #eeeeee;
    border-radius: 8px;
    padding: 6px;
    font-size: 13px;
}
QMenu::item {
    padding: 8px 16px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #212121;
    color: white;
    border-radius: 4px;
}
QScrollArea {
    border: none;
    background-color: #fafafa;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::handle:vertical {
    background: #e0e0e0;
    border-radius: 4px;
    min-height: 40px;
}
QScrollBar::handle:vertical:hover {
    background: #bdbdbd;
}
"""

# ====================================================================
# 深蓝色主题 - 深邃优雅的深蓝系
# ====================================================================
DEEP_BLUE_STYLE = """
QMainWindow {
    background-color: #0d1b2a;
}
QDialog {
    background-color: #1b263b;
    color: #e0e1dd;
}
QToolBar {
    background-color: #1b263b;
    border-bottom: 1px solid #415a77;
    padding: 5px;
}
QComboBox {
    padding: 6px;
    border: 1px solid #415a77;
    border-radius: 6px;
    background: #1b263b;
    color: #e0e1dd;
}
QComboBox:hover {
    border-color: #778da9;
}
QComboBox QAbstractItemView {
    background: #1b263b;
    color: #e0e1dd;
    selection-background-color: #3a5a80;
    selection-color: #e0e1dd;
    border: 1px solid #415a77;
    border-radius: 6px;
}
QPushButton {
    padding: 8px 20px;
    border: 1px solid #415a77;
    border-radius: 6px;
    background: #1b263b;
    color: #e0e1dd;
    font-weight: 500;
}
QPushButton:hover {
    background: #2d3e50;
    border-color: #778da9;
}
QPushButton:default {
    background: linear-gradient(180deg, #3a5a80 0%, #2d4a6a 100%);
    color: #ffffff;
    border-color: #3a5a80;
}
QPushButton:default:hover {
    background: linear-gradient(180deg, #4a6a90 0%, #3a5a80 100%);
}
QTextEdit {
    border: 1px solid #415a77;
    border-radius: 6px;
    background: #1b263b;
    padding: 10px;
    color: #e0e1dd;
}
QLineEdit {
    border: 1px solid #415a77;
    border-radius: 6px;
    background: #1b263b;
    padding: 6px;
    color: #e0e1dd;
}
QLineEdit:focus {
    border-color: #778da9;
    background: #2d3e50;
}
QLabel {
    color: #e0e1dd;
    font-weight: 500;
}
QGroupBox {
    border: 1px solid #415a77;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    background: rgba(27, 38, 59, 0.8);
    color: #e0e1dd;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: #778da9;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #415a77;
    border-radius: 8px;
    background: #1b263b;
}
QTabBar::tab {
    background: #2d3e50;
    color: #778da9;
    padding: 10px 20px;
    border: 1px solid #415a77;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background: #1b263b;
    color: #e0e1dd;
    border-bottom: 2px solid #3a5a80;
}
QTabBar::tab:hover:!selected {
    background: #3a5a80;
    color: #e0e1dd;
}
QMessageBox {
    background-color: #1b263b;
    color: #e0e1dd;
}
QProgressBar {
    border: 1px solid #415a77;
    border-radius: 6px;
    background: #2d3e50;
}
QProgressBar::chunk {
    background: linear-gradient(90deg, #3a5a80 0%, #2d4a6a 100%);
    border-radius: 4px;
}
QStatusBar {
    background-color: #1b263b;
    border-top: 1px solid #415a77;
    color: #778da9;
}
QMenuBar {
    background-color: #1b263b;
    color: #e0e1dd;
    border-bottom: 1px solid #415a77;
}
QMenuBar::item:selected {
    background-color: #2d3e50;
    color: #e0e1dd;
}
QMenu {
    background-color: #1b263b;
    color: #e0e1dd;
    border: 1px solid #415a77;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 8px 16px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #3a5a80;
    color: #ffffff;
    border-radius: 4px;
}
QScrollArea {
    border: none;
    background-color: #0d1b2a;
}
QScrollBar:vertical {
    background: #1b263b;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #415a77;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #778da9;
}
"""

# ====================================================================
# 深棕色主题 - 温暖沉稳的深棕系
# ====================================================================
DEEP_BROWN_STYLE = """
QMainWindow {
    background-color: #1a1512;
}
QDialog {
    background-color: #2d2420;
    color: #e8dcc8;
}
QToolBar {
    background-color: #2d2420;
    border-bottom: 1px solid #4a3f38;
    padding: 5px;
}
QComboBox {
    padding: 6px;
    border: 1px solid #5d4e44;
    border-radius: 6px;
    background: #2d2420;
    color: #e8dcc8;
}
QComboBox:hover {
    border-color: #8b7355;
}
QComboBox QAbstractItemView {
    background: #2d2420;
    color: #e8dcc8;
    selection-background-color: #6b5344;
    selection-color: #e8dcc8;
    border: 1px solid #4a3f38;
    border-radius: 6px;
}
QPushButton {
    padding: 8px 20px;
    border: 1px solid #5d4e44;
    border-radius: 6px;
    background: #2d2420;
    color: #e8dcc8;
    font-weight: 500;
}
QPushButton:hover {
    background: #3d322c;
    border-color: #8b7355;
}
QPushButton:default {
    background: linear-gradient(180deg, #6b5344 0%, #5a4538 100%);
    color: #ffffff;
    border-color: #6b5344;
}
QPushButton:default:hover {
    background: linear-gradient(180deg, #7b6354 0%, #6b5344 100%);
}
QTextEdit {
    border: 1px solid #5d4e44;
    border-radius: 6px;
    background: #2d2420;
    padding: 10px;
    color: #e8dcc8;
}
QLineEdit {
    border: 1px solid #5d4e44;
    border-radius: 6px;
    background: #2d2420;
    padding: 6px;
    color: #e8dcc8;
}
QLineEdit:focus {
    border-color: #8b7355;
    background: #3d322c;
}
QLabel {
    color: #e8dcc8;
    font-weight: 500;
}
QGroupBox {
    border: 1px solid #5d4e44;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    background: rgba(45, 36, 32, 0.8);
    color: #e8dcc8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: #b8a080;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #5d4e44;
    border-radius: 8px;
    background: #2d2420;
}
QTabBar::tab {
    background: #3d322c;
    color: #b8a080;
    padding: 10px 20px;
    border: 1px solid #5d4e44;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background: #2d2420;
    color: #e8dcc8;
    border-bottom: 2px solid #6b5344;
}
QTabBar::tab:hover:!selected {
    background: #4a3f38;
    color: #e8dcc8;
}
QMessageBox {
    background-color: #2d2420;
    color: #e8dcc8;
}
QProgressBar {
    border: 1px solid #5d4e44;
    border-radius: 6px;
    background: #3d322c;
}
QProgressBar::chunk {
    background: linear-gradient(90deg, #6b5344 0%, #5a4538 100%);
    border-radius: 4px;
}
QStatusBar {
    background-color: #2d2420;
    border-top: 1px solid #4a3f38;
    color: #b8a080;
}
QMenuBar {
    background-color: #2d2420;
    color: #e8dcc8;
    border-bottom: 1px solid #4a3f38;
}
QMenuBar::item:selected {
    background-color: #3d322c;
    color: #e8dcc8;
}
QMenu {
    background-color: #2d2420;
    color: #e8dcc8;
    border: 1px solid #4a3f38;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 8px 16px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #6b5344;
    color: #ffffff;
    border-radius: 4px;
}
QScrollArea {
    border: none;
    background-color: #1a1512;
}
QScrollBar:vertical {
    background: #2d2420;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #5d4e44;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #8b7355;
}
"""

# 聊天组件专用颜色（供 chat.py 使用）

# 深色主题通用组件样式 - 会被附加到所有深色主题的样式表末尾
DARK_COMMON_STYLE = """
/* 通用容器组件 - 深色主题 */
QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
}
QFrame, QLabeledStackedWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
}
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    background-color: #2d2d2d;
    border: 1px solid #3e3e3e;
    border-radius: 4px;
}
/* 列表组件 */
QListWidget, QListView, QTreeWidget, QTreeView, QTableWidget, QTableView {
    background-color: #1e1a1a;
    color: #e0e0e0;
    border: 1px solid #3e3e3e;
    border-radius: 4px;
}
QListWidget::item, QListView::item, QTreeWidget::item {
    background-color: transparent;
    padding: 4px;
}
QListWidget::item:selected, QListView::item:selected,
QTreeWidget::item:selected, QTreeView::item:selected {
    background-color: #0078d4;
    color: white;
}
QListWidget::item:hover, QListView::item:hover,
QTreeWidget::item:hover, QTreeView::item:hover {
    background-color: #3e3e3e;
}
/* 表头 */
QHeaderView::section {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3e3e3e;
    padding: 4px;
}
/* 分隔器 */
QSplitter::handle {
    background-color: #3e3e3e;
}
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }
/* 停靠窗口 */
QDockWidget {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3e3e3e;
}
QDockWidget::title {
    background-color: #252525;
    padding: 4px;
    border: 1px solid #3e3e3e;
}
/* 工具箱 */
QToolBox::tab {
    background-color: #2d2d2d;
    color: #e0e0e0;
    padding: 6px;
    border: 1px solid #3e3e3e;
}
QToolBox::tab:selected {
    background-color: #1e1e1e;
    border-bottom: 2px solid #0078d4;
}
QToolBox::tab:hover {
    background-color: #3e3e3e;
}
/* 堆叠窗口 */
QStackedWidget {
    background-color: #1e1e1e;
}
/* 命令对话框专用 */
QDialog {
    background-color: #1e1e1e;
    color: #e0e0e0;
}
/* 附件面板 - 深色主题 */
#attachmentPanel, AttachmentPanel {
    background-color: #2d2d2d;
    border: 1px solid #3e3e3e;
    border-radius: 6px;
}
#attachmentPanel QPushButton, AttachmentPanel QPushButton {
    background-color: #3c3c3c;
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 4px;
}
#attachmentPanel QPushButton:hover, AttachmentPanel QPushButton:hover {
    background-color: #4a4a4a;
}
#attachmentPanel QListWidget, AttachmentPanel QListWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    border: 1px solid #3e3e3e;
    border-radius: 4px;
}
#attachmentPanel QListWidget::item, AttachmentPanel QListWidget::item {
    background-color: transparent;
    color: #e0e0e0;
}
#attachmentPanel QListWidget::item:hover, AttachmentPanel QListWidget::item:hover {
    background-color: #3c3c3c;
}
/* 附件面板内部组件 - 深色主题 */
#attachmentPanel QLabel, AttachmentPanel QLabel {
    background-color: transparent;
    color: #e0e0e0;
}
/* 文件卡片 - 深色主题 */
#fileCard, #documentCard, FileCard, DocumentCard {
    background-color: #2d2d2d;
    border: 1px solid #3e3e3e;
    border-radius: 8px;
    padding: 8px;
    margin: 2px 0px;
}
#fileCard:hover, #documentCard:hover, FileCard:hover, DocumentCard:hover {
    border-color: #0078d4;
    background-color: #3c3c3c;
}
#fileCard QLabel, #documentCard QLabel, FileCard QLabel, DocumentCard QLabel {
    background-color: transparent;
    color: #e0e0e0;
}
#fileCard QPushButton, #documentCard QPushButton, FileCard QPushButton, DocumentCard QPushButton {
    background-color: #3c3c3c;
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 4px;
}
#fileCard QPushButton:hover, #documentCard QPushButton:hover, FileCard QPushButton:hover, DocumentCard QPushButton:hover {
    background-color: #4a4a4a;
}
/* 卡片详细文字 */
#fileCard #detailLabel, #documentCard QLabel[detail="true"],
FileCard QLabel, DocumentCard QLabel {
    color: #a0a0a0;
}
/* 定时任务卡片 - 深色主题 */
#cronJobCard, CronJobCard {
    background-color: #2d2d2d;
    border: 1px solid #3e3e3e;
    border-radius: 8px;
    padding: 8px;
    margin: 2px 0px;
}
#cronJobCard:hover, CronJobCard:hover {
    border-color: #0078d4;
    background-color: #3c3c3c;
}
#cronJobCard QLabel, CronJobCard QLabel {
    background-color: transparent;
    color: #e0e0e0;
}
#cronJobCard QPushButton, CronJobCard QPushButton {
    background-color: #3c3c3c;
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 4px;
}
#cronJobCard QPushButton:hover, CronJobCard QPushButton:hover {
    background-color: #4a4a4a;
}
/* 任务状态标签 */
#cronJobCard #statusLabel, CronJobCard #statusLabel {
    padding: 2px 8px;
    border-radius: 4px;
}
#cronJobCard #statusLabel[status="active"], CronJobCard #statusLabel[status="active"] {
    background-color: #2e7d32;
    color: white;
}
#cronJobCard #statusLabel[status="paused"], CronJobCard #statusLabel[status="paused"] {
    background-color: #f57c00;
    color: white;
}
/* 详细文字 */
#cronJobCard #detailLabel, CronJobCard #detailLabel {
    color: #a0a0a0;
}
"""
THEME_COLORS = {
    Theme.LIGHT: {
        # 背景色
        "chat_bg": "#f0f2f5",
        "chat_bg_gradient": "linear-gradient(180deg, #f0f2f5 0%, #ffffff 100%)",
        # 用户气泡
        "user_bubble_bg": "#e0e0e0",
        "user_bubble_bg_gradient": "linear-gradient(135deg, #f0f0f0 0%, #d0d0d0 100%)",
        "user_bubble_text": "black",
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
        "user_bubble_bg": "#2d2d3a",
        "user_bubble_bg_gradient": "linear-gradient(135deg, #3d3d4a 0%, #2d2d3a 100%)",
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
    Theme.OCEAN_BLUE: {
        "chat_bg": "#e3f2fd",
        "chat_bg_gradient": "linear-gradient(180deg, #e3f2fd 0%, #bbdefb 100%)",
        "user_bubble_bg": "#b3e5fc",
        "user_bubble_bg_gradient": "linear-gradient(135deg, #e1f5fe 0%, #b3e5fc 100%)",
        "user_bubble_text": "black",
        "ai_bubble_bg": "white",
        "ai_bubble_text": "#01579b",
        "ai_bubble_border": "#81d4fa",
        "ai_bubble_shadow": "0 2px 8px rgba(2,136,209,0.15)",
        "code_bg": "#e1f5fe",
        "code_border": "#81d4fa",
        "code_header_bg": "#b3e5fc",
        "syntax_keyword": "#0277bd",
        "syntax_string": "#01579b",
        "syntax_comment": "#78909c",
        "syntax_function": "#00838f",
        "syntax_number": "#0277bd",
        "syntax_builtin": "#e65100",
        "think_bg": "#e1f5fe",
        "think_border": "#29b6f6",
        "think_text": "#0288d1",
        "tool_card_bg": "linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%)",
        "tool_card_border": "#81d4fa",
        "tool_name_color": "#0288d1",
        "blockquote_border": "#0288d1",
        "blockquote_text": "#546e7a",
        "link_color": "#0277bd",
        "scrollbar_bg": "#e1f5fe",
        "scrollbar_handle": "#81d4fa",
        "scrollbar_handle_hover": "#29b6f6",
    },
    Theme.FOREST_GREEN: {
        "chat_bg": "#e8f5e9",
        "chat_bg_gradient": "linear-gradient(180deg, #e8f5e9 0%, #c8e6c9 100%)",
        "user_bubble_bg": "#c8e6c9",
        "user_bubble_bg_gradient": "linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%)",
        "user_bubble_text": "black",
        "ai_bubble_bg": "white",
        "ai_bubble_text": "#1b5e20",
        "ai_bubble_border": "#a5d6a7",
        "ai_bubble_shadow": "0 2px 8px rgba(46,125,50,0.15)",
        "code_bg": "#e8f5e9",
        "code_border": "#a5d6a7",
        "code_header_bg": "#c8e6c9",
        "syntax_keyword": "#2e7d32",
        "syntax_string": "#1b5e20",
        "syntax_comment": "#78909c",
        "syntax_function": "#00695c",
        "syntax_number": "#2e7d32",
        "syntax_builtin": "#e65100",
        "think_bg": "#e8f5e9",
        "think_border": "#66bb6a",
        "think_text": "#2e7d32",
        "tool_card_bg": "linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%)",
        "tool_card_border": "#a5d6a7",
        "tool_name_color": "#2e7d32",
        "blockquote_border": "#2e7d32",
        "blockquote_text": "#546e7a",
        "link_color": "#2e7d32",
        "scrollbar_bg": "#e8f5e9",
        "scrollbar_handle": "#a5d6a7",
        "scrollbar_handle_hover": "#66bb6a",
    },
    Theme.SUNSET_ORANGE: {
        "chat_bg": "#fff3e0",
        "chat_bg_gradient": "linear-gradient(180deg, #fff3e0 0%, #ffe0b2 100%)",
        "user_bubble_bg": "#ffe0b2",
        "user_bubble_bg_gradient": "linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%)",
        "user_bubble_text": "black",
        "ai_bubble_bg": "white",
        "ai_bubble_text": "#bf360c",
        "ai_bubble_border": "#ffab91",
        "ai_bubble_shadow": "0 2px 8px rgba(245,124,0,0.15)",
        "code_bg": "#fff3e0",
        "code_border": "#ffab91",
        "code_header_bg": "#ffe0b2",
        "syntax_keyword": "#e65100",
        "syntax_string": "#bf360c",
        "syntax_comment": "#78909c",
        "syntax_function": "#d84315",
        "syntax_number": "#e65100",
        "syntax_builtin": "#bf360c",
        "think_bg": "#fff3e0",
        "think_border": "#ff7043",
        "think_text": "#f57c00",
        "tool_card_bg": "linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%)",
        "tool_card_border": "#ffab91",
        "tool_name_color": "#f57c00",
        "blockquote_border": "#f57c00",
        "blockquote_text": "#546e7a",
        "link_color": "#e65100",
        "scrollbar_bg": "#fff3e0",
        "scrollbar_handle": "#ffab91",
        "scrollbar_handle_hover": "#ff7043",
    },
    Theme.PURPLE_DREAM: {
        "chat_bg": "#f3e5f5",
        "chat_bg_gradient": "linear-gradient(180deg, #f3e5f5 0%, #e1bee7 100%)",
        "user_bubble_bg": "#e1bee7",
        "user_bubble_bg_gradient": "linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%)",
        "user_bubble_text": "black",
        "ai_bubble_bg": "white",
        "ai_bubble_text": "#4a148c",
        "ai_bubble_border": "#ce93d8",
        "ai_bubble_shadow": "0 2px 8px rgba(123,31,162,0.15)",
        "code_bg": "#f3e5f5",
        "code_border": "#ce93d8",
        "code_header_bg": "#e1bee7",
        "syntax_keyword": "#6a1b9a",
        "syntax_string": "#4a148c",
        "syntax_comment": "#78909c",
        "syntax_function": "#6a1b9a",
        "syntax_number": "#7b1fa2",
        "syntax_builtin": "#d81b60",
        "think_bg": "#f3e5f5",
        "think_border": "#ab47bc",
        "think_text": "#7b1fa2",
        "tool_card_bg": "linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%)",
        "tool_card_border": "#ce93d8",
        "tool_name_color": "#7b1fa2",
        "blockquote_border": "#7b1fa2",
        "blockquote_text": "#546e7a",
        "link_color": "#6a1b9a",
        "scrollbar_bg": "#f3e5f5",
        "scrollbar_handle": "#ce93d8",
        "scrollbar_handle_hover": "#ab47bc",
    },
    Theme.PINK_ROSE: {
        "chat_bg": "#fce4ec",
        "chat_bg_gradient": "linear-gradient(180deg, #fce4ec 0%, #f8bbd9 100%)",
        "user_bubble_bg": "#f8bbd9",
        "user_bubble_bg_gradient": "linear-gradient(135deg, #fce4ec 0%, #f8bbd9 100%)",
        "user_bubble_text": "black",
        "ai_bubble_bg": "white",
        "ai_bubble_text": "#880e4f",
        "ai_bubble_border": "#f48fb1",
        "ai_bubble_shadow": "0 2px 8px rgba(236,64,122,0.15)",
        "code_bg": "#fce4ec",
        "code_border": "#f48fb1",
        "code_header_bg": "#f8bbd9",
        "syntax_keyword": "#c2185b",
        "syntax_string": "#880e4f",
        "syntax_comment": "#78909c",
        "syntax_function": "#ad1457",
        "syntax_number": "#ec407a",
        "syntax_builtin": "#d81b60",
        "think_bg": "#fce4ec",
        "think_border": "#f48fb1",
        "think_text": "#ec407a",
        "tool_card_bg": "linear-gradient(135deg, #fce4ec 0%, #f8bbd9 100%)",
        "tool_card_border": "#f48fb1",
        "tool_name_color": "#ec407a",
        "blockquote_border": "#ec407a",
        "blockquote_text": "#546e7a",
        "link_color": "#c2185b",
        "scrollbar_bg": "#fce4ec",
        "scrollbar_handle": "#f48fb1",
        "scrollbar_handle_hover": "#f06292",
    },
    Theme.MINIMAL_WHITE: {
        "chat_bg": "#fafafa",
        "chat_bg_gradient": "linear-gradient(180deg, #fafafa 0%, #ffffff 100%)",
        "user_bubble_bg": "#e0e0e0",
        "user_bubble_bg_gradient": "linear-gradient(135deg, #f0f0f0 0%, #e0e0e0 100%)",
        "user_bubble_text": "black",
        "ai_bubble_bg": "white",
        "ai_bubble_text": "#212121",
        "ai_bubble_border": "#e0e0e0",
        "ai_bubble_shadow": "0 2px 8px rgba(0,0,0,0.06)",
        "code_bg": "#f5f5f5",
        "code_border": "#e0e0e0",
        "code_header_bg": "#eeeeee",
        "syntax_keyword": "#212121",
        "syntax_string": "#616161",
        "syntax_comment": "#9e9e9e",
        "syntax_function": "#424242",
        "syntax_number": "#757575",
        "syntax_builtin": "#212121",
        "think_bg": "#f5f5f5",
        "think_border": "#757575",
        "think_text": "#424242",
        "tool_card_bg": "linear-gradient(135deg, #fafafa 0%, #f5f5f5 100%)",
        "tool_card_border": "#e0e0e0",
        "tool_name_color": "#424242",
        "blockquote_border": "#9e9e9e",
        "blockquote_text": "#757575",
        "link_color": "#424242",
        "scrollbar_bg": "#f5f5f5",
        "scrollbar_handle": "#e0e0e0",
        "scrollbar_handle_hover": "#bdbdbd",
    },
    Theme.DEEP_BLUE: {
        "chat_bg": "#0a0f1a",
        "chat_bg_gradient": "linear-gradient(180deg, #0a0f1a 0%, #0c1424 100%)",
        "user_bubble_bg": "#1a2332",
        "user_bubble_bg_gradient": "linear-gradient(135deg, #2a3342 0%, #1a2332 100%)",
        "user_bubble_text": "white",
        "ai_bubble_bg": "#1b263b",
        "ai_bubble_text": "#e0e1dd",
        "ai_bubble_border": "#415a77",
        "ai_bubble_shadow": "0 2px 8px rgba(0,0,0,0.3)",
        "code_bg": "#1b263b",
        "code_border": "#415a77",
        "code_header_bg": "#2d3e50",
        "syntax_keyword": "#778da9",
        "syntax_string": "#e0e1dd",
        "syntax_comment": "#5d6d7e",
        "syntax_function": "#a8b9cc",
        "syntax_number": "#778da9",
        "syntax_builtin": "#b8a080",
        "think_bg": "#1b263b",
        "think_border": "#3a5a80",
        "think_text": "#778da9",
        "tool_card_bg": "linear-gradient(135deg, #1b263b 0%, #0d1b2a 100%)",
        "tool_card_border": "#415a77",
        "tool_name_color": "#778da9",
        "blockquote_border": "#415a77",
        "blockquote_text": "#778da9",
        "link_color": "#778da9",
        "scrollbar_bg": "#1b263b",
        "scrollbar_handle": "#415a77",
        "scrollbar_handle_hover": "#778da9",
    },
    Theme.DEEP_BROWN: {
        "chat_bg": "#0a0806",
        "chat_bg_gradient": "linear-gradient(180deg, #0a0806 0%, #12100e 100%)",
        "user_bubble_bg": "#2a2018",
        "user_bubble_bg_gradient": "linear-gradient(135deg, #3a2f25 0%, #2a2018 100%)",
        "user_bubble_text": "white",
        "ai_bubble_bg": "#2d2420",
        "ai_bubble_text": "#e8dcc8",
        "ai_bubble_border": "#5d4e44",
        "ai_bubble_shadow": "0 2px 8px rgba(0,0,0,0.3)",
        "code_bg": "#2d2420",
        "code_border": "#5d4e44",
        "code_header_bg": "#3d322c",
        "syntax_keyword": "#b8a080",
        "syntax_string": "#e8dcc8",
        "syntax_comment": "#8b7355",
        "syntax_function": "#d4c4a8",
        "syntax_number": "#b8a080",
        "syntax_builtin": "#c8a060",
        "think_bg": "#2d2420",
        "think_border": "#6b5344",
        "think_text": "#b8a080",
        "tool_card_bg": "linear-gradient(135deg, #2d2420 0%, #1a1512 100%)",
        "tool_card_border": "#5d4e44",
        "tool_name_color": "#b8a080",
        "blockquote_border": "#5d4e44",
        "blockquote_text": "#8b7355",
        "link_color": "#b8a080",
        "scrollbar_bg": "#2d2420",
        "scrollbar_handle": "#5d4e44",
        "scrollbar_handle_hover": "#8b7355",
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
    
    stylesheet_map = {
        Theme.LIGHT: LIGHT_STYLE,
        Theme.DARK: DARK_STYLE,
        Theme.OCEAN_BLUE: OCEAN_BLUE_STYLE,
        Theme.FOREST_GREEN: FOREST_GREEN_STYLE,
        Theme.SUNSET_ORANGE: SUNSET_ORANGE_STYLE,
        Theme.PURPLE_DREAM: PURPLE_DREAM_STYLE,
        Theme.PINK_ROSE: PINK_ROSE_STYLE,
        Theme.MINIMAL_WHITE: MINIMAL_WHITE_STYLE,
        Theme.DEEP_BLUE: DEEP_BLUE_STYLE,
        Theme.DEEP_BROWN: DEEP_BROWN_STYLE,
    }
    
    style = stylesheet_map.get(resolved, LIGHT_STYLE)
    
    # 深色主题附加通用组件样式
    dark_themes = {Theme.DARK, Theme.DEEP_BLUE, Theme.DEEP_BROWN}
    if resolved in dark_themes:
        style = style + DARK_COMMON_STYLE
    
    return style


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
