#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
童话故事生成器 - 启动器
简化启动流程，提供图形化菜单
"""

import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path

def clear_screen():
    """清屏"""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    """打印标题"""
    print("╔══════════════════════════════════════════════════════╗")
    print("║                童话故事定时生成器                    ║")
    print("║                 Magic Story Generator                ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

def check_dependencies():
    """检查依赖"""
    print("🔍 检查系统环境...")
    
    # 检查Python
    try:
        result = subprocess.run([sys.executable, "--version"], 
                              capture_output=True, text=True)
        print(f"   ✓ Python版本: {result.stdout.strip()}")
    except:
        print("   ✗ 未找到Python")
        return False
    
    # 检查schedule库
    try:
        import schedule
        print("   ✓ schedule库已安装")
    except ImportError:
        print("   ⚠ schedule库未安装，正在安装...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "schedule"])
            print("   ✓ schedule库安装成功")
        except:
            print("   ✗ schedule库安装失败")
            return False
    
    # 检查输出目录
    output_dir = Path("fairy_tales")
    if not output_dir.exists():
        output_dir.mkdir()
        print(f"   ✓ 创建输出目录: {output_dir}")
    
    print()
    return True

def show_stories():
    """显示故事列表"""
    output_dir = Path("fairy_tales")
    
    if not output_dir.exists() or not any(output_dir.iterdir()):
        print("📭 尚未生成任何故事")
        return
    
    txt_files = list(output_dir.glob("*.txt"))
    if not txt_files:
        print("📭 没有找到故事文件")
        return
    
    print(f"📚 找到 {len(txt_files)} 个故事:")
    print("-" * 60)
    
    for i, file in enumerate(sorted(txt_files, key=lambda x: x.stat().st_mtime, reverse=True)[:10], 1):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                second_line = f.readline().strip()
            
            title = first_line.replace("标题：", "")
            date_str = second_line.replace("生成时间：", "")
            
            # 解析日期
            try:
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                date_display = date_obj.strftime("%Y-%m-%d %H:%M")
            except:
                date_display = date_str[:16]
            
            print(f"{i:2d}. {title}")
            print(f"    生成时间: {date_display}")
            print(f"    文件: {file.name}")
            print()
            
        except Exception as e:
            print(f"{i:2d}. 读取文件失败: {file.name}")
    
    print("-" * 60)

def show_stats():
    """显示统计信息"""
    output_dir = Path("fairy_tales")
    
    if not output_dir.exists():
        print("📊 统计信息:")
        print("   总故事数: 0")
        print("   输出目录: 不存在")
        return
    
    json_files = list(output_dir.glob("*.json"))
    txt_files = list(output_dir.glob("*.txt"))
    
    total_size = sum(f.stat().st_size for f in output_dir.iterdir())
    
    print("📊 统计信息:")
    print(f"   总故事数: {len(json_files)}")
    print(f"   文本文件: {len(txt_files)}")
    print(f"   总文件大小: {total_size/1024:.1f} KB")
    print(f"   输出目录: {output_dir.absolute()}")
    
    if json_files:
        latest_file = max(json_files, key=lambda x: x.stat().st_mtime)
        latest_time = datetime.fromtimestamp(latest_file.stat().st_mtime)
        print(f"   最后生成: {latest_time.strftime('%Y-%m-%d %H:%M:%S')}")

def run_generator_once():
    """运行一次生成器"""
    print("🎨 正在生成童话故事...")
    print("-" * 40)
    
    try:
        # 导入并运行生成器
        sys.path.append('.')
        from fairy_tale_generator import FairyTaleGenerator
        
        generator = FairyTaleGenerator()
        story = generator.generate_and_save()
        
        if story:
            print(f"✨ 成功生成故事: {story['title']}")
            print(f"📖 主角: {story['character']}")
            print(f"🏰 地点: {story['place']}")
            print(f"💡 寓意: {story['moral']}")
            print(f"💾 已保存到 fairy_tales/ 目录")
        else:
            print("❌ 生成故事失败")
            
    except Exception as e:
        print(f"❌ 运行生成器时出错: {e}")
    
    print("-" * 40)

def start_scheduler():
    """启动定时调度器"""
    print("⏰ 启动定时生成器...")
    print("   每隔1小时自动生成一个童话故事")
    print("   故事将保存到 'fairy_tales' 目录")
    print("   按 Ctrl+C 停止")
    print()
    
    try:
        # 导入并启动调度器
        sys.path.append('.')
        from setup_scheduler import FairyTaleScheduler
        
        scheduler = FairyTaleScheduler()
        scheduler.start_scheduler(1)
        
        print("✅ 定时生成器已启动")
        print("🔄 后台运行中...")
        
        # 保持程序运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 停止定时生成器...")
            scheduler.stop_scheduler()
            
    except Exception as e:
        print(f"❌ 启动调度器时出错: {e}")

def show_windows_task_guide():
    """显示Windows定时任务设置指南"""
    print("🖥️  Windows定时任务设置指南")
    print("=" * 60)
    print("按照以下步骤设置系统定时任务:")
    print()
    print("1. 打开'任务计划程序'")
    print("   按 Win+R，输入 taskschd.msc，回车")
    print()
    print("2. 创建基本任务")
    print("   右侧点击'创建基本任务'")
    print()
    print("3. 输入任务信息")
    print("   名称: 童话故事生成器")
    print("   描述: 每隔1小时自动生成童话故事")
    print()
    print("4. 设置触发器")
    print("   选择'每天'")
    print("   开始时间: 当前时间")
    print("   重复任务间隔: 1小时")
    print("   持续时间: 无限期")
    print()
    print("5. 设置操作")
    print("   选择'启动程序'")
    print(f"   程序或脚本: {sys.executable}")
    print(f"   添加参数: fairy_tale_generator.py")
    print(f"   起始于: {os.getcwd()}")
    print()
    print("6. 完成创建")
    print("   点击'完成'")
    print()
    print("=" * 60)
    print("✅ 设置完成后，系统会自动每小时运行生成器")

def main_menu():
    """主菜单"""
    if not check_dependencies():
        print("❌ 环境检查失败，请确保Python已正确安装")
        input("按Enter键退出...")
        return
    
    while True:
        clear_screen()
        print_header()
        
        print("请选择操作:")
        print("1. 🎨 手动生成一个童话故事")
        print("2. ⏰ 启动定时生成器（每隔1小时）")
        print("3. 📚 查看故事列表")
        print("4. 📊 查看统计信息")
        print("5. 🖥️  设置Windows定时任务")
        print("6. ❓ 查看帮助")
        print("7. 🚪 退出")
        print()
        
        choice = input("请输入选项 (1-7): ").strip()
        
        if choice == "1":
            clear_screen()
            print_header()
            run_generator_once()
            input("\n按Enter键返回菜单...")
            
        elif choice == "2":
            clear_screen()
            print_header()
            start_scheduler()
            input("\n按Enter键返回菜单...")
            
        elif choice == "3":
            clear_screen()
            print_header()
            show_stories()
            input("\n按Enter键返回菜单...")
            
        elif choice == "4":
            clear_screen()
            print_header()
            show_stats()
            input("\n按Enter键返回菜单...")
            
        elif choice == "5":
            clear_screen()
            print_header()
            show_windows_task_guide()
            input("\n按Enter键返回菜单...")
            
        elif choice == "6":
            clear_screen()
            print_header()
            print("❓ 帮助信息")
            print("=" * 60)
            print("童话故事定时生成器使用说明:")
            print()
            print("📌 功能:")
            print("   • 自动生成独特的童话故事")
            print("   • 每隔1小时自动运行")
            print("   • 保存为JSON和TXT格式")
            print()
            print("📁 文件位置:")
            print("   • 故事文件: fairy_tales/ 目录")
            print("   • 日志文件: fairy_tale_generator.log")
            print("   • 调度日志: fairy_tale_scheduler.log")
            print()
            print("⚙️  自定义:")
            print("   • 修改生成间隔: 编辑 setup_scheduler.py")
            print("   • 添加故事元素: 编辑 fairy_tale_generator.py")
            print()
            print("🛠️  故障排除:")
            print("   • 确保Python已安装并添加到PATH")
            print("   • 运行: pip install schedule")
            print("   • 检查日志文件获取错误信息")
            print("=" * 60)
            input("\n按Enter键返回菜单...")
            
        elif choice == "7":
            print("\n感谢使用童话故事生成器！")
            print("再见！ 👋")
            time.sleep(1)
            break
            
        else:
            print("❌ 无效选项，请重新输入")
            time.sleep(1)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n程序出错: {e}")
        import traceback
        traceback.print_exc()
        input("\n按Enter键退出...")