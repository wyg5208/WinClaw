"""生成文件追踪管理器 — 记录 Agent 交互过程中生成的所有文件。

功能：
- 追踪所有工具调用产生的新文件（写入、编辑、截图、下载等）
- 将生成文件可选地复制到统一的"生成空间"文件夹
- 提供文件列表、分类、打开等能力
- 支持会话隔离（每次会话的生成文件独立跟踪）
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 生成空间默认根目录（位于 winclaw 项目根目录下）
_DEFAULT_SPACE_DIR = Path(__file__).resolve().parent.parent.parent / "generated"


@dataclass
class GeneratedFileInfo:
    """单个生成文件的元信息。"""

    path: str                     # 文件原始绝对路径
    name: str                     # 文件名
    source_tool: str = ""         # 来源工具名（如 file、shell、screen）
    source_action: str = ""       # 来源动作名（如 write、screenshot）
    file_type: str = "other"      # 文件类型: text/code/image/data/other
    size: int = 0                 # 文件大小（字节）
    created_at: str = ""          # 记录时间 ISO 格式
    session_id: str = ""          # 所属会话 ID
    copied_to: str = ""           # 复制到生成空间后的路径（空表示未复制）

    def size_display(self) -> str:
        """人类可读的文件大小。"""
        if self.size < 1024:
            return f"{self.size}B"
        elif self.size < 1_048_576:
            return f"{self.size / 1024:.1f}KB"
        else:
            return f"{self.size / 1_048_576:.1f}MB"

    def get_icon(self) -> str:
        """获取文件类型图标。"""
        icons = {
            "text": "📝",
            "code": "💻",
            "image": "🖼️",
            "data": "📊",
            "document": "📄",
            "audio": "🎵",
            "video": "🎬",
            "archive": "📦",
            "executable": "⚙️",
            "other": "📁",
        }
        return icons.get(self.file_type, "📁")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_generated_file_type(file_path: str) -> str:
    """根据扩展名检测生成文件的类型。"""
    ext = Path(file_path).suffix.lower()
    type_map = {
        # 文本
        ".txt": "text", ".md": "text", ".log": "text", ".csv": "text",
        ".rtf": "text", ".tex": "text", ".tsv": "text",
        # 代码
        ".py": "code", ".js": "code", ".ts": "code", ".java": "code",
        ".cpp": "code", ".c": "code", ".h": "code", ".hpp": "code",
        ".html": "code", ".htm": "code", ".xhtml": "code",
        ".css": "code", ".scss": "code", ".sass": "code", ".less": "code",
        ".json": "code", ".jsonl": "code", ".xml": "code", ".xsd": "code",
        ".yaml": "code", ".yml": "code", ".toml": "code", ".ini": "code",
        ".cfg": "code", ".conf": "code", ".config": "code",
        ".bat": "code", ".cmd": "code", ".ps1": "code", ".psm1": "code",
        ".sh": "code", ".bash": "code", ".zsh": "code", ".fish": "code",
        ".sql": "code", ".pls": "code", 
        ".php": "code", ".phtml": "code", ".php3": "code", ".php4": "code",
        ".rb": "code", ".erb": "code", ".rake": "code",
        ".go": "code", ".mod": "code", ".sum": "code",
        ".rs": "code", ".rlib": "code",
        ".swift": "code", ".kt": "code", ".kts": "code",
        ".scala": "code", ".sc": "code",
        ".dart": "code", ".groovy": "code", ".gradle": "code",
        ".lua": "code", ".tcl": "code",
        ".perl": "code", ".pl": "code", ".pm": "code",
        ".r": "code", ".rmd": "code",
        ".matlab": "code", ".m": "code",
        ".cs": "code", ".fs": "code", ".vb": "code",
        ".coffee": "code", ".elm": "code", ".erl": "code",
        ".ex": "code", ".exs": "code", ".clj": "code", ".cljs": "code",
        ".hs": "code", ".lhs": "code", ".ml": "code", ".mli": "code",
        ".jl": "code", ".nim": "code", ".cr": "code",
        # 图片
        ".png": "image", ".jpg": "image", ".jpeg": "image",
        ".bmp": "image", ".gif": "image", ".webp": "image", ".svg": "image",
        ".ico": "image", ".tiff": "image", ".tif": "image",
        ".psd": "image", ".ai": "image", ".eps": "image",
        # 数据
        ".xlsx": "data", ".xls": "data", ".xlsb": "data", ".xlsm": "data",
        ".db": "data", ".sqlite": "data", ".sqlite3": "data",
        ".parquet": "data", ".feather": "data", ".h5": "data", ".hdf5": "data",
        # 文档
        ".pdf": "document", ".doc": "document", ".docx": "document",
        ".pptx": "document", ".ppt": "document", ".potx": "document", ".ppsx": "document",
        ".odt": "document", ".ods": "document", ".odp": "document",
        # 音频
        ".mp3": "audio", ".wav": "audio", ".flac": "audio", ".aac": "audio",
        ".ogg": "audio", ".m4a": "audio", ".wma": "audio", ".opus": "audio",
        ".mid": "audio", ".midi": "audio", ".ape": "audio", ".dsf": "audio",
        # 视频
        ".mp4": "video", ".avi": "video", ".mkv": "video", ".mov": "video",
        ".wmv": "video", ".flv": "video", ".webm": "video", ".m4v": "video",
        ".mts": "video", ".m2ts": "video", ".vob": "video", ".rmvb": "video",
        # 压缩包
        ".zip": "archive", ".rar": "archive", ".7z": "archive", ".tar": "archive",
        ".gz": "archive", ".bz2": "archive", ".xz": "archive", ".lz": "archive",
        ".cab": "archive", ".iso": "archive",
        # 可执行文件
        ".exe": "executable", ".msi": "executable", ".dll": "executable",
        ".app": "executable", ".deb": "executable", ".rpm": "executable",
        ".apk": "executable", ".ipa": "executable",
        # 其他
        ".torrent": "other", ".nfo": "other", ".dmg": "other",
    }
    return type_map.get(ext, "other")


class GeneratedFilesManager:
    """生成文件追踪管理器。

    核心职责：
    1. 记录所有工具调用过程中新建/写入的文件
    2. 将文件复制到统一的"生成空间"文件夹
    3. 提供按类型、时间、会话等维度的查询
    """

    def __init__(
        self,
        space_dir: Path | None = None,
        auto_copy: bool = True,
    ):
        self._space_dir = space_dir or _DEFAULT_SPACE_DIR
        self._auto_copy = auto_copy
        self._files: list[GeneratedFileInfo] = []

        # 确保生成空间目录存在
        self._space_dir.mkdir(parents=True, exist_ok=True)

    @property
    def space_dir(self) -> Path:
        """生成空间根目录。"""
        return self._space_dir

    @property
    def files(self) -> list[GeneratedFileInfo]:
        """获取所有已追踪的生成文件列表（副本）。"""
        return self._files.copy()

    @property
    def count(self) -> int:
        return len(self._files)

    def register_file(
        self,
        file_path: str,
        source_tool: str = "",
        source_action: str = "",
        session_id: str = "",
    ) -> GeneratedFileInfo | None:
        """注册一个新生成的文件。

        Args:
            file_path: 文件的绝对路径
            source_tool: 来源工具名
            source_action: 来源动作名
            session_id: 会话 ID

        Returns:
            GeneratedFileInfo 如果注册成功，否则 None
        """
        path = Path(file_path).resolve()

        if not path.exists():
            logger.warning("注册生成文件失败: 文件不存在 %s", path)
            return None

        # 避免重复注册同一文件（按路径判断）
        str_path = str(path)
        for f in self._files:
            if f.path == str_path:
                # 已存在，更新信息
                f.size = path.stat().st_size
                f.created_at = datetime.now().isoformat(timespec="seconds")
                logger.info("更新已注册文件: %s", path.name)
                return f

        # 创建文件信息
        info = GeneratedFileInfo(
            path=str_path,
            name=path.name,
            source_tool=source_tool,
            source_action=source_action,
            file_type=detect_generated_file_type(str_path),
            size=path.stat().st_size,
            created_at=datetime.now().isoformat(timespec="seconds"),
            session_id=session_id,
        )

        # 自动复制到生成空间
        if self._auto_copy:
            copied_path = self._copy_to_space(path, info)
            if copied_path:
                info.copied_to = str(copied_path)

        self._files.append(info)
        logger.info(
            "已注册生成文件: %s (%s, %s.%s)",
            info.name, info.size_display(), source_tool, source_action,
        )
        return info

    def _copy_to_space(self, source: Path, info: GeneratedFileInfo) -> Path | None:
        """将文件复制到生成空间目录。"""
        try:
            # 按日期创建子目录
            date_dir = self._space_dir / datetime.now().strftime("%Y-%m-%d")
            date_dir.mkdir(parents=True, exist_ok=True)

            # 如果源文件已经在生成空间的子目录中，跳过复制
            if str(source).startswith(str(self._space_dir)):
                logger.debug("文件已在生成空间目录中，跳过复制: %s", source.name)
                return source

            # 处理文件名冲突
            dest = date_dir / source.name
            if dest.exists():
                stem = source.stem
                suffix = source.suffix
                counter = 1
                while dest.exists():
                    dest = date_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

            shutil.copy2(source, dest)
            logger.info("已复制到生成空间: %s → %s", source.name, dest)
            return dest

        except Exception as e:
            logger.warning("复制文件到生成空间失败: %s — %s", source.name, e)
            return None

    def scan_existing_files(self) -> int:
        """扫描生成空间目录中已存在的文件并添加到追踪列表。
        
        Returns:
            int: 新增的文件数量
        """
        if not self._space_dir.exists():
            return 0
            
        new_count = 0
        scanned_paths = {f.path for f in self._files}  # 避免重复扫描
        
        # 遍历所有日期子目录
        for date_dir in self._space_dir.iterdir():
            if not date_dir.is_dir():
                continue
                
            # 遍历目录中的所有文件
            for file_path in date_dir.iterdir():
                if not file_path.is_file():
                    continue
                    
                str_path = str(file_path)
                if str_path in scanned_paths:
                    continue  # 已经追踪过了
                    
                # 创建文件信息
                info = GeneratedFileInfo(
                    path=str_path,
                    name=file_path.name,
                    source_tool="historical",
                    source_action="scan",
                    file_type=detect_generated_file_type(str_path),
                    size=file_path.stat().st_size,
                    created_at=datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(timespec="seconds"),
                    session_id="",
                    copied_to=str_path,  # 已在生成空间中
                )
                
                self._files.append(info)
                scanned_paths.add(str_path)
                new_count += 1
                logger.debug("扫描到历史文件: %s", file_path.name)
                
        # 也要扫描根目录下的文件（不是按日期分类的旧文件）
        for file_path in self._space_dir.iterdir():
            if not file_path.is_file():
                continue
                
            str_path = str(file_path)
            if str_path in scanned_paths:
                continue
                
            info = GeneratedFileInfo(
                path=str_path,
                name=file_path.name,
                source_tool="historical",
                source_action="scan",
                file_type=detect_generated_file_type(str_path),
                size=file_path.stat().st_size,
                created_at=datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(timespec="seconds"),
                session_id="",
                copied_to=str_path,
            )
            
            self._files.append(info)
            scanned_paths.add(str_path)
            new_count += 1
            logger.debug("扫描到根目录文件: %s", file_path.name)
            
        if new_count > 0:
            logger.info("扫描完成，新增 %d 个历史文件", new_count)
            
        return new_count

    def get_files_by_type(self, file_type: str) -> list[GeneratedFileInfo]:
        """按文件类型筛选。"""
        return [f for f in self._files if f.file_type == file_type]

    def get_files_by_session(self, session_id: str) -> list[GeneratedFileInfo]:
        """按会话筛选。"""
        return [f for f in self._files if f.session_id == session_id]

    def clear(self) -> None:
        """清空追踪记录（不删除实际文件）。"""
        self._files.clear()

    def remove_file(self, file_path: str) -> bool:
        """移除指定文件的追踪记录（不删除实际文件）。

        Args:
            file_path: 文件路径

        Returns:
            True 如果移除成功，否则 False
        """
        for i, f in enumerate(self._files):
            if f.path == file_path:
                self._files.pop(i)
                return True
        return False

    def open_space_folder(self) -> bool:
        """在资源管理器中打开生成空间目录。"""
        try:
            os.startfile(str(self._space_dir))
            return True
        except Exception as e:
            logger.error("打开生成空间目录失败: %s", e)
            return False

    def open_file(self, file_path: str) -> bool:
        """用系统默认程序打开指定文件。"""
        try:
            os.startfile(file_path)
            return True
        except Exception as e:
            logger.error("打开文件失败: %s — %s", file_path, e)
            return False

    def get_summary(self) -> str:
        """获取当前生成文件摘要。"""
        if not self._files:
            return "暂无生成文件"

        type_counts: dict[str, int] = {}
        total_size = 0
        for f in self._files:
            type_counts[f.file_type] = type_counts.get(f.file_type, 0) + 1
            total_size += f.size

        parts = [f"共 {len(self._files)} 个文件"]
        for ft, cnt in sorted(type_counts.items()):
            parts.append(f"{ft}: {cnt}")

        if total_size < 1024:
            parts.append(f"总大小: {total_size}B")
        elif total_size < 1_048_576:
            parts.append(f"总大小: {total_size / 1024:.1f}KB")
        else:
            parts.append(f"总大小: {total_size / 1_048_576:.1f}MB")

        return " | ".join(parts)
