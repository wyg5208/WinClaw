"""生成空间对话框 — 展示 Agent 交互过程中生成的所有文件。

功能：
- 以卡片列表形式展示生成的文件
- 按类型图标、文件名、大小、来源工具、时间排列
- 单击文件名可直接用系统默认程序打开
- "打开目录"按钮可在资源管理器中打开生成空间文件夹
- 支持清空记录
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QFrame,
    QMessageBox,
    QSizePolicy,
)

if TYPE_CHECKING:
    from src.core.generated_files import GeneratedFilesManager

logger = logging.getLogger(__name__)


class FileCard(QFrame):
    """单个文件卡片组件。"""

    file_open_requested = Signal(str)  # 请求打开文件

    def __init__(self, file_info, parent=None):
        super().__init__(parent)
        self._file_info = file_info
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setStyleSheet("""
            FileCard {
                background: palette(base);
                border: 1px solid palette(mid);
                border-radius: 8px;
                padding: 8px;
                margin: 2px 0px;
            }
            FileCard:hover {
                border-color: #0078d4;
                background: palette(alternateBase);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 图标
        icon_label = QLabel(self._file_info.get_icon())
        icon_label.setFont(QFont("", 20))
        icon_label.setFixedWidth(36)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        # 中间信息区
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # 文件名（可点击）
        name_label = QLabel(f"<a href='#'>{self._file_info.name}</a>")
        name_label.setFont(QFont("", 10, QFont.Weight.Bold))
        name_label.setTextFormat(Qt.TextFormat.RichText)
        name_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        name_label.linkActivated.connect(
            lambda: self.file_open_requested.emit(self._file_info.path)
        )
        name_label.setToolTip(f"点击打开: {self._file_info.path}")
        info_layout.addWidget(name_label)

        # 详细信息行
        detail_parts = []
        detail_parts.append(self._file_info.size_display())
        if self._file_info.source_tool:
            tool_desc = f"{self._file_info.source_tool}"
            if self._file_info.source_action:
                tool_desc += f".{self._file_info.source_action}"
            detail_parts.append(f"来源: {tool_desc}")
        if self._file_info.created_at:
            # 只显示时间部分
            time_part = self._file_info.created_at.split("T")[-1] if "T" in self._file_info.created_at else self._file_info.created_at
            detail_parts.append(time_part)

        detail_label = QLabel(" · ".join(detail_parts))
        detail_label.setStyleSheet("color: gray; font-size: 11px;")
        info_layout.addWidget(detail_label)

        # 路径行
        path_label = QLabel(self._file_info.path)
        path_label.setStyleSheet("color: gray; font-size: 10px;")
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        info_layout.addWidget(path_label)

        layout.addLayout(info_layout, stretch=1)

        # 打开按钮
        open_btn = QPushButton("打开")
        open_btn.setFixedWidth(60)
        open_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        open_btn.clicked.connect(
            lambda: self.file_open_requested.emit(self._file_info.path)
        )
        layout.addWidget(open_btn)


class GeneratedSpaceDialog(QDialog):
    """生成空间对话框。"""

    def __init__(self, manager: GeneratedFilesManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._setup_ui()
        self._populate_files()

    def _setup_ui(self):
        self.setWindowTitle("📂 生成空间 — AI 生成的文件")
        self.setMinimumSize(650, 480)
        self.resize(750, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 顶部标题 + 摘要
        header_layout = QHBoxLayout()
        title_label = QLabel("📂 生成空间")
        title_label.setFont(QFont("", 14, QFont.Weight.Bold))
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # 文件数量标签
        self._count_label = QLabel("")
        self._count_label.setStyleSheet("color: gray;")
        header_layout.addWidget(self._count_label)

        layout.addLayout(header_layout)

        # 摘要行
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self._summary_label)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # 文件列表滚动区域
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._file_list_widget = QWidget()
        self._file_list_layout = QVBoxLayout(self._file_list_widget)
        self._file_list_layout.setContentsMargins(0, 0, 0, 0)
        self._file_list_layout.setSpacing(6)

        self._scroll_area.setWidget(self._file_list_widget)
        layout.addWidget(self._scroll_area, stretch=1)

        # 空状态提示
        self._empty_label = QLabel(
            "🎉 尚未生成任何文件\n\n"
            "当 AI 在对话过程中创建或写入文件时，\n"
            "它们会自动出现在这里。"
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: gray; font-size: 13px; padding: 40px;")
        self._empty_label.setWordWrap(True)

        # 底部按钮栏
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # 打开生成空间文件夹
        open_folder_btn = QPushButton("📁 打开文件夹")
        open_folder_btn.setToolTip(f"在资源管理器中打开: {self._manager.space_dir}")
        open_folder_btn.clicked.connect(self._on_open_folder)
        button_layout.addWidget(open_folder_btn)

        # 刷新
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self._populate_files)
        button_layout.addWidget(refresh_btn)

        button_layout.addStretch()

        # 清空记录
        clear_btn = QPushButton("🗑️ 清空记录")
        clear_btn.clicked.connect(self._on_clear)
        button_layout.addWidget(clear_btn)

        # 关闭
        close_btn = QPushButton("关闭")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _populate_files(self):
        """填充文件列表。"""
        # 清空现有卡片
        while self._file_list_layout.count():
            item = self._file_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        files = self._manager.files

        # 更新统计
        self._count_label.setText(f"{len(files)} 个文件")
        self._summary_label.setText(self._manager.get_summary())

        if not files:
            self._file_list_layout.addWidget(self._empty_label)
            self._empty_label.show()
            return

        self._empty_label.hide()

        # 按时间倒序显示（最新的在前面）
        sorted_files = sorted(files, key=lambda f: f.created_at, reverse=True)

        for file_info in sorted_files:
            card = FileCard(file_info)
            card.file_open_requested.connect(self._on_open_file)
            self._file_list_layout.addWidget(card)

        # 底部弹性空间
        self._file_list_layout.addStretch()

    def _on_open_file(self, file_path: str):
        """打开文件。"""
        success = self._manager.open_file(file_path)
        if not success:
            QMessageBox.warning(
                self,
                "打开失败",
                f"无法打开文件:\n{file_path}\n\n文件可能已被删除或移动。",
            )

    def _on_open_folder(self):
        """打开生成空间文件夹。"""
        success = self._manager.open_space_folder()
        if not success:
            QMessageBox.warning(
                self,
                "打开失败",
                f"无法打开目录:\n{self._manager.space_dir}",
            )

    def _on_clear(self):
        """清空记录。"""
        if self._manager.count == 0:
            return

        reply = QMessageBox.question(
            self,
            "清空生成记录",
            f"确定清空 {self._manager.count} 条生成文件记录？\n\n"
            "注意：仅清空追踪记录，不会删除实际文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._manager.clear()
            self._populate_files()
