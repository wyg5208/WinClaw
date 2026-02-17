"""知识库 RAG 功能全流程测试。"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.tools.knowledge_rag import KnowledgeRAGTool
from src.tools.base import ToolResultStatus

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} — {detail}")


async def test_add_text_document(tool: KnowledgeRAGTool, tmpdir: str) -> None:
    """测试添加文本文档。"""
    print("\n🧪 测试添加文本文档")
    
    # 创建测试文件
    test_file = os.path.join(tmpdir, "test_doc.txt")
    content = """这是一个测试文档。

第一部分：关于人工智能
人工智能（Artificial Intelligence，AI）是计算机科学的一个分支，
它试图理解智能的本质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。

第二部分：机器学习
机器学习是人工智能的核心，是使计算机具有智能的根本途径。
它是一门多领域交叉学科，涉及概率论、统计学、逼近论、凸分析、算法复杂度理论等多门学科。

第三部分：深度学习
深度学习是机器学习的分支，是一种以人工神经网络为架构，
对数据进行表征学习的算法。"""
    
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(content)
    
    result = await tool.execute("add_document", {"file_path": test_file})
    check("添加文本文档", result.status == ToolResultStatus.SUCCESS, result.error)
    
    if result.status == ToolResultStatus.SUCCESS:
        doc_id = result.data.get("document_id")
        check("返回 document_id", doc_id is not None)
        check("返回 chunk_count", result.data.get("chunk_count", 0) > 0)
        return doc_id
    return None


async def test_add_markdown_document(tool: KnowledgeRAGTool, tmpdir: str) -> None:
    """测试添加 Markdown 文档。"""
    print("\n🧪 测试添加 Markdown 文档")
    
    test_file = os.path.join(tmpdir, "test_md.md")
    content = """# 测试 Markdown 文档

## 什么是 RAG？

检索增强生成（Retrieval Augmented Generation，RAG）是一种结合检索系统和生成模型的 AI 架构。

## 核心组件

1. **向量数据库**：存储文档的向量表示
2. ** Embedding 模型**：将文本转换为向量
3. **生成模型**：根据检索结果生成回答

## 优势

