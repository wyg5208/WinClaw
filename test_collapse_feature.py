"""测试消息收起/展开功能"""
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from src.ui.chat import ChatWidget

def main():
    app = QApplication(sys.argv)
    
    window = QMainWindow()
    window.setWindowTitle("测试消息收起/展开功能")
    window.resize(800, 600)
    
    # 创建中心widget
    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    
    layout = QVBoxLayout(central_widget)
    
    # 创建聊天组件
    chat = ChatWidget()
    layout.addWidget(chat)
    
    # 添加测试消息
    chat.add_user_message("你好，请介绍一下Python编程语言")
    
    # 添加一个长的AI消息
    long_message = """Python是一种高级编程语言，具有以下特点：

1. **简洁易读**：Python的语法简洁明了，接近自然语言，非常适合初学者。

2. **功能强大**：
   - 支持面向对象编程
   - 支持函数式编程
   - 拥有丰富的标准库
   - 第三方库生态系统完善

3. **应用广泛**：
   - Web开发（Django、Flask）
   - 数据科学和机器学习（NumPy、Pandas、TensorFlow）
   - 自动化脚本
   - 游戏开发
   - 桌面应用开发

4. **跨平台**：可以在Windows、Linux、macOS等多个平台上运行。

5. **开源免费**：Python是开源的，任何人都可以免费使用和修改。

示例代码：
```python
def hello_world():
    print("Hello, World!")
    
if __name__ == "__main__":
    hello_world()
```

Python的设计哲学强调代码的可读性和简洁的语法，这使得开发者能够用更少的代码表达更多的想法。"""
    
    chat.add_ai_message(long_message)
    
    # 添加另一条用户消息
    chat.add_user_message("谢谢介绍！")
    
    # 添加短消息
    chat.add_ai_message("不客气！如果你有任何其他问题，随时问我。")
    
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
