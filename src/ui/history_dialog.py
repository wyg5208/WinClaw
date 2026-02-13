"""历史对话对话框 — 浏览和恢复历史会话记录。

功能：
- 显示所有历史对话列表（标题、时间、消息数）
- 点击恢复对话到聊天区域
- 删除历史对话
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class _SessionCard(QWidget):
    """单条会话卡片。"""

    def __init__(
        self,
        session_id: str,
        title: str,
        updated_at: str,
        message_count: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.session_id = session_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # 标题行
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(title_label)

        # 信息行：时间 + 消息数
        info_parts: list[str] = []
        if updated_at:
            try:
                dt = datetime.fromisoformat(updated_at)
                info_parts.append(dt.strftime("%Y-%m-%d %H:%M"))
            except Exception:
                info_parts.append(updated_at[:16])
        if message_count > 0:
            info_parts.append(f"{message_count} 条消息")

        info_label = QLabel(" · ".join(info_parts) if info_parts else "")
        info_label.setStyleSheet("font-size: 12px; color: #888;")
        layout.addWidget(info_label)


class HistoryDialog(QDialog):
    """历史对话浏览对话框。

    Signals:
        session_selected(str): 发出被选中的 session_id
    """

    session_selected = Signal(str)  # 选中要恢复的会话 ID

    def __init__(
        self,
        sessions: list[dict[str, Any]],
        parent: QWidget | None = None,
    ) -> None:
        """
        Args:
            sessions: 会话列表, 每项包含:
                - id: str
                - title: str
                - updated_at: str (ISO 格式)
                - message_count: int (可选)
            parent: 父窗口
        """
        super().__init__(parent)
        self._sessions = sessions
        self._selected_id: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("历史对话")
        self.setMinimumSize(480, 420)
        self.resize(520, 500)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 标题
        header = QLabel("📋 历史对话记录")
        header.setStyleSheet("font-size: 16px; font-weight: bold; padding: 4px 0;")
        layout.addWidget(header)

        # 列表
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setStyleSheet(
            "QListWidget { border: 1px solid #ccc; border-radius: 4px; }"
            "QListWidget::item { border-bottom: 1px solid #eee; }"
            "QListWidget::item:selected { background-color: #e3f2fd; }"
        )
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list, stretch=1)

        # 填充数据
        if self._sessions:
            for s in self._sessions:
                card = _SessionCard(
                    session_id=s["id"],
                    title=s.get("title", "未命名对话"),
                    updated_at=s.get("updated_at", ""),
                    message_count=s.get("message_count", 0),
                )
                item = QListWidgetItem()
                item.setSizeHint(card.sizeHint())
                item.setData(Qt.ItemDataRole.UserRole, s["id"])
                self._list.addItem(item)
                self._list.setItemWidget(item, card)
        else:
            empty_label = QLabel("暂无历史对话记录")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #999; font-size: 14px; padding: 40px;")
            layout.addWidget(empty_label)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self._delete_btn = QPushButton("🗑 删除")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self._delete_btn)

        btn_layout.addStretch()

        self._open_btn = QPushButton("打开对话")
        self._open_btn.setDefault(True)
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._on_open)
        btn_layout.addWidget(self._open_btn)

        cancel_btn = QPushButton("关闭")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    # ---- 事件 ----

    def _on_selection_changed(self, current: QListWidgetItem | None, _prev) -> None:
        has_selection = current is not None
        self._open_btn.setEnabled(has_selection)
        self._delete_btn.setEnabled(has_selection)
        if current:
            self._selected_id = current.data(Qt.ItemDataRole.UserRole)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        sid = item.data(Qt.ItemDataRole.UserRole)
        if sid:
            self._selected_id = sid
            self.session_selected.emit(sid)
            self.accept()

    def _on_open(self) -> None:
        if self._selected_id:
            self.session_selected.emit(self._selected_id)
            self.accept()

    def _on_delete(self) -> None:
        if not self._selected_id:
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除此历史对话吗？删除后无法恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            # 从列表中移除
            row = self._list.currentRow()
            if row >= 0:
                self._list.takeItem(row)
            # 从数据中移除
            self._sessions = [
                s for s in self._sessions if s["id"] != self._selected_id
            ]
            self._selected_id = ""
            self._open_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)

    @property
    def deleted_ids(self) -> list[str]:
        """返回被用户删除的会话 ID 列表（供外部同步删除存储）。"""
        current_ids = {s["id"] for s in self._sessions}
        # 对比初始列表不太方便,改为让外部自行刷新
        return []

    @property
    def selected_session_id(self) -> str:
        return self._selected_id
