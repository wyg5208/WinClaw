"""向量存储 - 基于 ChromaDB 的向量数据库封装。

提供完整的向量存储和检索功能：
- 持久化存储
- 按用户隔离
- 元数据过滤
- 相似度检索
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 默认存储路径
DEFAULT_DB_PATH = os.path.expanduser("~/.winclaw/chroma_db")
DEFAULT_COLLECTION_NAME = "knowledge_base"


@dataclass
class SearchResult:
    """搜索结果。"""
    text: str
    distance: float
    metadata: dict
    doc_id: Optional[int] = None
    chunk_index: Optional[int] = None


class VectorStore:
    """向量存储。"""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        embedding_function=None,
    ):
        """初始化向量存储。

        Args:
            db_path: ChromaDB 持久化路径
            collection_name: Collection 名称
            embedding_function: Embedding 函数（可选，用于查询时自动向量化）
        """
        self.db_path = db_path
        self.collection_name = collection_name
        self.embedding_function = embedding_function
        self._client = None
        self._collection = None

        # 创建存储目录
        os.makedirs(db_path, exist_ok=True)

    @property
    def client(self):
        """获取 ChromaDB 客户端。"""
        if self._client is None:
            self._init_client()
        return self._client

    @property
    def collection(self):
        """获取 Collection。"""
        if self._collection is None:
            self._init_collection()
        return self._collection

    def _init_client(self) -> None:
        """初始化 ChromaDB 客户端。"""
        try:
            import chromadb
            from chromadb import PersistentClient

            self._client = PersistentClient(path=self.db_path)
            logger.info(f"✅ ChromaDB 初始化成功: {self.db_path}")

        except ImportError:
            logger.error("❌ chromadb 未安装，请运行: pip install chromadb")
            raise
        except Exception as e:
            logger.error(f"❌ ChromaDB 初始化失败: {e}")
            raise

    def _init_collection(self) -> None:
        """初始化 Collection。"""
        try:
            # 如果有自定义 embedding function，需要正确处理
            # ChromaDB 期望 embedding_function 是可调用对象
            ef = None
            if self.embedding_function is not None:
                # 包装 Embedder 以兼容 ChromaDB 接口
                ef = self._create_embedding_function()
            
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=ef,
                metadata={"description": "WinClaw 知识库"}
            )
            logger.info(f"✅ Collection '{self.collection_name}' 就绪")

        except Exception as e:
            logger.error(f"❌ Collection 初始化失败: {e}")
            raise

    def _create_embedding_function(self):
        """创建兼容 ChromaDB 的 embedding function。"""
        embedder = self.embedding_function
        
        class WrappedEmbeddingFunction:
            """包装 Embedder 以兼容 ChromaDB 接口。"""
            
            def __init__(self, fn):
                self._fn = fn
            
            def name(self):
                """ChromaDB 需要 name 方法。"""
                return "custom_embedding"
            
            def __call__(self, input):
                """ChromaDB 0.4.16+ 要求参数名为 input。"""
                if isinstance(input, str):
                    input = [input]
                return self._fn.embed(input)
        
        return WrappedEmbeddingFunction(embedder)

    def add_documents(
        self,
        documents: list[str],
        embeddings: Optional[list[list[float]]] = None,
        metadatas: Optional[list[dict]] = None,
        ids: Optional[list[str]] = None,
    ) -> list[str]:
        """添加文档到向量库。

        Args:
            documents: 文档文本列表
            embeddings: 向量列表（如果为 None，将使用 embedding_function 自动生成）
            metadatas: 元数据列表
            ids: ID 列表（如果为 None，将自动生成）

        Returns:
            生成的 ID 列表
        """
        if not documents:
            return []

        # 自动生成 ID
        if ids is None:
            ids = [f"doc_{i}_{str(hash(doc))[:8]}" for i, doc in enumerate(documents)]

        # 自动向量化
        if embeddings is None:
            if self.embedding_function is None:
                raise ValueError("必须提供 embeddings 或 embedding_function")
            embeddings = self.embedding_function.embed(documents)

        # 补齐元数据
        if metadatas is None:
            metadatas = [{}] * len(documents)

        try:
            self.collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids,
            )
            logger.info(f"✅ 添加 {len(documents)} 个文档到向量库")
            return ids

        except Exception as e:
            logger.error(f"❌ 添加文档失败: {e}")
            raise

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[dict] = None,
        where_document: Optional[dict] = None,
    ) -> list[SearchResult]:
        """查询向量库。

        Args:
            query_text: 查询文本
            n_results: 返回结果数量
            where: 元数据过滤条件
            where_document: 文档内容过滤条件

        Returns:
            搜索结果列表
        """
        try:
            # 自动向量化查询文本
            if self.embedding_function is None:
                raise ValueError("必须提供 embedding_function 才能进行查询")

            query_embedding = self.embedding_function.embed_single(query_text)

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where,
                where_document=where_document,
            )

            # 解析结果
            search_results = []
            
            # 安全检查：确保结果存在且格式正确
            if not results:
                return search_results
            
            documents = results.get("documents")
            if not documents or not isinstance(documents, list) or len(documents) == 0:
                return search_results
            
            docs = documents[0]
            if not docs or not isinstance(docs, list) or len(docs) == 0:
                return search_results
            
            # 获取可选字段
            metadatas = results.get("metadatas")
            distances = results.get("distances")
            
            for i, doc in enumerate(docs):
                metadata = {}
                if metadatas and isinstance(metadatas, list) and len(metadatas) > 0:
                    if isinstance(metadatas[0], list) and len(metadatas[0]) > i:
                        metadata = metadatas[0][i] or {}
                    elif isinstance(metadatas[0], dict):
                        metadata = metadatas[0]
                
                distance = 0.0
                if distances and isinstance(distances, list) and len(distances) > 0:
                    if isinstance(distances[0], list) and len(distances[0]) > i:
                        distance = distances[0][i]

                search_results.append(SearchResult(
                    text=doc,
                    distance=distance,
                    metadata=metadata,
                    doc_id=metadata.get("doc_id") if isinstance(metadata, dict) else None,
                    chunk_index=metadata.get("chunk_index") if isinstance(metadata, dict) else None,
                ))

            return search_results

        except Exception as e:
            logger.error(f"❌ 查询失败: {e}")
            raise

    def query_by_user(
        self,
        query_text: str,
        user_id: int,
        n_results: int = 5,
    ) -> list[SearchResult]:
        """按用户查询。

        Args:
            query_text: 查询文本
            user_id: 用户 ID
            n_results: 返回数量

        Returns:
            搜索结果列表
        """
        where = {"user_id": user_id}
        return self.query(query_text, n_results=n_results, where=where)

    def query_by_document(
        self,
        query_text: str,
        doc_id: int,
        n_results: int = 5,
    ) -> list[SearchResult]:
        """按文档查询。

        Args:
            query_text: 查询文本
            doc_id: 文档 ID
            n_results: 返回数量

        Returns:
            搜索结果列表
        """
        where = {"doc_id": doc_id}
        return self.query(query_text, n_results=n_results, where=where)

    def delete_by_document(self, doc_id: int) -> bool:
        """删除指定文档的所有块。

        Args:
            doc_id: 文档 ID

        Returns:
            是否成功
        """
        try:
            results = self.collection.get(where={"doc_id": doc_id})
            if results and results.get("ids"):
                self.collection.delete(ids=results["ids"])
                logger.info(f"✅ 删除文档 {doc_id} 的 {len(results['ids'])} 个块")
                return True
            return False

        except Exception as e:
            logger.error(f"❌ 删除文档失败: {e}")
            return False

    def delete_by_id(self, doc_id: str) -> bool:
        """删除指定 ID 的块。

        Args:
            doc_id: 块 ID

        Returns:
            是否成功
        """
        try:
            self.collection.delete(ids=[doc_id])
            return True
        except Exception as e:
            logger.error(f"❌ 删除失败: {e}")
            return False

    def get_document_chunks(self, doc_id: int) -> list[SearchResult]:
        """获取指定文档的所有块。

        Args:
            doc_id: 文档 ID

        Returns:
            块列表
        """
        try:
            results = self.collection.get(where={"doc_id": doc_id})

            chunks = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"]):
                    metadata = results["metadatas"][i]
                    chunks.append(SearchResult(
                        text=doc,
                        distance=0.0,
                        metadata=metadata,
                        doc_id=metadata.get("doc_id"),
                        chunk_index=metadata.get("chunk_index"),
                    ))

            return chunks

        except Exception as e:
            logger.error(f"❌ 获取文档块失败: {e}")
            return []

    def count(self, where: Optional[dict] = None) -> int:
        """统计向量数量。

        Args:
            where: 过滤条件

        Returns:
            向量数量
        """
        try:
            result = self.collection.get(where=where)
            return len(result.get("ids", [])) if result else 0
        except Exception as e:
            logger.error(f"❌ 统计失败: {e}")
            return 0

    def clear(self) -> bool:
        """清空向量库。"""
        try:
            self.client.delete_collection(self.collection_name)
            self._collection = None
            self._init_collection()
            logger.info("✅ 向量库已清空")
            return True
        except Exception as e:
            logger.error(f"❌ 清空失败: {e}")
            return False


# 全局单例
_default_store: Optional[VectorStore] = None


def get_vector_store(
    db_path: str = DEFAULT_DB_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedder=None,
) -> VectorStore:
    """获取全局向量存储实例。"""
    global _default_store

    if _default_store is None:
        _default_store = VectorStore(
            db_path=db_path,
            collection_name=collection_name,
            embedding_function=embedder,
        )

    return _default_store


def reset_vector_store() -> None:
    """重置全局向量存储。"""
    global _default_store
    _default_store = None