- 减少幻觉
- 提高准确性
- 支持私有知识
"""
    
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(content)
    
    result = await tool.execute("add_document", {"file_path": test_file})
    check("添加 Markdown 文档", result.status == ToolResultStatus.SUCCESS, result.error)
    
    if result.status == ToolResultStatus.SUCCESS:
        return result.data.get("document_id")
    return None


async def test_list_documents(tool: KnowledgeRAGTool) -> None:
    """测试列出文档。"""
    print("\n🧪 测试列出文档")
    
    result = await tool.execute("list_documents", {"limit": 10})
    check("列出文档", result.status == ToolResultStatus.SUCCESS, result.error)
    
    if result.status == ToolResultStatus.SUCCESS:
        docs = result.data.get("documents", [])
        check(f"文档数量 >= 2", len(docs) >= 2, f"实际: {len(docs)}")
        return docs
    return []


async def test_search(tool: KnowledgeRAGTool) -> None:
    """测试语义搜索。"""
    print("\n🧪 测试语义搜索")
    
    # 搜索机器学习相关内容
    result = await tool.execute("search", {
        "query": "什么是机器学习？",
        "top_k": 3
    })
    check("搜索执行成功", result.status == ToolResultStatus.SUCCESS, result.error)
    
    if result.status == ToolResultStatus.SUCCESS:
        results = result.data.get("results", [])
        check("返回搜索结果", len(results) > 0, f"结果数: {len(results)}")
        
        # 检查结果是否包含相关内容
        if results:
            text = results[0].get("text", "")
            check("结果包含关键词", "学习" in text or "机器" in text or "AI" in text or "人工智能" in text)


async def test_query_document(tool: KnowledgeRAGTool, docs: list) -> None:
    """测试查询指定文档。"""
    print("\n🧪 测试查询指定文档")
    
    if not docs:
        check("跳过（无文档）", False, "需要先添加文档")
        return
    
    # 使用第一个文档
    doc_name = docs[0].get("filename", "")
    if not doc_name:
        check("跳过（无文件名）", False)
        return
    
    result = await tool.execute("query_document", {
        "document_name": doc_name.replace(".txt", "").replace(".md", ""),
        "query": "人工智能",
        "top_k": 2
    })
    check("查询文档执行成功", result.status == ToolResultStatus.SUCCESS, result.error)
    
    if result.status == ToolResultStatus.SUCCESS:
        results = result.data.get("results", [])
        check("返回查询结果", len(results) > 0)


async def test_remove_document(tool: KnowledgeRAGTool, docs: list) -> None:
    """测试删除文档。"""
    print("\n🧪 测试删除文档")
    
    if not docs:
        check("跳过（无文档）", False, "需要先添加文档")
        return
    
    # 获取第一个文档的 ID
    doc_id = docs[0].get("id")
    if not doc_id:
        check("跳过（无文档ID）", False)
        return
    
    # 删除前先列出确认
    result_before = await tool.execute("list_documents", {"limit": 10})
    count_before = len(result_before.data.get("documents", [])) if result_before.status == ToolResultStatus.SUCCESS else 0
    
    # 删除
    result = await tool.execute("remove_document", {"document_id": doc_id})
    check("删除文档", result.status == ToolResultStatus.SUCCESS, result.error)
    
    # 验证删除
    if result.status == ToolResultStatus.SUCCESS:
        result_after = await tool.execute("list_documents", {"limit": 10})
        count_after = len(result_after.data.get("documents", [])) if result_after.status == ToolResultStatus.SUCCESS else 0
        check("文档数量减少", count_before > count_after, f"前: {count_before}, 后: {count_after}")


async def test_search_no_results(tool: KnowledgeRAGTool) -> None:
    """测试搜索无结果的情况。"""
    print("\n🧪 测试搜索无结果")
    
    result = await tool.execute("search", {
        "query": "完全不存在的搜索内容 xyz123456789",
        "top_k": 3
    })
    check("搜索执行成功", result.status == ToolResultStatus.SUCCESS)
    
    # 无结果是正常的，不应该报错


async def test_invalid_file(tool: KnowledgeRAGTool) -> None:
    """测试添加不存在的文件。"""
    print("\n🧪 测试添加不存在的文件")
    
    result = await tool.execute("add_document", {"file_path": "不存在的文件路径.txt"})
    check("正确处理不存在的文件", result.status == ToolResultStatus.ERROR)


async def test_unsupported_file(tool: KnowledgeRAGTool, tmpdir: str) -> None:
    """测试不支持的文件类型。"""
    print("\n🧪 测试不支持的文件类型")
    
    # 创建一个 exe 文件
    test_file = os.path.join(tmpdir, "test.exe")
    with open(test_file, "wb") as f:
        f.write(b"fake exe content")
    
    result = await tool.execute("add_document", {"file_path": test_file})
    check("正确处理不支持的文件", result.status == ToolResultStatus.ERROR)


async def main():
    global passed, failed
    
    print("=" * 60)
    print("  WinClaw 知识库 RAG 全流程测试")
    print("=" * 60)
    
    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建工具实例
        tool = KnowledgeRAGTool()
        
        # 1. 添加文本文档
        await test_add_text_document(tool, tmpdir)
        
        # 2. 添加 Markdown 文档
        await test_add_markdown_document(tool, tmpdir)
        
        # 3. 列出文档
        docs = await test_list_documents(tool)
        
        # 4. 语义搜索
        await test_search(tool)
        
        # 5. 查询指定文档
        await test_query_document(tool, docs)
        
        # 6. 测试无结果搜索
        await test_search_no_results(tool)
        
        # 7. 测试不存在的文件
        await test_invalid_file(tool)
        
        # 8. 测试不支持的文件
        await test_unsupported_file(tool, tmpdir)
        
        # 9. 删除文档（最后执行）
        await test_remove_document(tool, docs)
    
    print("\n" + "=" * 60)
    print(f"  结果: ✅ {passed} 通过  ❌ {failed} 失败")
    print("=" * 60)
    
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
