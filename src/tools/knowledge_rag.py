"""RAG 知识库工具 - 基于向量检索的智能知识库。

提供动作：
- add_document: 添加文档到知识库（解析 + 向量化 + 存储）
- search: 语义搜索知识库
- query_document: 查询指定文档内容
- list_documents: 列出知识库中的文档
- remove_document: 删除文档

依赖：
- chromadb: 向量数据库
- sentence-transformers: 本地 Embedding
- pymupdf4llm: PDF 解析
- python-docx: Word 解析
- beautifulsoup4: URL 解析

设计：
- 使用本地向量存储，保护数据隐私
- 支持多种文档格式
- 与现有 knowledge.py 工具共存
"""

import logging
import os
import shutil
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

# 默认配置
_DEFAULT_DB_DIR = os.path.expanduser("~/.winclaw")
_DOC_DIR = os.path.join(_DEFAULT_DB_DIR, "documents")
_VECTOR_DB_DIR = os.path.join(_DEFAULT_DB_DIR, "chroma_db")

# 支持的文件类型
_SUPPORTED_TYPES = {
    "pdf", "docx", "doc", "pptx", "ppt",
    "txt", "md", "markdown",
    "json", "csv", "xlsx", "xls",
    "jpg", "jpeg", "png", "gif", "webp", "bmp",
}

# 最大文件大小 (50MB)
_MAX_FILE_SIZE = 50 * 1024 * 1024


