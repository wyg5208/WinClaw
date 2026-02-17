#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安装RSS测试脚本的依赖
"""

import subprocess
import sys

def install_packages():
    """安装所需的Python包"""
    packages = [
        'requests',
        'feedparser',
        'markdown'
    ]
    
    print("正在安装RSS测试脚本所需的依赖包...")
    print("=" * 50)
    
    for package in packages:
        print(f"安装 {package}...")
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
            print(f"✅ {package} 安装成功")
        except subprocess.CalledProcessError:
            print(f"❌ {package} 安装失败")
            print("请尝试手动安装: pip install", package)
        print("-" * 30)
    
    print("\n" + "=" * 50)
    print("依赖安装完成！")
    print("\n现在可以运行以下命令进行测试:")
    print("1. python run_rss_test.py - 完整测试和报告生成")
    print("2. python rss_tester.py - 仅测试RSS源")
    print("3. python generate_reports.py - 仅生成报告")

if __name__ == "__main__":
    install_packages()