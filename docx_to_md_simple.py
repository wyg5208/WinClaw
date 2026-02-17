#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的 DOCX 到 MD 转换函数
可在 WinClaw 中直接调用
"""

import os
import mammoth

def docx_to_markdown(docx_path, md_path=None):
    """
    将 DOCX 文件转换为 Markdown 格式
    
    Args:
        docx_path: DOCX 文件路径
        md_path: 输出的 MD 文件路径（可选，默认同目录同名）
    
    Returns:
        dict: 转换结果
    """
    try:
        # 检查文件是否存在
        if not os.path.exists(docx_path):
            return {
                'success': False,
                'error': f'文件不存在: {docx_path}'
            }
        
        # 检查文件扩展名
        if not docx_path.lower().endswith('.docx'):
            return {
                'success': False,
                'error': '文件必须是 .docx 格式'
            }
        
        # 确定输出路径
        if md_path is None:
            base_name = os.path.splitext(docx_path)[0]
            md_path = f"{base_name}.md"
        
        # 读取并转换 DOCX 文件
        with open(docx_path, 'rb') as docx_file:
            result = mammoth.convert_to_markdown(docx_file)
            markdown_text = result.value
        
        # 保存 MD 文件
        with open(md_path, 'w', encoding='utf-8') as md_file:
            md_file.write(markdown_text)
        
        # 获取文件信息
        input_size = os.path.getsize(docx_path)
        output_size = os.path.getsize(md_path)
        
        return {
            'success': True,
            'docx_path': docx_path,
            'md_path': md_path,
            'input_size': input_size,
            'output_size': output_size,
            'markdown_preview': markdown_text[:500] + '...' if len(markdown_text) > 500 else markdown_text
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

def batch_docx_to_markdown(directory, output_dir=None):
    """
    批量转换目录中的所有 DOCX 文件
    
    Args:
        directory: 包含 DOCX 文件的目录
        output_dir: 输出目录（可选）
    
    Returns:
        dict: 批量转换结果
    """
    try:
        import glob
        
        # 获取所有 DOCX 文件
        docx_files = glob.glob(os.path.join(directory, '*.docx'))
        
        if not docx_files:
            return {
                'success': False,
                'error': f'在目录 {directory} 中未找到 .docx 文件'
            }
        
        results = []
        success_count = 0
        
        for docx_file in docx_files:
            try:
                # 确定输出路径
                if output_dir:
                    base_name = os.path.basename(docx_file)
                    base_name_no_ext = os.path.splitext(base_name)[0]
                    md_file = os.path.join(output_dir, f"{base_name_no_ext}.md")
                else:
                    md_file = None
                
                # 转换文件
                result = docx_to_markdown(docx_file, md_file)
                results.append({
                    'file': os.path.basename(docx_file),
                    'success': result['success'],
                    'md_file': result.get('md_path') if result['success'] else None,
                    'message': result.get('error', '转换成功') if not result['success'] else '转换成功'
                })
                
                if result['success']:
                    success_count += 1
                    
            except Exception as e:
                results.append({
                    'file': os.path.basename(docx_file),
                    'success': False,
                    'message': f'转换失败: {str(e)}'
                })
        
        return {
            'success': True,
            'total_files': len(docx_files),
            'success_count': success_count,
            'failed_count': len(docx_files) - success_count,
            'results': results
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'批量转换失败: {str(e)}'
        }

if __name__ == '__main__':
    # 测试代码
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python docx_to_md_simple.py <docx文件路径> [输出md文件路径]")
        print("或: python docx_to_md_simple.py --batch <目录路径> [输出目录]")
        sys.exit(1)
    
    if sys.argv[1] == '--batch':
        if len(sys.argv) < 3:
            print("批量转换用法: python docx_to_md_simple.py --batch <目录路径> [输出目录]")
            sys.exit(1)
        
        directory = sys.argv[2]
        output_dir = sys.argv[3] if len(sys.argv) > 3 else None
        
        result = batch_docx_to_markdown(directory, output_dir)
        
        if result['success']:
            print(f"批量转换完成:")
            print(f"  总文件数: {result['total_files']}")
            print(f"  成功: {result['success_count']}")
            print(f"  失败: {result['failed_count']}")
            
            for item in result['results']:
                status = "✅" if item['success'] else "❌"
                print(f"  {status} {item['file']}: {item['message']}")
        else:
            print(f"❌ {result['error']}")
    
    else:
        docx_path = sys.argv[1]
        md_path = sys.argv[2] if len(sys.argv) > 2 else None
        
        result = docx_to_markdown(docx_path, md_path)
        
        if result['success']:
            print(f"✅ 转换成功!")
            print(f"  DOCX 文件: {result['docx_path']}")
            print(f"  MD 文件: {result['md_path']}")
            print(f"  大小: {result['input_size']/1024:.1f}KB → {result['output_size']/1024:.1f}KB")
            print(f"\n预览:")
            print(result['markdown_preview'])
        else:
            print(f"❌ {result['error']}")