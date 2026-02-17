#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS测试报告生成器
用于生成Word文档和测试报告
"""

import json
import os
from datetime import datetime
from typing import Dict, List
import markdown

def load_test_results(json_file: str = 'rss_test_results.json') -> Dict:
    """加载测试结果"""
    if not os.path.exists(json_file):
        print(f"错误: 找不到测试结果文件 {json_file}")
        print("请先运行 rss_tester.py 进行测试")
        return None
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data

def generate_markdown_report(data: Dict) -> str:
    """生成Markdown格式的报告"""
    summary = data['summary']
    results = data['results']
    
    # 生成报告标题和时间
    report_date = datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')
    
    markdown_content = f"""# RSS源测试报告

**报告生成时间**: {report_date}
**测试执行时间**: {summary['test_time']}

## 📊 测试摘要

| 项目 | 数值 |
|------|------|
| 总测试RSS源数 | {summary['total_feeds']} |
| 成功测试数 | {summary['successful_feeds']} |
| 失败测试数 | {summary['failed_feeds']} |
| 成功率 | {summary['success_rate']}% |
| 平均响应时间 | {summary['average_response_time']}秒 |

## 📈 分类统计

"""
    
    # 添加分类统计
    for category, stats in summary['categories'].items():
        rate = stats['success'] / stats['total'] * 100 if stats['total'] > 0 else 0
        markdown_content += f"- **{category}**: {stats['success']}/{stats['total']} (成功率: {rate:.1f}%)\n"
    
    markdown_content += """

## 📋 详细测试结果

### ✅ 成功的RSS源
"""
    
    # 成功的RSS源
    successful_feeds = [r for r in results if r['status'] == 'success']
    for feed in successful_feeds:
        markdown_content += f"""
#### {feed['name']}
- **分类**: {feed['category']}
- **URL**: `{feed['url']}`
- **响应时间**: {feed['response_time']}秒
- **文章数量**: {feed['entries_count']}篇
- **最后更新**: {feed['last_updated'] or '未知'}

**示例文章**:
"""
        for i, entry in enumerate(feed['sample_entries'], 1):
            markdown_content += f"{i}. **{entry['title']}** - {entry['published']}\n"
    
    markdown_content += "\n### ❌ 失败的RSS源\n"
    
    # 失败的RSS源
    failed_feeds = [r for r in results if r['status'] != 'success']
    for feed in failed_feeds:
        markdown_content += f"""
#### {feed['name']}
- **分类**: {feed['category']}
- **URL**: `{feed['url']}`
- **状态**: {feed['status']}
- **错误信息**: {feed['error'] or '无'}
"""
    
    markdown_content += """

## 🔍 测试详情

### 测试方法
1. 发送HTTP请求获取RSS内容
2. 解析RSS/Atom格式
3. 检查响应状态和内容有效性
4. 提取基本信息（文章数量、最后更新时间等）
5. 记录响应时间和错误信息

### 测试标准
- **成功**: HTTP 200响应且能正确解析RSS内容
- **失败**: 连接错误、超时、HTTP错误或解析错误

## 💡 建议

### 推荐使用的RSS源
基于测试结果，以下RSS源表现良好，推荐使用：
"""
    
    # 推荐列表（响应时间快、文章数量多的）
    good_feeds = []
    for feed in successful_feeds:
        if feed['response_time'] < 2 and feed['entries_count'] > 5:
            good_feeds.append(feed)
    
    good_feeds.sort(key=lambda x: x['response_time'])
    
    for i, feed in enumerate(good_feeds[:5], 1):
        markdown_content += f"{i}. **{feed['name']}** - {feed['category']} (响应: {feed['response_time']}秒, 文章: {feed['entries_count']}篇)\n"
    
    markdown_content += """

### 注意事项
1. 部分RSS源可能需要特殊处理（如反爬虫机制）
2. 国际网站可能受网络环境影响
3. 建议定期测试RSS源的可用性
4. 对于失败的RSS源，可以尝试备用URL或联系网站管理员

## 📝 测试环境
- 测试工具: Python RSS测试脚本
- 测试时间: """ + summary['test_time'] + """
- 测试数量: """ + str(summary['total_feeds']) + """个RSS源
- 网络环境: 中国境内网络

---

*本报告由RSS测试工具自动生成*
*最后更新: """ + report_date + """*
"""
    
    return markdown_content

def generate_word_document(markdown_content: str, filename: str = None):
    """生成Word文档"""
    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"doc_RSS测试报告_{timestamp}.docx"
    
    # 使用doc_generator生成Word文档
    print(f"正在生成Word文档: {filename}")
    
    # 这里我们将在主程序中调用doc_generator
    return filename

def generate_html_report(markdown_content: str, filename: str = None):
    """生成HTML报告"""
    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"rss_test_report_{timestamp}.html"
    
    # 将Markdown转换为HTML
    html_content = markdown.markdown(markdown_content, extensions=['tables'])
    
    # 添加基本样式
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RSS源测试报告</title>
    <style>
        body {{
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1, h2, h3, h4 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}
        h1 {{ border-bottom-width: 4px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: #3498db;
            color: white;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        .success {{ color: #27ae60; font-weight: bold; }}
        .failed {{ color: #e74c3c; font-weight: bold; }}
        .info-box {{
            background-color: #e8f4fc;
            border-left: 4px solid #3498db;
            padding: 15px;
            margin: 20px 0;
        }}
        code {{
            background-color: #f8f9fa;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #7f8c8d;
            font-size: 0.9em;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        {html_content}
        <div class="footer">
            <p>报告生成时间: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}</p>
            <p>© RSS测试工具 - 自动生成报告</p>
        </div>
    </div>
</body>
</html>"""
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(full_html)
    
    print(f"HTML报告已生成: {filename}")
    return filename

def main():
    """主函数"""
    print("=" * 60)
    print("RSS测试报告生成器 v1.0")
    print("=" * 60)
    
    # 加载测试结果
    data = load_test_results()
    if not data:
        return
    
    # 生成Markdown报告
    print("正在生成Markdown报告...")
    markdown_report = generate_markdown_report(data)
    
    # 保存Markdown报告
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    md_filename = f"rss_test_report_{timestamp}.md"
    
    with open(md_filename, 'w', encoding='utf-8') as f:
        f.write(markdown_report)
    
    print(f"Markdown报告已保存: {md_filename}")
    
    # 生成HTML报告
    print("正在生成HTML报告...")
    html_filename = generate_html_report(markdown_report)
    
    # 生成Word文档（通过doc_generator）
    print("正在准备Word文档内容...")
    
    # 这里我们将在外部调用doc_generator
    print("\n" + "=" * 60)
    print("报告生成完成！")
    print("=" * 60)
    print(f"生成的报告文件:")
    print(f"1. Markdown报告: {md_filename}")
    print(f"2. HTML报告: {html_filename}")
    print(f"3. Word文档: 请使用doc_generator生成")
    print("\n要生成Word文档，请运行:")
    print("python -c \"from doc_generator import generate_document; generate_document('报告内容')\"")
    
    # 显示测试摘要
    summary = data['summary']
    print(f"\n测试摘要:")
    print(f"- 总测试数: {summary['total_feeds']}")
    print(f"- 成功数: {summary['successful_feeds']} (成功率: {summary['success_rate']}%)")
    print(f"- 平均响应时间: {summary['average_response_time']}秒")
    
    return markdown_report

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"生成报告时发生错误: {e}")