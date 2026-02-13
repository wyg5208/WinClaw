"""File 工具 — 文件读写与目录操作（Phase 1.3 增强版）。

增强内容：
- edit: 行级编辑（替换/插入/删除指定行范围）
- search: 文件内容搜索（支持正则表达式）
- tree: 目录树递归展示
- 大文件分页读取（start_line / end_line）
- 扩展名过滤（denied_extensions）
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


class FileTool(BaseTool):
    """文件读取、写入、编辑、搜索和目录树操作。"""

    name = "file"
    emoji = "📄"
    title = "文件操作"
    description = "读取、写入、编辑文件内容，搜索文件内容，列出目录结构"

    def __init__(
        self,
        max_read_size: int = 1_048_576,
        max_lines_per_page: int = 200,
        denied_extensions: list[str] | None = None,
    ):
        self.max_read_size = max_read_size  # 1MB
        self.max_lines_per_page = max_lines_per_page
        self.denied_extensions = denied_extensions or []

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="read",
                description="读取指定文件的内容。支持分页读取（指定起止行号）。",
                parameters={
                    "path": {
                        "type": "string",
                        "description": "文件的绝对路径或相对路径",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（从1开始，可选）",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号（包含，可选）",
                    },
                },
                required_params=["path"],
            ),
            ActionDef(
                name="write",
                description="将内容写入指定文件。如果文件不存在则创建，存在则覆盖。",
                parameters={
                    "path": {
                        "type": "string",
                        "description": "文件的绝对路径或相对路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文件内容",
                    },
                    "append": {
                        "type": "boolean",
                        "description": "是否追加模式（默认覆盖写入）",
                    },
                },
                required_params=["path", "content"],
            ),
            ActionDef(
                name="edit",
                description="行级编辑文件：替换、插入或删除指定行范围的内容。",
                parameters={
                    "path": {
                        "type": "string",
                        "description": "文件路径",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（从1开始）",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号（包含）。与 start_line 相同则替换单行。",
                    },
                    "new_content": {
                        "type": "string",
                        "description": "替换内容。为空字符串则删除指定行。",
                    },
                },
                required_params=["path", "start_line", "end_line", "new_content"],
            ),
            ActionDef(
                name="search",
                description="在文件中搜索内容。支持正则表达式。返回匹配的行号和内容。",
                parameters={
                    "path": {
                        "type": "string",
                        "description": "文件路径",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式（支持正则表达式）",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回结果数（默认50）",
                    },
                },
                required_params=["path", "pattern"],
            ),
            ActionDef(
                name="list",
                description="列出指定目录下的文件和子目录。",
                parameters={
                    "path": {
                        "type": "string",
                        "description": "目录的绝对路径或相对路径",
                    },
                },
                required_params=["path"],
            ),
            ActionDef(
                name="tree",
                description="递归展示目录树结构。",
                parameters={
                    "path": {
                        "type": "string",
                        "description": "目录路径",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "最大递归深度（默认3）",
                    },
                    "max_items": {
                        "type": "integer",
                        "description": "最大显示条目数（默认200）",
                    },
                },
                required_params=["path"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "read": self._read,
            "write": self._write,
            "edit": self._edit,
            "search": self._search,
            "list": self._list,
            "tree": self._tree,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return await handler(params)

    # ------------------------------------------------------------------
    # 扩展名安全检查
    # ------------------------------------------------------------------

    def _check_extension(self, path: Path) -> ToolResult | None:
        """检查文件扩展名是否被禁止。"""
        if self.denied_extensions:
            ext = path.suffix.lower()
            if ext in self.denied_extensions:
                return ToolResult(
                    status=ToolResultStatus.DENIED,
                    error=f"文件类型 '{ext}' 被安全策略禁止操作",
                )
        return None

    # ------------------------------------------------------------------
    # read（增强：分页读取）
    # ------------------------------------------------------------------

    async def _read(self, params: dict[str, Any]) -> ToolResult:
        path = Path(params["path"]).expanduser().resolve()
        if not path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"文件不存在: {path}",
            )
        if not path.is_file():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"路径不是文件: {path}",
            )

        ext_check = self._check_extension(path)
        if ext_check:
            return ext_check

        if path.stat().st_size > self.max_read_size:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"文件过大（{path.stat().st_size} 字节），超过限制 {self.max_read_size} 字节",
            )

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"读取文件失败: {e}",
            )

        start_line = params.get("start_line")
        end_line = params.get("end_line")

        if start_line is not None or end_line is not None:
            lines = content.splitlines(keepends=True)
            total_lines = len(lines)
            sl = max(1, start_line or 1)
            el = min(total_lines, end_line or (sl + self.max_lines_per_page - 1))

            selected = lines[sl - 1 : el]
            content = "".join(selected)
            header = f"[行 {sl}-{el} / 共 {total_lines} 行]\n"
            content = header + content

        logger.info("读取文件: %s (%d 字符)", path, len(content))
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=content,
            data={"path": str(path), "size": len(content)},
        )

    # ------------------------------------------------------------------
    # write
    # ------------------------------------------------------------------

    async def _write(self, params: dict[str, Any]) -> ToolResult:
        path = Path(params["path"]).expanduser().resolve()
        content = params.get("content", "")
        append = params.get("append", False)

        ext_check = self._check_extension(path)
        if ext_check:
            return ext_check

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(path, mode, encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"写入文件失败: {e}",
            )

        action_desc = "追加" if append else "写入"
        logger.info("%s文件: %s (%d 字符)", action_desc, path, len(content))
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已{action_desc}文件: {path} ({len(content)} 字符)",
            data={"path": str(path), "size": len(content)},
        )

    # ------------------------------------------------------------------
    # edit（新增：行级编辑）
    # ------------------------------------------------------------------

    async def _edit(self, params: dict[str, Any]) -> ToolResult:
        path = Path(params["path"]).expanduser().resolve()
        if not path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"文件不存在: {path}",
            )

        ext_check = self._check_extension(path)
        if ext_check:
            return ext_check

        start_line = params.get("start_line", 1)
        end_line = params.get("end_line", start_line)
        new_content = params.get("new_content", "")

        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"读取文件失败: {e}",
            )

        total_lines = len(lines)

        if start_line < 1 or start_line > total_lines + 1:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"起始行 {start_line} 超出范围（文件共 {total_lines} 行）",
            )
        if end_line < start_line:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"结束行 {end_line} 不能小于起始行 {start_line}",
            )

        # 构建新内容行
        new_lines = new_content.splitlines(keepends=True) if new_content else []
        # 如果新内容非空但最后没有换行，加上换行
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        # 替换行范围
        el = min(end_line, total_lines)
        result_lines = lines[: start_line - 1] + new_lines + lines[el:]

        try:
            path.write_text("".join(result_lines), encoding="utf-8")
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"写入文件失败: {e}",
            )

        deleted = el - start_line + 1
        inserted = len(new_lines)
        desc = f"替换行 {start_line}-{el}（删除 {deleted} 行，插入 {inserted} 行）"
        logger.info("编辑文件: %s — %s", path, desc)

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已编辑文件 {path}: {desc}，文件现有 {len(result_lines)} 行",
            data={"path": str(path), "lines": len(result_lines)},
        )

    # ------------------------------------------------------------------
    # search（新增：文件内搜索）
    # ------------------------------------------------------------------

    async def _search(self, params: dict[str, Any]) -> ToolResult:
        path = Path(params["path"]).expanduser().resolve()
        if not path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"文件不存在: {path}",
            )

        pattern_str = params.get("pattern", "")
        if not pattern_str:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="搜索模式不能为空",
            )

        max_results = params.get("max_results", 50)

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"读取文件失败: {e}",
            )

        try:
            regex = re.compile(pattern_str, re.IGNORECASE)
        except re.error as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"无效的正则表达式: {e}",
            )

        lines = content.splitlines()
        matches = []
        for i, line in enumerate(lines, 1):
            if regex.search(line):
                matches.append(f"  {i:>5}: {line.rstrip()}")
                if len(matches) >= max_results:
                    break

        if not matches:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"在 {path} 中未找到匹配 '{pattern_str}' 的内容",
                data={"path": str(path), "matches": 0},
            )

        header = f"在 {path} 中找到 {len(matches)} 处匹配:\n"
        output = header + "\n".join(matches)
        if len(matches) >= max_results:
            output += f"\n  ...(达到上限 {max_results}，可能还有更多)"

        logger.info("搜索文件: %s 匹配 '%s' → %d 处", path, pattern_str, len(matches))
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={"path": str(path), "matches": len(matches)},
        )

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    async def _list(self, params: dict[str, Any]) -> ToolResult:
        path = Path(params["path"]).expanduser().resolve()
        if not path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"目录不存在: {path}",
            )
        if not path.is_dir():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"路径不是目录: {path}",
            )

        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            lines = []
            for entry in entries[:100]:
                prefix = "📁" if entry.is_dir() else "📄"
                size_info = ""
                if entry.is_file():
                    size = entry.stat().st_size
                    if size < 1024:
                        size_info = f" ({size}B)"
                    elif size < 1_048_576:
                        size_info = f" ({size / 1024:.1f}KB)"
                    else:
                        size_info = f" ({size / 1_048_576:.1f}MB)"
                lines.append(f"{prefix} {entry.name}{size_info}")

            total = len(list(path.iterdir()))
            header = f"目录: {path} (共 {total} 项)\n"
            output = header + "\n".join(lines)
            if total > 100:
                output += f"\n...(仅显示前 100 项，共 {total} 项)"

        except PermissionError:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"无权限访问目录: {path}",
            )

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={"path": str(path), "count": total},
        )

    # ------------------------------------------------------------------
    # tree（新增：目录树）
    # ------------------------------------------------------------------

    async def _tree(self, params: dict[str, Any]) -> ToolResult:
        path = Path(params["path"]).expanduser().resolve()
        if not path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"目录不存在: {path}",
            )
        if not path.is_dir():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"路径不是目录: {path}",
            )

        max_depth = params.get("max_depth", 3)
        max_items = params.get("max_items", 200)

        lines: list[str] = [str(path)]
        count = [0]  # 用列表包装以便闭包修改

        def _walk(dir_path: Path, prefix: str, depth: int) -> None:
            if depth > max_depth or count[0] >= max_items:
                return
            try:
                entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except PermissionError:
                lines.append(f"{prefix}[无权限]")
                return

            for i, entry in enumerate(entries):
                if count[0] >= max_items:
                    lines.append(f"{prefix}...(已达 {max_items} 条上限)")
                    return
                is_last = i == len(entries) - 1
                connector = "└── " if is_last else "├── "
                size_info = ""
                if entry.is_file():
                    size = entry.stat().st_size
                    if size < 1024:
                        size_info = f" ({size}B)"
                    elif size < 1_048_576:
                        size_info = f" ({size / 1024:.1f}KB)"
                    else:
                        size_info = f" ({size / 1_048_576:.1f}MB)"
                lines.append(f"{prefix}{connector}{entry.name}{size_info}")
                count[0] += 1

                if entry.is_dir():
                    extension = "    " if is_last else "│   "
                    _walk(entry, prefix + extension, depth + 1)

        _walk(path, "", 1)
        output = "\n".join(lines)

        logger.info("目录树: %s (%d 项)", path, count[0])
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={"path": str(path), "items": count[0]},
        )
