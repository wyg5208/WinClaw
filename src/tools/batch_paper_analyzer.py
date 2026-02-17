"""批量论文阅读分析工具。

提供动作：
- scan_folder: 扫描论文文件夹，获取所有论文文件
- batch_import: 批量导入论文到向量知识库
- analyze_papers: 批量对论文进行学术角度分析
- generate_report: 生成论文分析汇总报告

依赖：
- knowledge_rag: 向量知识库（文档解析、入库、检索）
- doc_generator: 文档生成（生成 Word 报告）
- 大模型对话: 论文内容分析

设计：
- 支持批量处理大量论文
- 自动提取学术信息（标题、作者、年份、期刊等）
- 按学术规范分析研究问题、方法、结论、创新点
- 生成结构化阅读大纲和汇总报告
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)

# 支持的论文文件类型
PAPER_EXTENSIONS = {".pdf", ".docx", ".doc"}

# 分析报告输出目录
DEFAULT_OUTPUT_DIR = "generated/paper_analysis"


class BatchPaperAnalyzerTool(BaseTool):
    """批量论文阅读分析工具。"""

    name = "batch_paper_analyzer"
    emoji = "📚"
    title = "批量论文分析"
    description = "批量阅读和分析学术论文，生成阅读大纲和学术建议"
    timeout = 300  # 批量处理需要更长时间

    def __init__(
        self,
        knowledge_rag_tool=None,
        doc_generator_tool=None,
        llm_client=None,
        output_dir: str = "",
    ):
        """初始化批量论文分析工具。

        Args:
            knowledge_rag_tool: 知识库工具实例（用于文档入库和检索）
            doc_generator_tool: 文档生成工具实例（用于生成报告）
            llm_client: 大模型客户端（用于论文分析）
            output_dir: 输出目录
        """
        super().__init__()
        self._knowledge_rag = knowledge_rag_tool
        self._doc_generator = doc_generator_tool
        self._llm_client = llm_client

        self.output_dir = Path(output_dir) if output_dir else Path(DEFAULT_OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 存储分析结果
        self._analysis_results: dict[str, dict] = {}

    @property
    def llm_client(self):
        """获取 LLM 客户端（延迟加载）。"""
        if self._llm_client is None:
            # 尝试自动获取 litellm 客户端
            try:
                import litellm
                self._llm_client = litellm
            except ImportError:
                pass
        return self._llm_client

    @property
    def knowledge_rag(self):
        """获取知识库工具（延迟加载）。"""
        if self._knowledge_rag is None:
            from src.tools.knowledge_rag import KnowledgeRAGTool
            self._knowledge_rag = KnowledgeRAGTool()
        return self._knowledge_rag

    @property
    def doc_generator(self):
        """获取文档生成工具（延迟加载）。"""
        if self._doc_generator is None:
            from src.tools.doc_generator import DocGeneratorTool
            self._doc_generator = DocGeneratorTool(output_dir=str(self.output_dir))
        return self._doc_generator

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="scan_folder",
                description="扫描论文文件夹，获取所有论文文件列表。支持 PDF 和 DOCX 格式。",
                parameters={
                    "folder_path": {
                        "type": "string",
                        "description": "论文文件夹路径（绝对路径）",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归扫描子文件夹，默认 False",
                    },
                },
                required_params=["folder_path"],
            ),
            ActionDef(
                name="batch_import",
                description="批量将论文导入到向量知识库。会自动解析 PDF/DOCX 文档内容并向量化存储。",
                parameters={
                    "folder_path": {
                        "type": "string",
                        "description": "论文文件夹路径",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归扫描子文件夹",
                    },
                },
                required_params=["folder_path"],
            ),
            ActionDef(
                name="analyze_papers",
                description="批量对论文进行学术角度分析，提取研究问题、方法、结论、创新点等，生成阅读大纲。",
                parameters={
                    "folder_path": {
                        "type": "string",
                        "description": "论文文件夹路径",
                    },
                    "analysis_depth": {
                        "type": "string",
                        "description": "分析深度：basic(基础) / detailed(详细)，默认 detailed",
                        "enum": ["basic", "detailed"],
                    },
                },
                required_params=["folder_path"],
            ),
            ActionDef(
                name="generate_report",
                description="生成论文分析汇总报告，包含所有论文的核心观点和学术引用建议。",
                parameters={
                    "folder_path": {
                        "type": "string",
                        "description": "论文文件夹路径",
                    },
                    "title": {
                        "type": "string",
                        "description": "报告标题，默认'批量论文阅读分析报告'",
                    },
                    "format_type": {
                        "type": "string",
                        "description": "报告格式：docx 或 html，默认 docx",
                        "enum": ["docx", "html"],
                    },
                },
                required_params=["folder_path"],
            ),
            ActionDef(
                name="full_pipeline",
                description="完整工作流：扫描文件夹 -> 批量入库 -> 学术分析 -> 生成报告，一步完成所有步骤。",
                parameters={
                    "folder_path": {
                        "type": "string",
                        "description": "论文文件夹路径（绝对路径）",
                    },
                    "report_title": {
                        "type": "string",
                        "description": "生成的报告标题",
                    },
                },
                required_params=["folder_path"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "scan_folder": self._scan_folder,
            "batch_import": self._batch_import,
            "analyze_papers": self._analyze_papers,
            "generate_report": self._generate_report,
            "full_pipeline": self._full_pipeline,
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
            logger.error(f"批量论文分析失败: {e}\n{traceback.format_exc()}")
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))

    # -------------------- 动作实现 --------------------

    def _scan_folder(self, params: dict[str, Any]) -> ToolResult:
        """扫描论文文件夹。"""
        folder_path = params.get("folder_path", "").strip()
        recursive = params.get("recursive", False)

        if not folder_path:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="文件夹路径不能为空",
            )

        folder = Path(folder_path)
        if not folder.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"文件夹不存在: {folder_path}",
            )
        if not folder.is_dir():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不是文件夹: {folder_path}",
            )

        # 扫描论文文件
        paper_files = []
        try:
            if recursive:
                for ext in PAPER_EXTENSIONS:
                    paper_files.extend(folder.rglob(f"*{ext}"))
            else:
                for ext in PAPER_EXTENSIONS:
                    paper_files.extend(folder.glob(f"*{ext}"))
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"扫描文件夹失败: {e}",
            )

        # 去重并排序
        paper_files = sorted(set(paper_files), key=lambda x: x.name)

        if not paper_files:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"文件夹中未找到论文文件: {folder_path}\n支持的格式: {', '.join(PAPER_EXTENSIONS)}",
                data={"papers": [], "count": 0},
            )

        # 生成文件信息
        papers_info = []
        for f in paper_files:
            size_kb = f.stat().st_size / 1024
            papers_info.append({
                "name": f.name,
                "path": str(f.resolve()),
                "size_kb": round(size_kb, 1),
                "type": f.suffix.lower(),
            })

        output_lines = [
            f"📂 文件夹: {folder_path}",
            f"📄 找到 {len(paper_files)} 篇论文：\n",
        ]
        for i, p in enumerate(papers_info, 1):
            output_lines.append(f"  {i}. {p['name']} ({p['size_kb']:.1f}KB)")

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(output_lines),
            data={"papers": papers_info, "count": len(papers_info)},
        )

    def _batch_import(self, params: dict[str, Any]) -> ToolResult:
        """批量导入论文到向量知识库。"""
        # 智能事件循环处理
        try:
            loop = asyncio.get_running_loop()
            # 如果有运行中的事件循环，创建一个任务
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self._batch_import_async(params))
                return future.result()
        except RuntimeError:
            # 没有运行中的事件循环，可以安全使用 asyncio.run
            return asyncio.run(self._batch_import_async(params))

    async def _batch_import_async(self, params: dict[str, Any]) -> ToolResult:
        """批量导入论文到向量知识库（异步版本）。"""
        folder_path = params.get("folder_path", "").strip()
        recursive = params.get("recursive", False)

        # 先扫描文件夹
        scan_result = self._scan_folder({"folder_path": folder_path, "recursive": recursive})
        if not scan_result.is_success:
            return scan_result

        papers = scan_result.data.get("papers", [])
        if not papers:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="没有需要导入的论文",
            )

        # 逐个导入
        success_count = 0
        failed_papers = []
        results = []

        for paper in papers:
            file_path = paper["path"]
            print(f"  尝试导入: {paper['name']}...")
            try:
                result = await self.knowledge_rag.execute("add_document", {"file_path": file_path})
                print(f"  导入 {paper['name']}: {result.status}")
                if result.is_success:
                    success_count += 1
                    results.append({"paper": paper["name"], "status": "success"})
                else:
                    failed_papers.append(paper["name"])
                    results.append({"paper": paper["name"], "status": "failed", "error": result.error})
            except Exception as e:
                print(f"  ❌ 导入失败: {paper['name']}, 错误: {e}")
                failed_papers.append(paper["name"])
                results.append({"paper": paper["name"], "status": "failed", "error": str(e)})

        output_lines = [
            f"📥 批量导入完成",
            f"   成功: {success_count}/{len(papers)}",
        ]
        if failed_papers:
            output_lines.append(f"   失败: {', '.join(failed_papers)}")

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(output_lines),
            data={
                "total": len(papers),
                "success": success_count,
                "failed": len(failed_papers),
                "results": results,
            },
        )

    def _analyze_papers(self, params: dict[str, Any]) -> ToolResult:
        """批量分析论文。"""
        folder_path = params.get("folder_path", "").strip()
        analysis_depth = params.get("analysis_depth", "detailed")

        if not self.llm_client:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="未配置大模型客户端，无法进行分析。请在初始化时提供 llm_client。",
            )

        # 扫描文件夹
        scan_result = self._scan_folder({"folder_path": folder_path})
        if not scan_result.is_success:
            return scan_result

        papers = scan_result.data.get("papers", [])
        if not papers:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="没有需要分析的论文",
            )

        # 存储分析结果
        self._analysis_results = {}
        analysis_output = [f"📊 开始分析 {len(papers)} 篇论文...\n"]

        for i, paper in enumerate(papers, 1):
            paper_name = paper["name"]
            analysis_output.append(f"  [{i}/{len(papers)}] 正在分析: {paper_name}")

            try:
                # 使用大模型分析论文
                analysis = self._analyze_single_paper(paper["path"], analysis_depth)
                self._analysis_results[paper_name] = analysis
            except Exception as e:
                analysis_output.append(f"    ❌ 分析失败: {e}")

        output_lines = [
            f"✅ 分析完成，共处理 {len(papers)} 篇论文",
            "",
        ]
        for name, analysis in self._analysis_results.items():
            output_lines.append(f"  📄 {name}")
            if analysis.get("title"):
                output_lines.append(f"     标题: {analysis['title']}")
            if analysis.get("one_sentence"):
                output_lines.append(f"     概括: {analysis['one_sentence']}")

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(output_lines),
            data={"analysis_results": self._analysis_results},
        )

    def _analyze_single_paper(self, file_path: str, depth: str) -> dict:
        """分析单篇论文。"""
        # 解析论文内容
        from src.core.rag import DocumentParser
        parser = DocumentParser()
        parse_result = parser.parse(file_path)

        if not parse_result.success or not parse_result.content:
            return {"error": f"文档解析失败: {parse_result.error}"}

        # 截取内容用于分析（避免超出 token 限制）
        content = parse_result.content[:15000]  # 保留足够的内容

        # 构建分析提示词
        if depth == "basic":
            prompt = f"""请分析以下学术论文，提取关键信息。用中文回复。

