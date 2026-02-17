"""追问UI组件。

用于显示AI追问的选项选择、确认对话框等。
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class AskWidget(QWidget):
    """追问选择组件。

    显示选项按钮组、超时倒计时等。
    """

    # 信号
    option_selected = Signal(str)   # 选项被选中
    confirm_accepted = Signal()    # 确认通过
    confirm_rejected = Signal()    # 确认拒绝

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化追问组件。

        Args:
            parent: 父部件
        """
        super().__init__(parent)
        self._options: list[str] = []
        self._recommended: Optional[str] = None
        self._current_intent = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """设置UI。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 问题标签
        self._question_label = QLabel()
        self._question_label.setWordWrap(True)
        self._question_label.setFont(QFont("", 10))
        layout.addWidget(self._question_label)

        # 按钮容器
        self._button_layout = QHBoxLayout()
        self._button_layout.setSpacing(10)
        layout.addLayout(self._button_layout)

        # 超时提示
        self._timeout_label = QLabel()
        self._timeout_label.setStyleSheet("color: #888; font-size: 11px;")
        self._timeout_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._timeout_label)

        # 默认隐藏
        self.hide()

    def show_choice(
        self,
        question: str,
        options: list[str],
        recommended: Optional[str] = None,
        timeout_seconds: int = 30,
    ) -> None:
        """显示选项选择。

        Args:
            question: 问题文本
            options: 选项列表
            recommended: 推荐答案
            timeout_seconds: 超时秒数
        """
        self._options = options
        self._recommended = recommended

        # 设置问题
        self._question_label.setText(question)

        # 清除旧按钮
        while self._button_layout.count():
            item = self._button_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 创建选项按钮
        for option in options:
            btn = QPushButton(option)
            btn.setMinimumWidth(80)
            btn.setMaximumWidth(150)

            # 推荐答案样式
            if option == recommended:
                btn.setStyleSheet(
                    "QPushButton {"
                    "  background-color: #e3f2fd;"
                    "  border: 2px solid #2196f3;"
                    "  border-radius: 4px;"
                    "  padding: 6px 12px;"
                    "}"
                    "QPushButton:hover {"
                    "  background-color: #bbdefb;"
                    "}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton {"
                    "  background-color: #f5f5f5;"
                    "  border: 1px solid #ddd;"
                    "  border-radius: 4px;"
                    "  padding: 6px 12px;"
                    "}"
                    "QPushButton:hover {"
                    "  background-color: #e0e0e0;"
                    "}"
                )

            btn.clicked.connect(lambda checked, opt=option: self._on_option_clicked(opt))
            self._button_layout.addWidget(btn)

        # 添加跳过按钮
        skip_btn = QPushButton("跳过")
        skip_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #ffebee;"
            "  border: 1px solid #ffcdd2;"
            "  border-radius: 4px;"
            "  padding: 6px 12px;"
            "  color: #c62828;"
            "}"
        )
        skip_btn.clicked.connect(self._on_skip_clicked)
        self._button_layout.addWidget(skip_btn)

        # 设置超时提示
        self._timeout_label.setText(f"⏱️ 等待选择... ({timeout_seconds}秒超时将自动选择)")

        self.show()

    def show_confirm(
        self,
        question: str,
        timeout_seconds: int = 30,
    ) -> None:
        """显示确认对话框。

        Args:
            question: 确认问题
            timeout_seconds: 超时秒数
        """
        self._question_label.setText(question)

        # 清除旧按钮
        while self._button_layout.count():
            item = self._button_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 确认按钮
        confirm_btn = QPushButton("确认")
        confirm_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #4caf50;"
            "  border: none;"
            "  border-radius: 4px;"
            "  color: white;"
            "  padding: 8px 24px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #43a047;"
            "}"
        )
        confirm_btn.clicked.connect(self._on_confirm_clicked)
        self._button_layout.addWidget(confirm_btn)

        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #f5f5f5;"
            "  border: 1px solid #ddd;"
            "  border-radius: 4px;"
            "  padding: 8px 24px;"
            "}"
        )
        cancel_btn.clicked.connect(self._on_cancel_clicked)
        self._button_layout.addWidget(cancel_btn)

        # 超时提示
        self._timeout_label.setText(f"⏱️ 等待确认... ({timeout_seconds}秒超时将自动确认)")

        self.show()

    def show_input(
        self,
        question: str,
        timeout_seconds: int = 30,
    ) -> None:
        """显示输入提示。

        Args:
            question: 输入提示
            timeout_seconds: 超时秒数
        """
        self._question_label.setText(question)

        # 清除旧按钮
        while self._button_layout.count():
            item = self._button_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 添加"说完了"按钮
        done_btn = QPushButton("说完了")
        done_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #2196f3;"
            "  border: none;"
            "  border-radius: 4px;"
            "  color: white;"
            "  padding: 8px 24px;"
            "}"
        )
        done_btn.clicked.connect(self._on_done_clicked)
        self._button_layout.addWidget(done_btn)

        # 超时提示
        self._timeout_label.setText(f"⏱️ 请说话... ({timeout_seconds}秒无输入将跳过)")

        self.show()

    def update_countdown(self, remaining: int) -> None:
        """更新倒计时显示。

        Args:
            remaining: 剩余秒数
        """
        if remaining <= 5:
            self._timeout_label.setStyleSheet(
                "color: #f44336; font-size: 11px; font-weight: bold;"
            )
        self._timeout_label.setText(f"⏱️ 等待选择... ({remaining}秒超时)")

    def hide_widget(self) -> None:
        """隐藏组件。"""
        self.hide()
        # 清除旧按钮
        while self._button_layout.count():
            item = self._button_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ========== 私有方法 ==========

    def _on_option_clicked(self, option: str) -> None:
        """选项按钮点击。"""
        logger.info(f"用户选择: {option}")
        self.option_selected.emit(option)
        self.hide_widget()

    def _on_skip_clicked(self) -> None:
        """跳过按钮点击。"""
        logger.info("用户跳过")
        self.option_selected.emit("")
        self.hide_widget()

    def _on_confirm_clicked(self) -> None:
        """确认按钮点击。"""
        logger.info("用户确认")
        self.confirm_accepted.emit()
        self.hide_widget()

    def _on_cancel_clicked(self) -> None:
        """取消按钮点击。"""
        logger.info("用户取消")
        self.confirm_rejected.emit()
        self.hide_widget()

    def _on_done_clicked(self) -> None:
        """说完了按钮点击。"""
        logger.info("用户完成输入")
        self.option_selected.emit("__done__")
        self.hide_widget()


class AskDialog(QDialog):
    """追问对话框（可选的对话框模式）。"""

    # 信号
    option_selected = Signal(str)
    dialog_closed = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        modal: bool = True,
    ):
        """初始化追问对话框。

        Args:
            parent: 父部件
            modal: 是否模态
        """
        super().__init__(parent)
        self.setModal(modal)
        self._ask_widget = AskWidget(self)
        self._ask_widget.option_selected.connect(self.option_selected.emit)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """设置UI。"""
        layout = QVBoxLayout(self)
        layout.addWidget(self._ask_widget)

    def show_choice(
        self,
        question: str,
        options: list[str],
        recommended: Optional[str] = None,
        timeout_seconds: int = 30,
    ) -> None:
        """显示选项选择。"""
        self._ask_widget.show_choice(question, options, recommended, timeout_seconds)
        self.show()

    def show_confirm(
        self,
        question: str,
        timeout_seconds: int = 30,
    ) -> None:
        """显示确认。"""
        self._ask_widget.show_confirm(question, timeout_seconds)
        self.show()

    def closeEvent(self, event) -> None:
        """关闭事件。"""
        self.dialog_closed.emit()
        super().closeEvent(event)
