"""附件管理器 - 管理用户上传的文件附件。

功能:
- 管理附件列表（添加、删除、清空）
- 存储文件元信息（路径、类型、大小、名称）
- 提供附件摘要供 Agent 参考
- 文件类型自动检测
"""

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Signal


@dataclass
class AttachmentInfo:
    """附件信息数据类。"""
    
    path: str           # 文件完整路径
    name: str           # 文件名
    file_type: str      # 类型分类: image/text/code/document/other
    size: int           # 文件大小(字节)
    mime_type: str      # MIME 类型
    
    def size_display(self) -> str:
        """返回可读的文件大小。"""
        if self.size < 1024:
            return f"{self.size}B"
        elif self.size < 1024 * 1024:
            return f"{self.size / 1024:.1f}KB"
        else:
            return f"{self.size / (1024 * 1024):.1f}MB"
    
    def get_icon(self) -> str:
        """根据文件类型返回图标。"""
        icons = {
            "image": "🖼️",
            "text": "📄",
            "code": "📝",
            "document": "📑",
            "other": "📎",
        }
        return icons.get(self.file_type, "📎")


# 文件类型映射
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".ico", ".tiff", ".tif"}
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".yaml", ".yml", ".ini", ".conf", ".cfg"}
CODE_EXTENSIONS = {".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".hpp", ".cs", ".go", ".rs", ".rb", 
                   ".php", ".html", ".css", ".scss", ".less", ".sql", ".sh", ".bat", ".ps1", ".vue", ".jsx", ".tsx"}
DOCUMENT_EXTENSIONS = {".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".pdf", ".odt", ".ods", ".odp"}


def detect_file_type(file_path: str) -> str:
    """检测文件类型分类。"""
    ext = Path(file_path).suffix.lower()
    
    if ext in IMAGE_EXTENSIONS:
        return "image"
    elif ext in TEXT_EXTENSIONS:
        return "text"
    elif ext in CODE_EXTENSIONS:
        return "code"
    elif ext in DOCUMENT_EXTENSIONS:
        return "document"
    else:
        return "other"


def get_mime_type(file_path: str) -> str:
    """获取文件 MIME 类型。"""
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or "application/octet-stream"


class AttachmentManager(QObject):
    """附件管理器 - 管理用户上传的文件列表。"""
    
    # 信号
    attachment_added = Signal(AttachmentInfo)      # 添加附件
    attachment_removed = Signal(str)               # 删除附件 (path)
    attachments_cleared = Signal()                 # 清空所有附件
    attachments_changed = Signal(list)             # 附件列表变化
    
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._attachments: List[AttachmentInfo] = []
        self._max_attachments = 10  # 最大附件数量
        self._max_file_size = 50 * 1024 * 1024  # 50MB 单文件大小限制
    
    @property
    def attachments(self) -> List[AttachmentInfo]:
        """获取附件列表。"""
        return self._attachments.copy()
    
    @property
    def count(self) -> int:
        """获取附件数量。"""
        return len(self._attachments)
    
    def has_attachments(self) -> bool:
        """是否有附件。"""
        return len(self._attachments) > 0
    
    def add_file(self, file_path: str) -> tuple[bool, str]:
        """添加文件附件。
        
        Args:
            file_path: 文件路径
            
        Returns:
            (success, message) 元组
        """
        path = Path(file_path).resolve()
        
        # 检查文件是否存在
        if not path.exists():
            return False, f"文件不存在: {file_path}"
        
        if not path.is_file():
            return False, f"不是有效文件: {file_path}"
        
        # 检查文件大小
        file_size = path.stat().st_size
        if file_size > self._max_file_size:
            size_mb = file_size / (1024 * 1024)
            return False, f"文件过大: {size_mb:.1f}MB (限制 {self._max_file_size // (1024*1024)}MB)"
        
        # 检查附件数量
        if len(self._attachments) >= self._max_attachments:
            return False, f"附件数量已达上限 ({self._max_attachments})"
        
        # 检查是否已存在
        str_path = str(path)
        for att in self._attachments:
            if att.path == str_path:
                return False, "文件已添加"
        
        # 创建附件信息
        attachment = AttachmentInfo(
            path=str_path,
            name=path.name,
            file_type=detect_file_type(str_path),
            size=file_size,
            mime_type=get_mime_type(str_path),
        )
        
        self._attachments.append(attachment)
        self.attachment_added.emit(attachment)
        self.attachments_changed.emit(self._attachments.copy())
        
        return True, f"已添加: {attachment.name}"
    
    def add_files(self, file_paths: List[str]) -> tuple[int, List[str]]:
        """批量添加文件。
        
        Returns:
            (成功数量, 错误消息列表)
        """
        success_count = 0
        errors = []
        
        for path in file_paths:
            ok, msg = self.add_file(path)
            if ok:
                success_count += 1
            else:
                errors.append(msg)
        
        return success_count, errors
    
    def remove_file(self, file_path: str) -> bool:
        """删除指定附件。"""
        for i, att in enumerate(self._attachments):
            if att.path == file_path:
                self._attachments.pop(i)
                self.attachment_removed.emit(file_path)
                self.attachments_changed.emit(self._attachments.copy())
                return True
        return False
    
    def clear(self) -> None:
        """清空所有附件。"""
        if self._attachments:
            self._attachments.clear()
            self.attachments_cleared.emit()
            self.attachments_changed.emit([])
    
    def get_attachment(self, file_path: str) -> Optional[AttachmentInfo]:
        """获取指定路径的附件信息。"""
        for att in self._attachments:
            if att.path == file_path:
                return att
        return None
    
    def get_context_prompt(self) -> str:
        """生成附件上下文描述，供 Agent 参考。
        
        Returns:
            格式化的附件信息字符串
        """
        if not self._attachments:
            return ""
        
        lines = ["[附件信息]"]
        for att in self._attachments:
            type_desc = {
                "image": "图片",
                "text": "文本",
                "code": "代码",
                "document": "文档",
                "other": "文件",
            }.get(att.file_type, "文件")
            
            lines.append(f"- {att.name} ({type_desc}, {att.size_display()}, 路径: {att.path})")
        
        lines.append("")  # 空行分隔
        return "\n".join(lines)
    
    def get_files_by_type(self, file_type: str) -> List[AttachmentInfo]:
        """获取指定类型的附件列表。"""
        return [att for att in self._attachments if att.file_type == file_type]
    
    def get_image_files(self) -> List[AttachmentInfo]:
        """获取所有图片附件。"""
        return self.get_files_by_type("image")
    
    def get_text_files(self) -> List[AttachmentInfo]:
        """获取所有文本附件（包括代码）。"""
        return [att for att in self._attachments if att.file_type in ("text", "code")]
