#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DOCX 到 MD 文件转换器
支持将 Word 文档转换为 Markdown 格式
"""

import os
import sys
import argparse
from pathlib import Path

def convert_docx_to_md(docx_path, md_path=None):
    """
    将 DOCX 文件转换为 MD 文件
    
    Args:
        docx_path: DOCX 文件路径
        md_path: MD 文件输出路径（可选，默认与 DOCX 同目录）
    
    Returns:
        str: 转换后的 MD 文件路径
    """
    try:
        import mammoth
        
        # 检查文件是否存在
        if not os.path.exists(docx_path):
            raise FileNotFoundError(f"文件不存在: {docx_path}")
        
        # 确定输出路径
        if md_path is None:
            docx_dir = os.path.dirname(docx_path)
            docx_name = os.path.splitext(os.path.basename(docx_path))[0]
            md_path = os.path.join(docx_dir, f"{docx_name}.md")
        
        # 读取并转换 DOCX 文件
        with open(docx_path, 'rb') as docx_file:
            result = mammoth.convert_to_markdown(docx_file)
            markdown_text = result.value
        
        # 保存 MD 文件
        with open(md_path, 'w', encoding='utf-8') as md_file:
            md_file.write(markdown_text)
        
        # 获取文件大小
        input_size = os.path.getsize(docx_path)
        output_size = os.path.getsize(md_path)
        
        return {
            'success': True,
            'md_path': md_path,
            'input_size': input_size,
            'output_size': output_size,
            'message': f'转换成功！DOCX: {input_size/1024:.1f}KB → MD: {output_size/1024:.1f}KB'
        }
        
    except ImportError:
        return {
            'success': False,
            'error': '需要安装 mammoth 库，请运行: pip install mammoth'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'转换失败: {str(e)}'
        }

def batch_convert_docx_to_md(directory, output_dir=None):
    """
    批量转换目录中的所有 DOCX 文件
    
    Args:
        directory: 目录路径
        output_dir: 输出目录（可选，默认与输入目录相同）
    
    Returns:
        list: 转换结果列表
    """
    results = []
    
    # 遍历目录中的 DOCX 文件
    for file in Path(directory).glob('*.docx'):
        try:
            # 确定输出路径
            if output_dir:
                output_path = os.path.join(output_dir, f"{file.stem}.md")
            else:
                output_path = os.path.join(directory, f"{file.stem}.md")
            
            # 转换文件
            result = convert_docx_to_md(str(file), output_path)
            results.append({
                'file': file.name,
                'success': result['success'],
                'md_path': result.get('md_path'),
                'message': result.get('message', result.get('error', '未知错误'))
            })
            
        except Exception as e:
            results.append({
                'file': file.name,
                'success': False,
                'error': str(e)
            })
    
    return results

def main():
    parser = argparse.ArgumentParser(description='将 DOCX 文件转换为 Markdown 格式')
    parser.add_argument('input', help='输入文件或目录路径')
    parser.add_argument('-o', '--output', help='输出文件或目录路径')
    parser.add_argument('-b', '--batch', action='store_true', help='批量转换目录中的所有 DOCX 文件')
    
    args = parser.parse_args()
    
    if args.batch:
        # 批量转换模式
        if not os.path.isdir(args.input):
            print(f"错误: {args.input} 不是目录")
            sys.exit(1)
        
        print(f"批量转换目录: {args.input}")
        results = batch_convert_docx_to_md(args.input, args.output)
        
        print(f"\n转换完成，共处理 {len(results)} 个文件:")
        for result in results:
            status = "✅ 成功" if result['success'] else "❌ 失败"
            print(f"  {status} {result['file']}: {result['message']}")
    
    else:
        # 单个文件转换模式
        if not os.path.isfile(args.input):
            print(f"错误: {args.input} 不是文件")
            sys.exit(1)
        
        print(f"转换文件: {args.input}")
        result = convert_docx_to_md(args.input, args.output)
        
        if result['success']:
            print(f"✅ {result['message']}")
            print(f"📄 输出文件: {result['md_path']}")
        else:
            print(f"❌ {result['error']}")
            sys.exit(1)

if __name__ == '__main__':
    main()