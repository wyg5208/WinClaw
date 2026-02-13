"""Knowledge 工具 — 文档知识库（索引与检索）。

支持动作：
- search_documents: 搜索已索引的文档（按文件名或内容关键词）
- query_document_content: 查询文档内容片段（简易 RAG）

借鉴来源：参考项目_changoai/backend/tool_functions.py 文档检索相关函数
存储位置：~/.winclaw/winclaw_tools.db（documents 表）
文档存放：~/.winclaw/documents/（用户添加的文档副本）

设计说明：
- 采用 SQLite LIKE 搜索而非向量数据库，减少外部依赖
- 支持 .txt / .md / .json / .csv / .log 等纯文本文件
- 文档内容存入数据库，原文件可选保留在 documents/ 目录
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path.home() / ".winclaw" / "winclaw_tools.db"
_DOC_DIR = Path.home() / ".winclaw" / "documents"

# 支持索引的文件扩展名
_INDEXABLE_EXTS = {
    ".txt", ".md", ".json", ".csv", ".log", ".ini", ".cfg",
    ".yaml", ".yml", ".toml", ".xml", ".html", ".htm",
    ".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h",
}

# 最大索引文件大小 (2 MB)
_MAX_FILE_SIZE = 2 * 1024 * 1024


class KnowledgeTool(BaseTool):
    """文档知识库工具。

    支持将本地文本文件索引到知识库，
    然后通过关键词搜索文件名或内容片段。
    """

    name = "knowledge"
    emoji = "📚"
    title = "文档知识库"
    description = "索引本地文档并搜索内容，支持关键词检索和文档内容查询"

    def __init__(self, db_path: str = "", doc_dir: str = ""):
        super().__init__()
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB
        self._doc_dir = Path(doc_dir) if doc_dir else _DOC_DIR
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._doc_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._db_path))
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL UNIQUE,
                    file_size INTEGER DEFAULT 0,
                    content TEXT NOT NULL DEFAULT '',
                    indexed_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_filename
                ON documents(filename)
            """)
            conn.commit()

    # ------------------------------------------------------------------

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="index_document",
                description=(
                    "将本地文件索引到知识库。支持 .txt/.md/.json/.csv/.py 等文本文件。"
                    "索引后可通过 search_documents 搜索。"
                ),
                parameters={
                    "file_path": {
                        "type": "string",
                        "description": "要索引的文件绝对路径",
                    },
                },
                required_params=["file_path"],
            ),
            ActionDef(
                name="search_documents",
                description="搜索知识库中的文档，按文件名或内容关键词匹配",
                parameters={
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量，默认 10",
                    },
                },
                required_params=["query"],
            ),
            ActionDef(
                name="query_document_content",
                description=(
                    "查询指定文档中包含关键词的内容片段。"
                    "返回匹配行及其上下文。"
                ),
                parameters={
                    "document_name": {
                        "type": "string",
                        "description": "文档文件名（或部分名称）",
                    },
                    "question": {
                        "type": "string",
                        "description": "要查找的关键词或问题",
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "每个匹配点前后显示的行数，默认 3",
                    },
                },
                required_params=["document_name", "question"],
            ),
            ActionDef(
                name="list_documents",
                description="列出知识库中已索引的所有文档",
                parameters={
                    "limit": {
                        "type": "integer",
                        "description": "返回数量，默认 50",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="remove_document",
                description="从知识库中移除文档索引",
                parameters={
                    "document_id": {
                        "type": "integer",
                        "description": "文档 ID",
                    },
                },
                required_params=["document_id"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "index_document": self._index_document,
            "search_documents": self._search_documents,
            "query_document_content": self._query_document_content,
            "list_documents": self._list_documents,
            "remove_document": self._remove_document,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"不支持的动作: {action}")
        try:
            return handler(params)
        except Exception as e:
            logger.error("知识库操作失败: %s", e)
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))

    # ------------------------------------------------------------------

    def _index_document(self, params: dict[str, Any]) -> ToolResult:
        file_path_str = params.get("file_path", "").strip()
        if not file_path_str:
            return ToolResult(status=ToolResultStatus.ERROR, error="文件路径不能为空")

        fp = Path(file_path_str)
        if not fp.exists():
            return ToolResult(status=ToolResultStatus.ERROR, error=f"文件不存在: {fp}")
        if not fp.is_file():
            return ToolResult(status=ToolResultStatus.ERROR, error=f"不是文件: {fp}")
        if fp.suffix.lower() not in _INDEXABLE_EXTS:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的文件类型: {fp.suffix}。支持: {', '.join(sorted(_INDEXABLE_EXTS))}",
            )
        if fp.stat().st_size > _MAX_FILE_SIZE:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"文件过大 ({fp.stat().st_size / 1024:.0f} KB)，最大支持 {_MAX_FILE_SIZE // 1024} KB",
            )

        # 读取内容
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"读取文件失败: {e}")

        now = datetime.now().isoformat()
        filepath_key = str(fp.resolve())

        with self._conn() as conn:
            # 检查是否已索引（按路径去重）
            existing = conn.execute(
                "SELECT id FROM documents WHERE filepath = ?", (filepath_key,)
            ).fetchone()

            if existing:
                # 更新
                conn.execute("""
                    UPDATE documents SET filename=?, file_size=?, content=?, updated_at=?
                    WHERE filepath=?
                """, (fp.name, fp.stat().st_size, content, now, filepath_key))
                conn.commit()
                doc_id = existing[0]
                action_text = "已更新"
            else:
                # 新增
                cursor = conn.execute("""
                    INSERT INTO documents (filename, filepath, file_size, content, indexed_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (fp.name, filepath_key, fp.stat().st_size, content, now, now))
                conn.commit()
                doc_id = cursor.lastrowid
                action_text = "已索引"

        lines_count = content.count("\n") + 1
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"{action_text}: {fp.name} (ID:{doc_id}, {lines_count} 行, {fp.stat().st_size / 1024:.1f} KB)",
            data={
                "document_id": doc_id, "filename": fp.name,
                "lines": lines_count, "size_bytes": fp.stat().st_size,
            },
        )

    def _search_documents(self, params: dict[str, Any]) -> ToolResult:
        query = params.get("query", "").strip()
        limit = min(params.get("limit", 10), 50)

        if not query:
            return ToolResult(status=ToolResultStatus.ERROR, error="搜索关键词不能为空")

        pattern = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT id, filename, filepath, file_size,
                       SUBSTR(content, MAX(1, INSTR(LOWER(content), LOWER(?)) - 50), 200) as snippet
                FROM documents
                WHERE filename LIKE ? OR content LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, (query, pattern, pattern, limit)).fetchall()

        if not rows:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"未找到包含 '{query}' 的文档。",
                data={"results": [], "count": 0},
            )

        lines = [f"找到 {len(rows)} 个匹配文档："]
        data_list = []
        for i, (did, fname, fpath, fsize, snippet) in enumerate(rows, 1):
            snippet_clean = snippet.replace("\n", " ").strip() if snippet else ""
            if len(snippet_clean) > 150:
                snippet_clean = snippet_clean[:150] + "..."
            lines.append(f"  {i}. 📄 {fname} (ID:{did}, {fsize / 1024:.1f} KB)")
            if snippet_clean:
                lines.append(f"      ...{snippet_clean}...")
            data_list.append({
                "id": did, "filename": fname, "filepath": fpath,
                "size_bytes": fsize, "snippet": snippet_clean,
            })

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={"results": data_list, "count": len(data_list), "query": query},
        )

    def _query_document_content(self, params: dict[str, Any]) -> ToolResult:
        doc_name = params.get("document_name", "").strip()
        question = params.get("question", "").strip()
        context_lines = params.get("context_lines", 3)

        if not doc_name or not question:
            return ToolResult(status=ToolResultStatus.ERROR, error="文档名和关键词不能为空")

        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, filename, content FROM documents WHERE filename LIKE ? LIMIT 1",
                (f"%{doc_name}%",)
            ).fetchone()

        if not row:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"未找到匹配 '{doc_name}' 的文档，请先索引文件",
            )

        did, fname, content = row
        all_lines = content.split("\n")
        keyword_lower = question.lower()

        # 找到所有匹配行
        matches = []
        for idx, line in enumerate(all_lines):
            if keyword_lower in line.lower():
                start = max(0, idx - context_lines)
                end = min(len(all_lines), idx + context_lines + 1)
                snippet = "\n".join(
                    f"{'>>>' if j == idx else '   '} {j + 1}: {all_lines[j]}"
                    for j in range(start, end)
                )
                matches.append({"line_number": idx + 1, "snippet": snippet})

        if not matches:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"在 {fname} 中未找到包含 '{question}' 的内容。",
                data={"document": fname, "matches": [], "count": 0},
            )

        # 最多返回 5 个匹配
        shown = matches[:5]
        lines_out = [f"在 {fname} 中找到 {len(matches)} 处匹配："]
        for m in shown:
            lines_out.append(f"\n--- 第 {m['line_number']} 行 ---")
            lines_out.append(m["snippet"])

        if len(matches) > 5:
            lines_out.append(f"\n... 还有 {len(matches) - 5} 处匹配未显示")

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines_out),
            data={
                "document": fname, "document_id": did,
                "matches": [{"line": m["line_number"]} for m in shown],
                "total_matches": len(matches),
            },
        )

    def _list_documents(self, params: dict[str, Any]) -> ToolResult:
        limit = min(params.get("limit", 50), 200)

        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, filename, filepath, file_size, indexed_at FROM documents "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            ).fetchall()

        if not rows:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="知识库中暂无文档。可使用 index_document 添加文件。",
                data={"documents": [], "count": 0},
            )

        lines = [f"知识库中共 {len(rows)} 个文档："]
        data_list = []
        for i, (did, fname, fpath, fsize, indexed) in enumerate(rows, 1):
            lines.append(f"  {i}. 📄 {fname} (ID:{did}, {fsize / 1024:.1f} KB, 索引于 {indexed[:10]})")
            data_list.append({
                "id": did, "filename": fname, "filepath": fpath,
                "size_bytes": fsize, "indexed_at": indexed,
            })

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={"documents": data_list, "count": len(data_list)},
        )

    def _remove_document(self, params: dict[str, Any]) -> ToolResult:
        doc_id = params.get("document_id")
        if doc_id is None:
            return ToolResult(status=ToolResultStatus.ERROR, error="缺少 document_id")

        with self._conn() as conn:
            row = conn.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not row:
                return ToolResult(status=ToolResultStatus.ERROR, error=f"文档不存在: ID {doc_id}")
            fname = row[0]
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            conn.commit()

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已从知识库移除: {fname} (ID:{doc_id})",
            data={"document_id": doc_id, "deleted": True},
        )
