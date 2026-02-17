"""文档详情预览对话框。

功能：
- 显示文档元数据信息
- 显示解析内容预览
- 支持打开原文件、复制内容等操作
"""

from __future__ import annotations

import logging
import os
import subprocess
import webbrowser
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QClipboard
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QScrollArea,
    QWidget,
    QFrame,
    QMessageBox,
    QApplication,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QAbstractButton

logger = logging.getLogger(__name__)


class DocumentDetailDialog(QDialog):
    """文档详情预览对话框。"""

    def __init__(self, doc_info: dict, parent=None):
        super().__init__(parent)
        self._doc_info = doc_info
        self._setup_ui()

    def _setup_ui(self):
        """构建 UI。"""
        self.setWindowTitle(f"文档详情 - {self._doc_info.get('filename', '未知')}")
        self.setMinimumSize(600, 500)
        self.resize(650, 550)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ========== 文件元数据区域 ==========
        metadata_group = QFrame()
        metadata_group.setFrameShape(QFrame.Shape.StyledPanel)
        metadata_layout = QVBoxLayout(metadata_group)
        metadata_layout.setSpacing(8)

        # 标题
        title_label = QLabel("📄 文件信息")
        title_label.setFont(QFont("", 11, QFont.Weight.Bold))
        metadata_layout.addWidget(title_label)

        # 元数据表格
        metadata_grid = QVBoxLayout()
        metadata_grid.setSpacing(6)

        # 文件名
        filename = self._doc_info.get("filename", "未知")
        self._add_metadata_row(metadata_grid, "文件名:", filename)

        # 原始路径
        original_path = self._doc_info.get("original_path", "")
        self._add_metadata_row(metadata_grid, "原始路径:", original_path or "-")

        # 存储路径
        stored_path = self._doc_info.get("stored_path", "")
        self._add_metadata_row(metadata_grid, "存储路径:", stored_path or "-")

        # 文件大小
        size = self._doc_info.get("size", 0)
        size_kb = size / 1024 if size else 0
        size_mb = size_kb / 1024
        if size_mb >= 1:
            size_str = f"{size_mb:.2f} MB"
        elif size_kb >= 1:
            size_str = f"{size_kb:.1f} KB"
        else:
            size_str = f"{size} B"
        self._add_metadata_row(metadata_grid, "文件大小:", size_str)

        # 文件类型
        file_type = self._doc_info.get("file_type", "unknown")
        self._add_metadata_row(metadata_grid, "文件类型:", file_type.upper())

        # 索引时间
        indexed_at = self._doc_info.get("indexed_at", "")
        if indexed_at:
            # 格式化时间
            if "T" in indexed_at:
                date_part, time_part = indexed_at.split("T")
                time_part = time_part.split(".")[0] if "." in time_part else time_part
                indexed_at = f"{date_part} {time_part}"
        else:
            indexed_at = "-"
        self._add_metadata_row(metadata_grid, "索引时间:", indexed_at)

        # 片段数量
        chunk_count = self._doc_info.get("chunk_count", 0)
        self._add_metadata_row(metadata_grid, "文本片段:", f"{chunk_count} 个")

        metadata_layout.addLayout(metadata_grid)
        layout.addWidget(metadata_group)

        # ========== 内容预览区域 ==========
        content_group = QFrame()
        content_group.setFrameShape(QFrame.Shape.StyledPanel)
        content_layout = QVBoxLayout(content_group)
        content_layout.setSpacing(8)

        # 标题
        content_label = QLabel("📝 内容预览")
        content_label.setFont(QFont("", 11, QFont.Weight.Bold))
        content_layout.addWidget(content_label)

        # 内容文本框
        self._content_text = QTextEdit()
        self._content_text.setReadOnly(True)

        # 获取内容预览
        content_text = self._doc_info.get("content_text", "")
        if content_text:
            # 截取前500字作为预览
            preview_text = content_text[:500] if len(content_text) > 500 else content_text
            if len(content_text) > 500:
                preview_text += "\n\n... (内容过长，仅显示前500字)"
            self._content_text.setPlainText(preview_text)
        else:
            self._content_text.setPlainText("(无文本内容)")

        # 内容滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self._content_text)
        content_layout.addWidget(scroll_area)

        layout.addWidget(content_group, stretch=1)

        # ========== 按钮区域 ==========
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # 打开文件按钮（优先打开存储路径的文件）
        open_btn = QPushButton("📄 打开文件")
        open_btn.setToolTip("打开存储的知识库文件")
        open_btn.clicked.connect(self._on_open_file)
        button_layout.addWidget(open_btn)

        # 打开文件夹按钮
        open_folder_btn = QPushButton("📁 打开文件夹")
        open_folder_btn.setToolTip("打开文件所在文件夹")
        open_folder_btn.clicked.connect(self._on_open_folder)
        button_layout.addWidget(open_folder_btn)

        # 复制内容按钮
        copy_btn = QPushButton("📋 复制内容")
        copy_btn.clicked.connect(self._on_copy_content)
        button_layout.addWidget(copy_btn)

        button_layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _add_metadata_row(self, layout: QVBoxLayout, label: str, value: str):
        """添加一行元数据。"""
        row_layout = QHBoxLayout()
        row_layout.setSpacing(8)

        label_widget = QLabel(label)
        label_widget.setFixedWidth(80)
        label_widget.setStyleSheet("color: gray;")
        row_layout.addWidget(label_widget)

        value_widget = QLabel(value)
        value_widget.setWordWrap(True)
        row_layout.addWidget(value_widget, stretch=1)

        layout.addLayout(row_layout)

    def _get_best_file_path(self) -> tuple[str, str]:
        """获取最佳的文件路径。

        Returns:
            (文件路径, 文件来源描述)
        """
        original_path = self._doc_info.get("original_path", "")
        stored_path = self._doc_info.get("stored_path", "")

        # 优先检查存储路径
        if stored_path and os.path.exists(stored_path):
            return stored_path, "存储路径"

        # 其次检查原始路径
        if original_path and os.path.exists(original_path):
            return original_path, "原始路径"

        # 都不可用时返回存储路径（即使不存在）
        if stored_path:
            return stored_path, "存储路径(不存在)"

        return "", ""

    def _on_open_file(self):
        """打开文件。"""
        file_path, source = self._get_best_file_path()

        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(
                self,
                "文件不存在",
                f"文件不存在: {file_path}\n\n可能原因：\n1. 文件已被移动或删除\n2. 原始文件路径已变更",
            )
            return

        try:
            # 使用系统默认程序打开文件
            if os.name == "nt":  # Windows
                os.startfile(file_path)
            else:
                webbrowser.open(f"file://{file_path}")
        except Exception as e:
            logger.error(f"打开文件失败: {e}")
            QMessageBox.warning(
                self,
                "打开失败",
                f"无法打开文件: {str(e)}",
            )

    def _on_open_folder(self):
        """打开文件所在文件夹。"""
        file_path, source = self._get_best_file_path()

        if not file_path:
            QMessageBox.warning(
                self,
                "路径不存在",
                "文件路径信息不可用，无法打开文件夹。",
            )
            return

        # 获取文件所在目录
        folder_path = os.path.dirname(file_path)

        if not os.path.exists(folder_path):
            # 如果文件不存在，尝试使用存储路径的目录
            stored_path = self._doc_info.get("stored_path", "")
            if stored_path:
                folder_path = os.path.dirname(stored_path)
            else:
                QMessageBox.warning(
                    self,
                    "文件夹不存在",
                    f"文件夹不存在: {folder_path}",
                )
                return

        try:
            # 打开文件夹
            if os.name == "nt":  # Windows
                os.startfile(folder_path)
            else:
                webbrowser.open(f"file://{folder_path}")
        except Exception as e:
            logger.error(f"打开文件夹失败: {e}")
            QMessageBox.warning(
                self,
                "打开失败",
                f"无法打开文件夹: {str(e)}",
            )

    def _on_copy_content(self):
        """复制内容到剪贴板。"""
        content_text = self._doc_info.get("content_text", "")

        if not content_text:
            QMessageBox.information(
                self,
                "提示",
                "没有可复制的文本内容。",
            )
            return

        # 复制到剪贴板
        clipboard = QApplication.instance().clipboard()
        clipboard.setText(content_text)

        QMessageBox.information(
            self,
            "已复制",
            "内容已复制到剪贴板。",
        )