class KnowledgeRAGTool(BaseTool):
    """RAG 知识库工具。"""

    name = "knowledge_rag"
    emoji = "🧠"
    title = "智能知识库"
    description = "基于向量检索的智能知识库，支持 PDF/DOCX/图片/URL 等格式"

    def __init__(
        self,
        db_path: str = "",
        doc_dir: str = "",
        vector_db_dir: str = "",
        vision_client=None,
    ):
        """初始化 RAG 知识库工具。

        Args:
            db_path: SQLite 数据库路径（存储文档元数据）
            doc_dir: 文档存储目录
            vector_db_dir: ChromaDB 向量数据库目录
            vision_client: 视觉模型客户端（用于图片处理）
        """
        super().__init__()

        self._db_path = db_path or os.path.join(_DEFAULT_DB_DIR, "winclaw_rag.db")
        self._doc_dir = Path(doc_dir or _DOC_DIR)
        self._vector_db_dir = vector_db_dir or _VECTOR_DB_DIR

        self._doc_dir.mkdir(parents=True, exist_ok=True)

        # 初始化 RAG 组件
        self._embedder = None
        self._vector_store = None
        self._parser = None
        self._vision_client = vision_client

        # 初始化 SQLite
        self._init_db()

    @property
    def embedder(self):
        """获取嵌入器（延迟加载）。"""
        if self._embedder is None:
            from src.core.rag import Embedder
            self._embedder = Embedder()
        return self._embedder

    @property
    def vector_store(self):
        """获取向量存储（延迟加载）。"""
        if self._vector_store is None:
            from src.core.rag import VectorStore
            self._vector_store = VectorStore(
                db_path=self._vector_db_dir,
                embedding_function=self.embedder,
            )
        return self._vector_store

    @property
    def parser(self):
        """获取文档解析器。"""
        if self._parser is None:
            from src.core.rag import DocumentParser
            self._parser = DocumentParser(
                vision_client=self._vision_client,
            )
        return self._parser

    def _init_db(self) -> None:
        """初始化 SQLite 数据库。"""
        import sqlite3

        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    original_path TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    content_text TEXT,
                    chunk_count INTEGER DEFAULT 0,
                    indexed_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rag_filename
                ON rag_documents(filename)
            """)
            conn.commit()
        finally:
            conn.close()

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="add_document",
                description=(
                    "将文档添加到知识库。支持 PDF/DOCX/PPT/TXT/MD/JSON/CSV/图片等格式。"
                    "会自动解析文档内容、分块、向量化并存入向量数据库。"
                ),
                parameters={
                    "file_path": {
                        "type": "string",
                        "description": "要添加的文档路径（绝对路径）",
                    },
                    "url": {
                        "type": "string",
                        "description": "或者输入网页 URL（可选，与 file_path 二选一）",
                    },
                },
                required_params=["file_path"],
            ),
            ActionDef(
                name="search",
                description=(
                    "语义搜索知识库。根据用户问题检索相关文档内容。"
                    "返回与问题最相关的文档片段。"
                ),
                parameters={
                    "query": {
                        "type": "string",
                        "description": "搜索内容/问题",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量，默认 3",
                    },
                },
                required_params=["query"],
            ),
            ActionDef(
                name="query_document",
                description=(
                    "查询指定文档的内容。"
                    "根据关键词检索特定文档中的相关内容。"
                ),
                parameters={
                    "document_name": {
                        "type": "string",
                        "description": "文档名（支持模糊匹配）",
                    },
                    "query": {
                        "type": "string",
                        "description": "查询内容/问题",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量，默认 3",
                    },
                },
                required_params=["document_name", "query"],
            ),
            ActionDef(
                name="list_documents",
                description="列出知识库中的所有文档",
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
                description="从知识库中删除指定文档",
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
            "add_document": self._add_document,
            "search": self._search,
            "query_document": self._query_document,
            "list_documents": self._list_documents,
            "remove_document": self._remove_document,
        }

        handler = handlers.get(action)
        if handler is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )

        try:
            return handler(params)
        except Exception as e:
            import traceback
            logger.error(f"知识库操作失败: {e}\n{traceback.format_exc()}")
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))

    # -------------------- 动作实现 --------------------

    def _add_document(self, params: dict[str, Any]) -> ToolResult:
        """添加文档到知识库。"""
        file_path = params.get("file_path", "").strip()
        url = params.get("url", "").strip()

        now = datetime.now().isoformat()

        # 处理 URL
        if url:
            return self._add_url(url, now)

        # 处理文件
        if not file_path:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="必须提供 file_path 或 url",
            )

        fp = Path(file_path)

        # 验证文件
        if not fp.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"文件不存在: {file_path}",
            )

        if not fp.is_file():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不是文件: {file_path}",
            )

        ext = fp.suffix.lower().lstrip(".")
        if ext not in _SUPPORTED_TYPES:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的文件类型: {ext}，支持的类型: {', '.join(_SUPPORTED_TYPES)}",
            )

        file_size = fp.stat().st_size
        if file_size > _MAX_FILE_SIZE:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"文件过大: {file_size / 1024 / 1024:.1f}MB，最大支持 {_MAX_FILE_SIZE / 1024 / 1024}MB",
            )

        # 解析文档
        parse_result = self.parser.parse(file_path)

        if not parse_result.success:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"文档解析失败: {parse_result.error}",
            )

        # 检查解析内容是否为空
        if not parse_result.content or len(parse_result.content.strip()) == 0:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"文档解析成功但内容为空，可能是加密PDF或图片PDF，请尝试其他方式提取文字",
            )

        # 复制文件到存储目录
        stored_filename = f"{uuid.uuid4()}_{fp.name}"
        stored_path = self._doc_dir / stored_filename
        shutil.copy2(fp, stored_path)

        # 分块
        from src.core.rag import TextSplitter
        splitter = TextSplitter(chunk_size=1000, chunk_overlap=100)
        chunks = splitter.split(
            parse_result.content,
            metadata={"filename": fp.name, "file_type": parse_result.file_type},
        )

        chunk_metadatas = []
        
        # 向量化并存储
        if chunks:
            chunk_texts = [chunk.text for chunk in chunks]
            chunk_metadatas = [
                {
                    "doc_id": 0,  # 临时，稍后更新
                    "filename": fp.name,
                    "file_type": parse_result.file_type,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in chunks
            ]

            # 添加到向量库
            chunk_ids = self.vector_store.add_documents(
                documents=chunk_texts,
                metadatas=chunk_metadatas,
            )

        # 保存到数据库
        import sqlite3

        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(
                """INSERT INTO rag_documents
                   (filename, original_path, stored_path, file_type, file_size,
                    content_text, chunk_count, indexed_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fp.name,
                    str(fp.resolve()),
                    str(stored_path),
                    parse_result.file_type,
                    file_size,
                    parse_result.content[:10000],  # 限制存储内容大小
                    len(chunks),
                    now,
                    now,
                ),
            )
            doc_id = cursor.lastrowid

            # 更新向量库中的 doc_id
            if chunks:
                for i in range(len(chunks)):
                    chunk_metadatas[i]["doc_id"] = doc_id

                # 重新添加（实际上应该直接使用正确 doc_id，这里简化处理）
                # TODO: 优化为直接使用正确 doc_id

            conn.commit()
        finally:
            conn.close()

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=(
                f"✅ 文档已添加到知识库：{fp.name}\n"
                f"   类型: {parse_result.file_type}\n"
                f"   大小: {file_size / 1024:.1f}KB\n"
                f"   块数: {len(chunks)}"
            ),
            data={
                "document_id": doc_id,
                "filename": fp.name,
                "file_type": parse_result.file_type,
                "chunk_count": len(chunks),
            },
        )

    def _add_url(self, url: str, now: str) -> ToolResult:
        """添加 URL 到知识库。"""
        # 验证 URL
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"无效的 URL: {url}",
            )

        # 解析 URL
        try:
            parse_result = self.parser.parse_url(url)
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"URL 解析失败: {e}",
            )

        if not parse_result.content:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="无法提取网页内容",
            )

        # 保存 URL 内容到文件
        url_filename = f"{uuid.uuid4()}_{parsed.netloc}.txt"
        stored_path = self._doc_dir / url_filename
        content = f"# {parse_result.title}\n\nURL: {url}\n\n{parse_result.content}"
        stored_path.write_text(content, encoding="utf-8")

        # 分块
        from src.core.rag import TextSplitter
        splitter = TextSplitter(chunk_size=1000, chunk_overlap=100)
        chunks = splitter.split(
            content,
            metadata={"filename": url, "file_type": "url"},
        )

        chunk_metadatas = []
        
        # 存储到向量库
        if chunks:
            chunk_texts = [chunk.text for chunk in chunks]
            chunk_metadatas = [
                {
                    "doc_id": 0,
                    "filename": url,
                    "file_type": "url",
                    "chunk_index": chunk.chunk_index,
                    "source_url": url,
                }
                for chunk in chunks
            ]

            self.vector_store.add_documents(
                documents=chunk_texts,
                metadatas=chunk_metadatas,
            )

        # 保存到数据库
        import sqlite3

        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(
                """INSERT INTO rag_documents
                   (filename, original_path, stored_path, file_type, file_size,
                    content_text, chunk_count, indexed_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    url,
                    url,
                    str(stored_path),
                    "url",
                    len(content),
                    content[:10000],
                    len(chunks),
                    now,
                    now,
                ),
            )
            doc_id = cursor.lastrowid
            conn.commit()
        finally:
            conn.close()

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=(
                f"✅ 网页已添加到知识库：{parse_result.title or url}\n"
                f"   网址: {url}\n"
                f"   块数: {len(chunks)}"
            ),
            data={
                "document_id": doc_id,
                "filename": url,
                "title": parse_result.title,
                "chunk_count": len(chunks),
            },
        )

    def _search(self, params: dict[str, Any]) -> ToolResult:
        """语义搜索。"""
        query = params.get("query", "").strip()
        top_k = params.get("top_k", 3)

        if not query:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="搜索关键词不能为空",
            )

        try:
            results = self.vector_store.query(query, n_results=top_k)

            if not results:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=f"未找到与 '{query}' 相关的内容",
                    data={"results": [], "query": query},
                )

            output_lines = [f"找到 {len(results)} 个相关片段：\n"]
            data_results = []

            for i, result in enumerate(results, 1):
                # 获取文件名
                filename = result.metadata.get("filename", "未知")
                chunk_idx = result.metadata.get("chunk_index", 0)

                output_lines.append(f"--- 相关片段 {i} ---")
                output_lines.append(f"来源: {filename}")
                output_lines.append(f"内容: {result.text[:300]}...")
                output_lines.append("")

                data_results.append({
                    "filename": filename,
                    "chunk_index": chunk_idx,
                    "text": result.text,
                    "distance": result.distance,
                })

            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="\n".join(output_lines),
                data={"results": data_results, "query": query},
            )

        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"搜索失败: {e}",
            )

    def _query_document(self, params: dict[str, Any]) -> ToolResult:
        """查询指定文档。"""
        doc_name = params.get("document_name", "").strip()
        query = params.get("query", "").strip()
        top_k = params.get("top_k", 3)

        if not doc_name or not query:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="文档名和查询内容不能为空",
            )

        # 查找文档
        import sqlite3

        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT id, filename FROM rag_documents WHERE filename LIKE ? LIMIT 1",
                (f"%{doc_name}%",),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"未找到文档: {doc_name}",
            )

        doc_id, filename = row

        # 查询向量库
        try:
            results = self.vector_store.query_by_document(query, doc_id, top_k)

            if not results:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=f"在 {filename} 中未找到与 '{query}' 相关的内容",
                    data={"filename": filename},
                )

            output_lines = [f"在 {filename} 中找到 {len(results)} 个相关片段：\n"]
            data_results = []

            for i, result in enumerate(results, 1):
                output_lines.append(f"--- 片段 {i} ---")
                output_lines.append(f"内容: {result.text[:300]}...")
                output_lines.append("")

                data_results.append({
                    "text": result.text,
                    "distance": result.distance,
                })

            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="\n".join(output_lines),
                data={"filename": filename, "results": data_results},
            )

        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"查询失败: {e}",
            )

    def _list_documents(self, params: dict[str, Any]) -> ToolResult:
        """列出文档。"""
        limit = min(params.get("limit", 50), 200)

        import sqlite3

        conn = sqlite3.connect(self._db_path)
        try:
            rows = conn.execute(
                """SELECT id, filename, original_path, stored_path, file_type, file_size, content_text, chunk_count, indexed_at
                   FROM rag_documents ORDER BY indexed_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="知识库中暂无文档，请使用 add_document 添加文档",
                data={"documents": [], "count": 0},
            )

        lines = [f"知识库中共 {len(rows)} 个文档：\n"]
        docs = []

        for i, (doc_id, filename, original_path, stored_path, file_type, size, content_text, chunks, indexed) in enumerate(rows, 1):
            size_kb = size / 1024
            # chunk_count=0 表示解析失败
            if chunks == 0:
                lines.append(
                    f"  {i}. {filename} ({file_type}, {size_kb:.1f}KB) - ⚠️ 解析失败，内容为空"
                )
            else:
                lines.append(
                    f"  {i}. {filename} ({file_type}, {size_kb:.1f}KB, {chunks}块)"
                )
            docs.append({
                "id": doc_id,
                "filename": filename,
                "original_path": original_path,
                "stored_path": stored_path,
                "file_type": file_type,
                "size": size,
                "content_text": content_text or "",
                "chunk_count": chunks,
                "indexed_at": indexed,
            })

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={"documents": docs, "count": len(docs)},
        )

    def _remove_document(self, params: dict[str, Any]) -> ToolResult:
        """删除文档。"""
        doc_id = params.get("document_id")

        if doc_id is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="缺少 document_id",
            )

        import sqlite3

        conn = sqlite3.connect(self._db_path)
        try:
            # 获取文档信息
            row = conn.execute(
                "SELECT filename, stored_path FROM rag_documents WHERE id = ?",
                (doc_id,),
            ).fetchone()

            if not row:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"文档不存在: ID {doc_id}",
                )

            filename, stored_path = row

            # 删除向量库中的块
            self.vector_store.delete_by_document(doc_id)

            # 删除存储的文件
            try:
                Path(stored_path).unlink(missing_ok=True)
            except Exception:
                pass

            # 删除数据库记录
            conn.execute("DELETE FROM rag_documents WHERE id = ?", (doc_id,))
            conn.commit()

        finally:
            conn.close()

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=f"已从知识库删除: {filename}",
            data={"document_id": doc_id, "deleted": True},
        )

