"""知识库管理对话框 — 管理 RAG 知识库中的文档。

功能：
- 显示已索引的文档列表
- 添加文档（文件选择或 URL 输入）
- 删除文档
- 测试搜索功能
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Optional

from PySide6.QtCore import Qt, Signal, QThread, QTimer
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
    QLineEdit,
    QTextEdit,
    QProgressBar,
    QFileDialog,
    QComboBox,
)

if TYPE_CHECKING:
    from src.tools.knowledge_rag import KnowledgeRAGTool

logger = logging.getLogger(__name__)


class DocumentCard(QFrame):
    """单个文档卡片组件。"""

    delete_requested = Signal(int)  # 请求删除文档
    view_requested = Signal(dict)  # 请求查看文档详情

    def __init__(self, doc_info: dict, parent=None):
        super().__init__(parent)
        self._doc_info = doc_info
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        # 样式由全局主题控制
        self.setObjectName("documentCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 图标
        file_type = self._doc_info.get("file_type", "unknown")
        icon_map = {
            "pdf": "📕",
            "docx": "📘",
            "url": "🌐",
            "image": "🖼️",
            "text": "📄",
        }
        icon_label = QLabel(icon_map.get(file_type, "📄"))
        icon_label.setFont(QFont("", 20))
        icon_label.setFixedWidth(36)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        # 中间信息区
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # 文件名
        name_label = QLabel(self._doc_info.get("filename", "未知"))
        name_label.setFont(QFont("", 10, QFont.Weight.Bold))
        name_label.setWordWrap(True)
        info_layout.addWidget(name_label)

        # 详细信息
        size = self._doc_info.get("size", 0)
        size_kb = size / 1024 if size else 0
        chunks = self._doc_info.get("chunk_count", 0)
        indexed = self._doc_info.get("indexed_at", "")

        detail_text = f"{file_type.upper()} · {size_kb:.1f} KB · {chunks} 个片段"
        if indexed:
            # 只显示日期
            date_part = indexed.split("T")[0] if "T" in indexed else indexed
            detail_text += f" · {date_part}"

        detail_label = QLabel(detail_text)
        detail_label.setStyleSheet("font-size: 11px;")
        info_layout.addWidget(detail_label)

        layout.addLayout(info_layout, stretch=1)

        # 查看按钮
        view_btn = QPushButton("查看")
        view_btn.setFixedWidth(60)
        view_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        view_btn.clicked.connect(self._on_view)
        layout.addWidget(view_btn)

        # 删除按钮
        delete_btn = QPushButton("🗑️ 删除")
        delete_btn.setFixedWidth(70)
        delete_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(delete_btn)

    def _on_view(self):
        """查看文档详情。"""
        self.view_requested.emit(self._doc_info)

    def _on_delete(self):
        doc_id = self._doc_info.get("id")
        if doc_id:
            self.delete_requested.emit(doc_id)


class ListDocumentsWorker(QThread):
    """后台列出文档的工作线程。"""

    finished = Signal(list)  # 文档列表

    def __init__(self, tool: "KnowledgeRAGTool"):
        super().__init__()
        self._tool = tool

    def run(self):
        try:
            import asyncio
            from src.tools.base import ToolResultStatus

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            result = loop.run_until_complete(
                self._tool.execute("list_documents", {"limit": 50})
            )

            loop.close()

            if result.status == ToolResultStatus.SUCCESS:
                docs = result.data.get("documents", []) if result.data else []
                self.finished.emit(docs)
            else:
                self.finished.emit([])

        except Exception as e:
            logger.error(f"列出文档失败: {e}")
            self.finished.emit([])


class DeleteDocumentWorker(QThread):
    """后台删除文档的工作线程。"""

    finished = Signal(bool, str)  # 成功标志, 消息

    def __init__(self, tool: "KnowledgeRAGTool", doc_id: int):
        super().__init__()
        self._tool = tool
        self._doc_id = doc_id

    def run(self):
        try:
            import asyncio
            from src.tools.base import ToolResultStatus

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            result = loop.run_until_complete(
                self._tool.execute("remove_document", {"document_id": self._doc_id})
            )

            loop.close()

            if result.status == ToolResultStatus.SUCCESS:
                self.finished.emit(True, "文档已删除")
            else:
                self.finished.emit(False, result.error or "删除失败")

        except Exception as e:
            self.finished.emit(False, str(e))


class AddDocumentWorker(QThread):
    """后台添加文档的工作线程。"""

    finished = Signal(bool, str)  # 成功标志, 消息
    progress = Signal(str)  # 进度消息
    progress_percent = Signal(int, str)  # 百分比, 进度消息

    def __init__(self, tool: "KnowledgeRAGTool", file_path: str = "", url: str = ""):
        super().__init__()
        self._tool = tool
        self._file_path = file_path
        self._url = url

    def run(self):
        try:
            import asyncio
            from src.tools.base import ToolResultStatus

            self.progress_percent.emit(10, "正在解析文档...")

            # 异步执行
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            if self._file_path:
                self.progress_percent.emit(30, "正在解析文档...")
                result = loop.run_until_complete(
                    self._tool.execute("add_document", {"file_path": self._file_path})
                )
            else:
                self.progress_percent.emit(30, "正在解析网页...")
                result = loop.run_until_complete(
                    self._tool.execute("add_document", {"url": self._url})
                )

            loop.close()

            if result.status == ToolResultStatus.SUCCESS:
                self.progress_percent.emit(90, "正在完成...")
                self.finished.emit(True, result.output)
            else:
                self.finished.emit(False, result.error or "添加失败")

        except Exception as e:
            self.finished.emit(False, str(e))


class SearchWorker(QThread):
    """后台搜索的工作线程。"""

    finished = Signal(str)  # 搜索结果

    def __init__(self, tool: "KnowledgeRAGTool", query: str, top_k: int = 3):
        super().__init__()
        self._tool = tool
        self._query = query
        self._top_k = top_k
        self._is_cancelled = False

    def cancel(self):
        """取消搜索操作。"""
        self._is_cancelled = True

    def run(self):
        try:
            # 首先确保模型已加载（在主线程安全地预加载）
            # 这样可以避免在后台线程中加载 PyTorch 模型的问题
            try:
                # 访问 embedder 属性会触发模型加载
                _ = self._tool.embedder.model
            except Exception as e:
                logger.warning(f"预加载 embedding 模型时出现问题: {e}")

            # 检查是否被取消
            if self._is_cancelled:
                self.finished.emit("搜索已取消")
                return

            import asyncio
            from src.tools.base import ToolResultStatus

            # 使用较长的超时时间来确保模型加载完成
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 设置较长的超时时间
            import socket
            socket.setdefaulttimeout(300)  # 5分钟超时

            result = loop.run_until_complete(
                self._tool.execute("search", {"query": self._query, "top_k": self._top_k})
            )

            loop.close()

            # 检查是否被取消
            if self._is_cancelled:
                self.finished.emit("搜索已取消")
                return

            if result.status == ToolResultStatus.SUCCESS:
                self.finished.emit(result.output)
            else:
                self.finished.emit(f"搜索失败: {result.error}")

        except Exception as e:
            logger.error(f"搜索线程异常: {e}")
            self.finished.emit(f"搜索失败: {str(e)}")


class KnowledgeRAGDialog(QDialog):
    """知识库管理对话框。"""

    def __init__(self, tool: "KnowledgeRAGTool", parent=None):
        super().__init__(parent)
        self._tool = tool
        self._worker: Optional[AddDocumentWorker] = None
        self._search_worker: Optional[SearchWorker] = None
        self._list_worker: Optional[ListDocumentsWorker] = None
        self._delete_worker: Optional[DeleteDocumentWorker] = None
        self._all_docs: list = []  # 保存所有文档用于筛选排序
        self._setup_ui()
        self._refresh_documents()

    def _setup_ui(self):
        self.setWindowTitle("🧠 智能知识库管理")
        self.setMinimumSize(700, 550)
        self.resize(800, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 顶部标题
        title_label = QLabel("🧠 智能知识库")
        title_label.setFont(QFont("", 14, QFont.Weight.Bold))
        layout.addWidget(title_label)

        # 文档统计信息（增强版）
        self._count_label = QLabel("")
        self._count_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self._count_label)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # 添加文档区域
        add_layout = QHBoxLayout()
        add_layout.setSpacing(10)

        # 添加方式选择
        self._add_type_combo = QComboBox()
        self._add_type_combo.addItems(["添加文件", "添加网址"])
        self._add_type_combo.setFixedWidth(100)
        self._add_type_combo.currentTextChanged.connect(self._on_add_type_changed)
        add_layout.addWidget(self._add_type_combo)

        # 文件路径输入
        self._path_input = QLineEdit()
        self._path_input.setPlaceholderText("选择要添加的文档文件...")
        self._path_input.setMinimumWidth(300)
        add_layout.addWidget(self._path_input, stretch=1)

        # 浏览按钮
        self._browse_btn = QPushButton("浏览...")
        self._browse_btn.clicked.connect(self._on_browse_file)
        add_layout.addWidget(self._browse_btn)

        # 添加按钮
        self._add_btn = QPushButton("➕ 添加")
        self._add_btn.clicked.connect(self._on_add_document)
        add_layout.addWidget(self._add_btn)

        layout.addLayout(add_layout)

        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setMaximum(100)  # 百分比进度
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        layout.addWidget(self._progress_bar)

        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line2)

        # 搜索测试区域
        search_layout = QHBoxLayout()
        search_layout.setSpacing(10)

        search_label = QLabel("🔍 搜索测试:")
        search_layout.addWidget(search_label)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("输入搜索内容...")
        self._search_input.setMinimumWidth(300)
        self._search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._search_input, stretch=1)

        self._search_btn = QPushButton("搜索")
        self._search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(self._search_btn)

        layout.addLayout(search_layout)

        # 搜索结果区域
        self._search_result = QTextEdit()
        self._search_result.setReadOnly(True)
        self._search_result.setMaximumHeight(120)
        self._search_result.setPlaceholderText("搜索结果将显示在这里...")
        layout.addWidget(self._search_result)

        # 分隔线
        line3 = QFrame()
        line3.setFrameShape(QFrame.Shape.HLine)
        line3.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line3)

        # 文档列表标题
        doc_list_header_layout = QHBoxLayout()
        doc_list_label = QLabel("📚 已索引的文档")
        doc_list_label.setFont(QFont("", 11, QFont.Weight.Bold))
        doc_list_header_layout.addWidget(doc_list_label)

        doc_list_header_layout.addStretch()

        # 筛选器：按文档类型筛选
        filter_label = QLabel("筛选:")
        doc_list_header_layout.addWidget(filter_label)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems([
            "全部", "PDF", "DOCX", "XLSX", "PPTX", "TXT", "JSON", "CSV", "图片", "网页", "其他"
        ])
        self._filter_combo.setFixedWidth(100)
        self._filter_combo.currentTextChanged.connect(self._on_filter_changed)
        doc_list_header_layout.addWidget(self._filter_combo)

        # 排序器
        sort_label = QLabel("排序:")
        doc_list_header_layout.addWidget(sort_label)

        self._sort_combo = QComboBox()
        self._sort_combo.addItems([
            "索引时间降序",
            "索引时间升序",
            "名称升序",
            "名称降序",
            "大小降序",
            "大小升序",
        ])
        self._sort_combo.setFixedWidth(120)
        self._sort_combo.currentTextChanged.connect(self._on_sort_changed)
        doc_list_header_layout.addWidget(self._sort_combo)

        layout.addLayout(doc_list_header_layout)

        # 文档列表滚动区域
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._doc_list_widget = QWidget()
        self._doc_list_layout = QVBoxLayout(self._doc_list_widget)
        self._doc_list_layout.setContentsMargins(0, 0, 0, 0)
        self._doc_list_layout.setSpacing(6)

        self._scroll_area.setWidget(self._doc_list_widget)
        layout.addWidget(self._scroll_area, stretch=1)

        # 空状态提示
        self._empty_label = QLabel(
            "📭 知识库为空\n\n"
            "请添加文档到知识库，\n"
            "支持 PDF、DOCX、图片、网页等多种格式。"
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: gray; font-size: 13px; padding: 40px;")
        self._empty_label.setWordWrap(True)

        # 底部按钮栏
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self._refresh_documents)
        button_layout.addWidget(refresh_btn)

        button_layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # 初始状态
        self._on_add_type_changed("添加文件")

    def _on_add_type_changed(self, text: str):
        """添加类型改变。"""
        if text == "添加文件":
            self._path_input.setPlaceholderText("选择要添加的文档文件...")
            self._browse_btn.setVisible(True)
        else:
            self._path_input.setPlaceholderText("输入网页 URL...")
            self._browse_btn.setVisible(False)

    def _on_browse_file(self):
        """浏览文件。"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择文档",
            "",
            "所有支持的文件 (*.pdf *.docx *.doc *.txt *.md *.json *.csv *.jpg *.jpeg *.png);;"
            "PDF 文件 (*.pdf);;"
            "Word 文档 (*.docx *.doc);;"
            "文本文件 (*.txt *.md);;"
            "所有文件 (*.*)",
        )
        if file_path:
            self._path_input.setText(file_path)

    def _on_add_document(self):
        """添加文档。"""
        add_type = self._add_type_combo.currentText()

        if add_type == "添加文件":
            file_path = self._path_input.text().strip()
            if not file_path:
                QMessageBox.warning(self, "提示", "请选择要添加的文档文件")
                return

            if not os.path.exists(file_path):
                QMessageBox.warning(self, "提示", "文件不存在")
                return

            self._start_add_worker(file_path=file_path)
        else:
            url = self._path_input.text().strip()
            if not url:
                QMessageBox.warning(self, "提示", "请输入网页 URL")
                return

            if not url.startswith(("http://", "https://")):
                QMessageBox.warning(self, "提示", "请输入有效的 URL（以 http:// 或 https:// 开头）")
                return

            self._start_add_worker(url=url)

    def _start_add_worker(self, file_path: str = "", url: str = ""):
        """启动添加文档的后台工作。"""
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._add_btn.setEnabled(False)

        self._worker = AddDocumentWorker(self._tool, file_path=file_path, url=url)
        self._worker.progress.connect(self._on_add_progress)
        self._worker.progress_percent.connect(self._on_add_progress_percent)
        self._worker.finished.connect(self._on_add_finished)
        self._worker.start()

    def _on_add_progress(self, message: str):
        """添加进度更新。"""
        self._progress_bar.setFormat(message)

    def _on_add_progress_percent(self, percent: int, message: str):
        """添加进度百分比更新。"""
        self._progress_bar.setValue(percent)
        self._progress_bar.setFormat(f"{percent}% - {message}")

    def _on_add_finished(self, success: bool, message: str):
        """添加完成。"""
        self._progress_bar.setValue(100)
        self._progress_bar.setVisible(False)
        self._add_btn.setEnabled(True)
        self._path_input.clear()

        if success:
            QMessageBox.information(self, "成功", message)
            self._refresh_documents()
        else:
            QMessageBox.warning(self, "失败", message)

    def _on_search(self):
        """搜索。"""
        query = self._search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "提示", "请输入搜索内容")
            return

        self._search_btn.setEnabled(False)
        self._search_result.setText("搜索中...")

        # 在主线程中预加载 embedding 模型，避免在后台线程中加载 PyTorch 模型
        # 这是避免 QThread 与 PyTorch 多线程冲突的关键
        try:
            _ = self._tool.embedder.model
        except Exception as e:
            logger.warning(f"预加载模型时出现问题: {e}")

        # 取消之前的搜索线程（如果还在运行）
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.cancel()
            self._search_worker.quit()
            self._search_worker.wait(1000)

        self._search_worker = SearchWorker(self._tool, query, top_k=3)
        self._search_worker.finished.connect(self._on_search_finished)
        self._search_worker.start()

    def _on_search_finished(self, result: str):
        """搜索完成。"""
        self._search_btn.setEnabled(True)
        self._search_result.setText(result)

    def _refresh_documents(self):
        """刷新文档列表。"""
        self._list_worker = ListDocumentsWorker(self._tool)
        self._list_worker.finished.connect(self._populate_documents)
        self._list_worker.start()

    def _populate_documents(self, docs: list):
        """填充文档列表。"""
        # 保存所有文档用于筛选排序
        self._all_docs = docs

        # 清空现有卡片
        while self._doc_list_layout.count():
            item = self._doc_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # 计算增强统计信息
        self._update_statistics(docs)

        if not docs:
            self._doc_list_layout.addWidget(self._empty_label)
            self._empty_label.show()
            return

        self._empty_label.hide()

        # 应用筛选和排序
        filtered_docs = self._apply_filter_and_sort()

        # 添加文档卡片
        for doc in filtered_docs:
            card = DocumentCard(doc)
            card.delete_requested.connect(self._on_delete_document)
            card.view_requested.connect(self._on_view_document)
            self._doc_list_layout.addWidget(card)

        # 底部弹性空间
        self._doc_list_layout.addStretch()

    def _update_statistics(self, docs: list):
        """更新统计信息显示。"""
        if not docs:
            self._count_label.setText("共 0 个文档")
            return

        # 统计各类型数量
        type_counts = {}
        total_size = 0
        total_chunks = 0

        for doc in docs:
            file_type = doc.get("file_type", "unknown")
            # 映射类型名称
            if file_type in ("pdf",):
                type_name = "PDF"
            elif file_type in ("docx", "doc"):
                type_name = "DOCX"
            elif file_type in ("txt", "md", "text"):
                type_name = "TXT"
            elif file_type in ("jpg", "jpeg", "png", "gif", "webp", "bmp", "image"):
                type_name = "图片"
            elif file_type in ("url",):
                type_name = "网页"
            else:
                type_name = file_type.upper()

            type_counts[type_name] = type_counts.get(type_name, 0) + 1
            total_size += doc.get("size", 0)
            total_chunks += doc.get("chunk_count", 0)

        # 格式化总大小
        total_size_kb = total_size / 1024
        total_size_mb = total_size_kb / 1024
        if total_size_mb >= 1:
            size_str = f"{total_size_mb:.1f} MB"
        else:
            size_str = f"{total_size_kb:.0f} KB"

        # 构建统计字符串
        stat_parts = [f"共 {len(docs)} 个文档"]
        type_parts = []
        for t in ["PDF", "DOCX", "TXT", "图片", "网页"]:
            if t in type_counts:
                type_parts.append(f"{t}: {type_counts[t]}")

        if type_parts:
            stat_parts.append(" | ".join(type_parts))

        stat_parts.append(f"总大小: {size_str}")
        stat_parts.append(f"总片段数: {total_chunks:,}")

        self._count_label.setText(" | ".join(stat_parts))

    def _on_filter_changed(self, text: str):
        """筛选条件改变。"""
        self._refresh_documents()

    def _on_sort_changed(self, text: str):
        """排序条件改变。"""
        self._refresh_documents()

    def _apply_filter_and_sort(self) -> list:
        """应用筛选和排序。"""
        if not self._all_docs:
            return []

        # 获取当前筛选和排序条件
        filter_type = self._filter_combo.currentText()
        sort_type = self._sort_combo.currentText()

        # 筛选
        filtered = []
        for doc in self._all_docs:
            file_type = doc.get("file_type", "")

            if filter_type == "全部":
                filtered.append(doc)
            elif filter_type == "PDF":
                if file_type == "pdf":
                    filtered.append(doc)
            elif filter_type == "DOCX":
                if file_type in ("docx", "doc"):
                    filtered.append(doc)
            elif filter_type == "XLSX":
                if file_type in ("xlsx", "xls"):
                    filtered.append(doc)
            elif filter_type == "PPTX":
                if file_type in ("pptx", "ppt"):
                    filtered.append(doc)
            elif filter_type == "TXT":
                if file_type in ("txt", "md", "text", "markdown"):
                    filtered.append(doc)
            elif filter_type == "JSON":
                if file_type == "json":
                    filtered.append(doc)
            elif filter_type == "CSV":
                if file_type == "csv":
                    filtered.append(doc)
            elif filter_type == "图片":
                if file_type in ("jpg", "jpeg", "png", "gif", "webp", "bmp", "image"):
                    filtered.append(doc)
            elif filter_type == "网页":
                if file_type == "url":
                    filtered.append(doc)
            elif filter_type == "其他":
                # 其他类型：不在上面所有分类中的类型
                known_types = ("pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt",
                               "txt", "md", "text", "markdown", "json", "csv",
                               "jpg", "jpeg", "png", "gif", "webp", "bmp", "image", "url")
                if file_type not in known_types:
                    filtered.append(doc)

        # 排序
        if sort_type == "索引时间降序":
            filtered.sort(key=lambda x: x.get("indexed_at", ""), reverse=True)
        elif sort_type == "索引时间升序":
            filtered.sort(key=lambda x: x.get("indexed_at", ""))
        elif sort_type == "名称升序":
            filtered.sort(key=lambda x: x.get("filename", "").lower())
        elif sort_type == "名称降序":
            filtered.sort(key=lambda x: x.get("filename", "").lower(), reverse=True)
        elif sort_type == "大小降序":
            filtered.sort(key=lambda x: x.get("size", 0), reverse=True)
        elif sort_type == "大小升序":
            filtered.sort(key=lambda x: x.get("size", 0))

        return filtered

    def _on_view_document(self, doc_info: dict):
        """查看文档详情。"""
        from .document_detail_dialog import DocumentDetailDialog

        dlg = DocumentDetailDialog(doc_info, self)
        dlg.exec()

    def _on_delete_document(self, doc_id: int):
        """删除文档。"""
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要从知识库中删除此文档吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._delete_worker = DeleteDocumentWorker(self._tool, doc_id)
            self._delete_worker.finished.connect(self._on_delete_finished)
            self._delete_worker.start()

    def _on_delete_finished(self, success: bool, message: str):
        """删除完成。"""
        if success:
            QMessageBox.information(self, "成功", message)
            self._refresh_documents()
        else:
            QMessageBox.warning(self, "失败", message)

    def closeEvent(self, event):
        """关闭对话框时确保线程安全退出。"""
        # 等待添加文档线程结束
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)  # 最多等待3秒

        # 等待搜索线程结束
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.quit()
            self._search_worker.wait(3000)  # 最多等待3秒

        # 等待列出文档线程结束
        if hasattr(self, '_list_worker') and self._list_worker and self._list_worker.isRunning():
            self._list_worker.quit()
            self._list_worker.wait(3000)

        # 等待删除文档线程结束
        if hasattr(self, '_delete_worker') and self._delete_worker and self._delete_worker.isRunning():
            self._delete_worker.quit()
            self._delete_worker.wait(3000)

        event.accept()