论文内容：
{content}

请提取以下信息（JSON 格式）：
{{
    "title": "论文标题",
    "authors": "作者",
    "year": "发表年份",
    "venue": "期刊/会议",
    "one_sentence": "一句话概括论文核心贡献",
    "research_question": "研究问题",
    "method": "研究方法",
    "conclusion": "主要结论",
    "innovation": "创新点",
    "limitations": "局限性"
}}
"""
        else:  # detailed
            prompt = f"""请对以下学术论文进行深度学术分析。用中文回复。

论文内容：
{content}

请提取以下信息（JSON 格式）：
{{
    "title": "论文标题",
    "authors": "作者",
    "year": "发表年份",
    "venue": "期刊/会议",
    "one_sentence": "一句话概括论文核心贡献",
    "research_question": "研究问题",
    "research_hypothesis": "研究假设",
    "method": "研究方法",
    "data_source": "数据来源",
    "key_findings": "主要发现",
    "conclusion": "主要结论",
    "contribution": "主要贡献",
    "innovation": "创新点（理论/方法/应用）",
    "limitations": "研究局限性",
    "related_work": "相关文献",
    "reading_time": "建议阅读时间（分钟）",
    "key_sections": "重点章节"
}}
"""

        # 调用大模型
        try:
            response = self.llm_client.chat.completions.create(
                model="glm-4-flash",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            import json
            import re

            # 解析 JSON 结果
            content_text = response.choices[0].message.content
            # 提取 JSON 部分
            json_match = re.search(r'\{[\s\S]*\}', content_text)
            if json_match:
                result = json.loads(json_match.group())
                return result
            else:
                return {"raw_analysis": content_text}
        except Exception as e:
            return {"error": f"分析失败: {e}"}

    def _generate_report(self, params: dict[str, Any]) -> ToolResult:
        """生成汇总报告。"""
        # 智能事件循环处理
        try:
            loop = asyncio.get_running_loop()
            # 如果有运行中的事件循环，使用线程池
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self._generate_report_async(params))
                return future.result()
        except RuntimeError:
            # 没有运行中的事件循环，可以安全使用 asyncio.run
            return asyncio.run(self._generate_report_async(params))

    async def _generate_report_async(self, params: dict[str, Any]) -> ToolResult:
        """生成汇总报告（异步版本）。"""
        folder_path = params.get("folder_path", "").strip()
        title = params.get("title", "批量论文阅读分析报告")
        format_type = params.get("format_type", "docx")

        # 如果没有预存的分析结果，先进行分析
        if not self._analysis_results:
            # 尝试从知识库获取
            analyze_result = self._analyze_papers({
                "folder_path": folder_path,
                "analysis_depth": "detailed"
            })
            if not analyze_result.is_success:
                return analyze_result

        if not self._analysis_results:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="没有分析结果可供生成报告",
            )

        # 构建报告内容
        report_content = self._build_report_content(title, folder_path)

        # 生成文档
        try:
            result = await self.doc_generator.execute("generate_document", {
                "content": report_content,
                "title": title,
                "format_type": format_type,
            })
            return result
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"生成报告失败: {e}",
            )

    def _build_report_content(self, title: str, folder_path: str) -> str:
        """构建报告 Markdown 内容。"""
        from datetime import datetime

        lines = [
            f"# {title}",
            "",
            "## 基本信息",
            "",
            f"- **分析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **来源文件夹**: {folder_path}",
            f"- **分析论文数量**: {len(self._analysis_results)} 篇",
            "",
            "---",
            "",
        ]

        # 论文清单
        lines.append("## 论文清单")
        lines.append("")
        lines.append("| 序号 | 标题 | 作者 | 年份 | 状态 |")
        lines.append("|:---:|:---|:---|:---:|:---:|")

        for i, (name, analysis) in enumerate(self._analysis_results.items(), 1):
            paper_title = analysis.get("title", name)
            authors = analysis.get("authors", "-")
            year = analysis.get("year", "-")
            status = "✅" if "error" not in analysis else "⚠️"
            lines.append(f"| {i} | {paper_title} | {authors} | {year} | {status} |")

        lines.append("")

        # 主题聚类（按年份分组）
        lines.append("## 论文概览")
        lines.append("")
        for name, analysis in self._analysis_results.items():
            if "error" in analysis:
                continue
            paper_title = analysis.get("title", name)
            one_sentence = analysis.get("one_sentence", "-")
            method = analysis.get("method", "-")
            conclusion = analysis.get("conclusion", "-")

            lines.append(f"### {paper_title}")
            lines.append("")
            lines.append(f"**一句话概括**: {one_sentence}")
            lines.append("")
            lines.append(f"**研究方法**: {method}")
            lines.append("")
            lines.append(f"**主要结论**: {conclusion}")
            lines.append("")

        # 学术建议
        lines.append("## 学术建议")
        lines.append("")
        lines.append("### 论文引用建议")
        lines.append("")
        for name, analysis in self._analysis_results.items():
            if "error" in analysis:
                continue
            paper_title = analysis.get("title", name)
            contribution = analysis.get("contribution", analysis.get("innovation", "-"))
            lines.append(f"**{paper_title}**")
            lines.append(f"- 主要贡献: {contribution}")
            lines.append("")

        lines.append("### 写作组织建议")
        lines.append("")
        lines.append("1. **按主题组织**: 将论文按研究主题分组，构建清晰的论证逻辑")
        lines.append("2. **方法论对比**: 比较不同论文使用的研究方法，分析优劣势")
        lines.append("3. **引用策略**: 优先引用创新性强、结论可靠的论文")
        lines.append("")

        return "\n".join(lines)

    def _full_pipeline(self, params: dict[str, Any]) -> ToolResult:
        """完整工作流。"""
        import asyncio

        folder_path = params.get("folder_path", "").strip()
        report_title = params.get("report_title", "批量论文阅读分析报告")

        if not folder_path:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="文件夹路径不能为空",
            )

        steps = [
            ("扫描文件夹", lambda: self._scan_folder({"folder_path": folder_path})),
            ("批量入库", lambda: self._batch_import({"folder_path": folder_path})),
            ("学术分析", lambda: self._analyze_papers({"folder_path": folder_path})),
            ("生成报告", lambda: self._generate_report({
                "folder_path": folder_path,
                "title": report_title,
            })),
        ]

        output_lines = ["🚀 开始完整工作流\n"]

        for step_name, step_func in steps:
            output_lines.append(f"📌 步骤: {step_name}...")
            try:
                result = step_func()
                if result.is_success:
                    output_lines.append(f"   ✅ 完成")
                else:
                    output_lines.append(f"   ⚠️ {result.error}")
            except Exception as e:
                output_lines.append(f"   ❌ 失败: {e}")

        output_lines.append("\n🎉 工作流完成！")

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(output_lines),
        )


# 用于测试
if __name__ == "__main__":
    import asyncio

    async def test():
        tool = BatchPaperAnalyzerTool()

        # 测试扫描
        result = await tool.execute("scan_folder", {
            "folder_path": "D:/papers",
        })
        print(result.output)

    asyncio.run(test())
