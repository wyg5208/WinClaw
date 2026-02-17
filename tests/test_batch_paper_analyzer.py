"""批量论文分析工具测试脚本。

测试步骤：
1. 扫描论文文件夹
2. 批量导入向量库
3. 学术分析论文
4. 生成汇总报告
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def test_scan_folder():
    """测试扫描文件夹功能。"""
    print("\n" + "=" * 50)
    print("测试1: 扫描论文文件夹")
    print("=" * 50)

    from src.tools.batch_paper_analyzer import BatchPaperAnalyzerTool

    tool = BatchPaperAnalyzerTool()
    result = await tool.execute("scan_folder", {
        "folder_path": "D:/python_projects/openclaw_demo/winclaw/papers_for_test"
    })

    print(result.output)
    print(f"\n状态: {'✅ 成功' if result.is_success else '❌ 失败'}")
    if result.data:
        print(f"论文数量: {result.data.get('count', 0)}")
    return result


async def test_batch_import():
    """测试批量导入向量库功能。"""
    print("\n" + "=" * 50)
    print("测试2: 批量导入向量库")
    print("=" * 50)

    from src.tools.batch_paper_analyzer import BatchPaperAnalyzerTool

    tool = BatchPaperAnalyzerTool()
    result = await tool.execute("batch_import", {
        "folder_path": "D:/python_projects/openclaw_demo/winclaw/papers_for_test"
    })

    print(result.output)
    print(f"\n状态: {'✅ 成功' if result.is_success else '❌ 失败'}")
    if result.data:
        print(f"成功导入: {result.data.get('success', 0)}/{result.data.get('total', 0)}")
    return result


async def test_analyze_papers():
    """测试论文分析功能。"""
    print("\n" + "=" * 50)
    print("测试3: 学术论文分析")
    print("=" * 50)

    from src.tools.batch_paper_analyzer import BatchPaperAnalyzerTool

    # 直接使用模拟分析结果进行测试
    tool = BatchPaperAnalyzerTool()

    # 预填充分析结果
    tool._analysis_results = {
        "2020-Scrum-Guide-US.pdf": {
            "title": "The Scrum Guide (2020)",
            "authors": "Ken Schwaber, Jeff Sutherland",
            "year": "2020",
            "venue": "Scrum.org",
            "one_sentence": "Scrum是一个轻量级框架，帮助人们、团队和组织通过自适应问题解决方案创造价值。",
            "research_question": "如何通过敏捷方法提升团队效率",
            "method": "框架定义与实践指导",
            "conclusion": "Scrum基于经验过程控制理论，适用于复杂产品开发",
            "innovation": "简化管理流程，强调透明性和快速迭代",
            "limitations": "不适用于所有类型的项目"
        },
        "Product_innovation_firm_performance_and_moderating.pdf": {
            "title": "Product Innovation, Firm Performance and Moderating Factors",
            "authors": "Multiple Authors",
            "year": "2020",
            "venue": "Journal",
            "one_sentence": "产品创新对企业绩效的影响及其调节因素研究。",
            "research_question": "产品创新如何影响企业绩效",
            "method": "实证研究",
            "conclusion": "产品创新对企业绩效有显著正向影响",
            "innovation": "揭示了调节因素的作用机制",
            "limitations": "样本范围有限"
        },
        "understanding-user-journeys-in-edtech-startups-the-role-of-analytics-integration.pdf": {
            "title": "Understanding User Journeys in EdTech Startups",
            "authors": "Multiple Authors",
            "year": "2021",
            "venue": "Conference",
            "one_sentence": "分析教育科技初创企业中的用户旅程及分析集成的作用。",
            "research_question": "用户旅程如何影响教育科技产品",
            "method": "案例研究",
            "conclusion": "分析集成能提升用户体验和留存率",
            "innovation": "提出了用户旅程分析框架",
            "limitations": "仅关注初创企业"
        }
    }

    result = tool._analyze_papers({
        "folder_path": "D:/python_projects/openclaw_demo/winclaw/papers_for_test"
    })

    print(result.output)
    print(f"\n状态: {'✅ 成功' if result.is_success else '❌ 失败'}")
    return result


async def test_generate_report():
    """测试生成报告功能。"""
    print("\n" + "=" * 50)
    print("测试4: 生成分析报告")
    print("=" * 50)

    from src.tools.batch_paper_analyzer import BatchPaperAnalyzerTool

    tool = BatchPaperAnalyzerTool()

    # 预填充分析结果（模拟分析完成后的状态）
    tool._analysis_results = {
        "2020-Scrum-Guide-US.pdf": {
            "title": "The Scrum Guide (2020)",
            "authors": "Ken Schwaber, Jeff Sutherland",
            "year": "2020",
            "venue": "Scrum.org",
            "one_sentence": "Scrum是一个轻量级框架，帮助人们、团队和组织通过自适应问题解决方案创造价值。",
            "research_question": "如何通过敏捷方法提升团队效率",
            "method": "框架定义与实践指导",
            "key_findings": "Scrum基于经验过程控制理论",
            "conclusion": "Scrum适用于复杂产品开发",
            "contribution": "提出敏捷开发框架",
            "innovation": "简化管理流程，强调透明性",
            "limitations": "不适用于所有类型的项目"
        },
        "Product_innovation_firm_performance_and_moderating.pdf": {
            "title": "Product Innovation, Firm Performance and Moderating Factors",
            "authors": "Research Team",
            "year": "2020",
            "venue": "Business Journal",
            "one_sentence": "产品创新对企业绩效的影响及其调节因素研究。",
            "research_question": "产品创新如何影响企业绩效",
            "method": "实证研究/回归分析",
            "key_findings": "创新投入与绩效正相关",
            "conclusion": "产品创新对企业绩效有显著正向影响",
            "contribution": "揭示了调节因素的作用机制",
            "innovation": "识别出关键调节变量",
            "limitations": "样本范围有限"
        },
        "understanding-user-journeys-in-edtech-startups.pdf": {
            "title": "Understanding User Journeys in EdTech Startups",
            "authors": "EdTech Research Team",
            "year": "2021",
            "venue": "Education Technology Conference",
            "one_sentence": "分析教育科技初创企业中的用户旅程及分析集成的作用。",
            "research_question": "用户旅程如何影响教育科技产品",
            "method": "案例研究/用户访谈",
            "key_findings": "分析集成提升用户参与度",
            "conclusion": "分析集成能提升用户体验和留存率",
            "contribution": "提出用户旅程分析框架",
            "innovation": "构建EdTech用户旅程模型",
            "limitations": "仅关注初创企业"
        }
    }

    result = await tool.execute("generate_report", {
        "folder_path": "D:/python_projects/openclaw_demo/winclaw/papers_for_test",
        "title": "论文分析测试报告",
        "format_type": "docx"
    })

    print(result.output)
    print(f"\n状态: {'✅ 成功' if result.is_success else '❌ 失败'}")
    if result.data:
        print(f"生成文件: {result.data.get('file_path', 'N/A')}")
    return result


async def test_full_pipeline():
    """测试完整工作流。"""
    print("\n" + "=" * 50)
    print("测试5: 完整工作流")
    print("=" * 50)

    from src.tools.batch_paper_analyzer import BatchPaperAnalyzerTool

    tool = BatchPaperAnalyzerTool()

    # 预填充分析结果
    tool._analysis_results = {
        "2020-Scrum-Guide-US.pdf": {
            "title": "The Scrum Guide (2020)",
            "authors": "Ken Schwaber, Jeff Sutherland",
            "year": "2020",
            "one_sentence": "Scrum是一个轻量级敏捷框架。",
            "method": "框架定义",
            "conclusion": "适用于复杂产品开发",
            "contribution": "提出敏捷开发框架",
            "innovation": "简化管理流程",
            "limitations": "适用范围有限"
        },
        "Product_innovation_firm_performance_and_moderating.pdf": {
            "title": "Product Innovation and Firm Performance",
            "authors": "Research Team",
            "year": "2020",
            "one_sentence": "产品创新对企业绩效有正向影响。",
            "method": "实证研究",
            "conclusion": "创新驱动绩效提升",
            "contribution": "揭示调节因素",
            "innovation": "识别关键变量",
            "limitations": "样本有限"
        },
        "understanding-user-journeys-in-edtech-startups.pdf": {
            "title": "User Journeys in EdTech",
            "authors": "EdTech Team",
            "year": "2021",
            "one_sentence": "用户旅程分析提升产品体验。",
            "method": "案例研究",
            "conclusion": "分析集成有益于用户留存",
            "contribution": "提出分析框架",
            "innovation": "构建新模型",
            "limitations": "仅针对初创企业"
        }
    }

    result = await tool.execute("full_pipeline", {
        "folder_path": "D:/python_projects/openclaw_demo/winclaw/papers_for_test",
        "report_title": "测试批量论文分析报告"
    })

    print(result.output)
    print(f"\n状态: {'✅ 成功' if result.is_success else '❌ 失败'}")
    return result


async def main():
    """主测试函数。"""
    print("\n" + "🎓" * 20)
    print("批量论文分析工具测试")
    print("🎓" * 20)

    # 测试1: 扫描文件夹
    await test_scan_folder()

    # 测试2: 批量导入向量库
    await test_batch_import()

    # 测试3: 论文分析（可能需要较长时间）
    await test_analyze_papers()

    # 测试4: 生成报告
    await test_generate_report()

    # 测试5: 完整工作流
    await test_full_pipeline()

    print("\n" + "=" * 50)
    print("所有测试完成！")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
