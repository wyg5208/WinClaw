import sys
import os
import traceback

# 设置环境变量
os.environ['DEEPSEEK_API_KEY'] = 'test_key'

# 添加当前目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print(f"当前目录: {current_dir}")
print(f"Python 路径: {sys.executable}")
print(f"系统路径: {sys.path[:3]}")

try:
    # 尝试导入
    print("尝试导入 src.ui.gui_app...")
    from src.ui.gui_app import main
    print("导入成功！")
    
    print("尝试启动 GUI...")
    main()
    
except Exception as e:
    print(f"错误: {type(e).__name__}: {e}")
    traceback.print_exc()