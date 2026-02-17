"""WinClaw RAG (Retrieval Augmented Generation) 模块。

提供完整的知识库功能：
- 文档解析：支持 PDF、DOCX、PPT、图片、URL 等格式
- 向量存储：基于 ChromaDB 的向量数据库
- 语义检索：基于 sentence-transformers 的本地 Embedding

典型用法：
    from src.core.rag import DocumentParser, VectorStore, TextSplitter, Embedder
    
    # 解析文档
    parser = DocumentParser()
    content = parser.parse_file("example.pdf")
    
    # 分块
    splitter = TextSplitter()
    chunks = splitter.split(content)
    
    # 向量化
    embedder = Embedder()
    vectors = embedder.embed(chunks)
    
    # 存储
    store = VectorStore()
    store.add_documents(chunks, vectors, metadata)
    
    # 检索
    results = store.query("查询内容", top_k=5)
"""

from .parser import DocumentParser
from .vector_store import VectorStore
from .text_splitter import TextSplitter
from .embedder import Embedder

__all__ = [
    "DocumentParser",
    "VectorStore", 
    "TextSplitter",
    "Embedder",
]
