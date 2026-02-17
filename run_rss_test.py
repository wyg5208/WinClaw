#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS测试主脚本
整合测试和报告生成功能
"""

import os
import sys
import subprocess
from datetime import datetime

def check_dependencies():
    """检查依赖"""
    required_packages = ['requests', 'feedparser', 'markdown']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"缺少依赖包: {', '.join(missing_packages)}")
        print("请使用以下命令安装:")
        print(f"pip install {' '.join(missing_packages)}")
        return False
    
    return True

def run_rss_test():
    """运行RSS测试"""
    print("=" * 60)
    print("开始RSS源测试")
    print("=" * 60)
    
    # 运行测试脚本
    try:
        import rss_tester
        results, summary = rss_tester.main()
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        return False
    
    return True

def generate_reports():
    """生成报告"""
    print("\n" + "=" * 60)
    print("开始生成报告")
    print("=" * 60)
    
    # 运行报告生成脚本
    try:
        import generate_reports
        markdown_report = generate_reports.main()
        
        if markdown_report:
            # 使用doc_generator生成Word文档
            print("\n正在生成Word文档...")
            generate_word_document(markdown_report)
    
    except Exception as e:
        print(f"生成报告时发生错误: {e}")
        return False
    
    return True

def generate_word_document(markdown_content: str):
    """生成Word文档"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"doc_RSS源测试报告_{timestamp}"
    
    print(f"Word文档将保存为: {filename}.docx")
    
    # 这里需要调用doc_generator工具
    # 由于我们是在WinClaw环境中，可以直接使用工具调用
    print("提示: 请在WinClaw对话中使用doc_generator工具生成Word文档")
    print(f"内容长度: {len(markdown_content)} 字符")
    
    # 保存Markdown内容到临时文件，方便复制
    temp_file = f"rss_report_{timestamp}.md"
    with open(temp_file, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    
    print(f"Markdown内容已保存到: {temp_file}")
    print("您可以将此内容复制到doc_generator中生成Word文档")
    
    return temp_file

def main():
    """主函数"""
    print("RSS源测试与报告生成系统")
    print("版本: 1.0")
    print("=" * 60)
    
    # 检查依赖
    if not check_dependencies():
        print("请先安装依赖包")
        return
    
    # 创建输出目录
    output_dir = "rss_test_results"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 切换到输出目录
    original_dir = os.getcwd()
    os.chdir(output_dir)
    
    try:
        # 运行测试
        test_success = run_rss_test()
        
        if test_success:
            # 生成报告
            report_success = generate_reports()
            
            if report_success:
                print("\n" + "=" * 60)
                print("✅ 所有任务完成！")
                print("=" * 60)
                print("\n生成的文件:")
                print("1. rss_test_results.json - 原始测试数据")
                print("2. rss_test_report_*.md - Markdown格式报告")
                print("3. rss_test_report_*.html - HTML格式报告")
                print("4. 请使用doc_generator生成Word文档")
                
                # 显示当前目录中的文件
                print("\n当前目录中的文件:")
                for file in os.listdir('.'):
                    if file.endswith(('.json', '.md', '.html')):
                        print(f"  - {file}")
            else:
                print("\n❌ 报告生成失败")
        else:
            print("\n❌ RSS测试失败")
    
    finally:
        # 切换回原始目录
        os.chdir(original_dir)
    
    print("\n操作完成！")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()