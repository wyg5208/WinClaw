import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # 尝试导入 gui_app
    from src.ui.gui_app import main
    print("导入成功！")
    
    # 尝试运行
    print("尝试启动 GUI...")
    main()
    
except Exception as e:
    print(f"导入失败: {e}")
    import traceback
    traceback.print_exc()