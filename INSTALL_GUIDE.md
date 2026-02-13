# 童话故事定时生成器 - 安装和运行指南

## 系统要求

- Windows 7/8/10/11
- Python 3.6 或更高版本
- 至少 100MB 可用磁盘空间

## 第一步：安装Python

如果你还没有安装Python：

1. 访问 [Python官网](https://www.python.org/downloads/)
2. 下载最新版本的Python（3.6+）
3. 安装时**务必勾选** "Add Python to PATH"
4. 完成安装

验证Python安装：
```cmd
python --version
```

## 第二步：获取项目文件

你已经有了所有必要的文件：
- `fairy_tale_generator.py` - 核心故事生成器
- `setup_scheduler.py` - 定时任务设置工具
- `start_fairy_tales.py` - 简化启动脚本
- `README.md` - 说明文档

## 第三步：安装依赖

打开命令提示符（CMD）或 PowerShell，导航到项目目录：

```cmd
cd D:\python_projects\openclaw_demo\winclaw
```

安装所需库：
```cmd
pip install schedule
```

## 第四步：测试运行

### 测试1：生成单个故事
```cmd
python fairy_tale_generator.py
```

你应该看到类似输出：
```
============================================================
童话故事生成器
============================================================

============================================================
最新生成的童话故事：
============================================================
标题：智慧图书馆的智慧的秘密
生成时间：2026-02-13T08:12:23.769374
故事ID：tale_20260213_081223

故事内容：
----------------------------------------
在遥远的智慧图书馆，住着一位聪明的狐狸...
----------------------------------------
寓意：希望永远存在

统计信息：
总故事数：1
输出目录：D:\python_projects\openclaw_demo\winclaw\fairy_tales

============================================================
童话故事生成完成！
============================================================
```

检查生成的文件：
```cmd
dir fairy_tales
```

### 测试2：使用简化启动脚本
```cmd
python start_fairy_tales.py
```

选择选项 `2` 测试手动生成。

## 第五步：设置定时任务（三种方法）

### 方法A：使用后台调度器（最简单）

运行简化启动脚本并选择选项1：
```cmd
python start_fairy_tales.py
```

选择 `1`，程序会在后台运行，每隔1小时自动生成故事。

**保持命令窗口打开**，程序会持续运行。

### 方法B：使用完整控制台

```cmd
python setup_scheduler.py
```

主菜单选项：
1. 启动定时生成器（后台运行）
2. 手动生成一个故事
3. 查看状态和故事列表
4. 设置Windows定时任务
5. 停止定时生成器
6. 退出

### 方法C：设置Windows系统定时任务（推荐）

1. 运行设置工具：
   ```cmd
   python setup_scheduler.py
   ```

2. 选择选项 `4`：设置Windows定时任务

3. 按照屏幕提示操作：
   ```
   设置Windows定时任务（手动步骤）：
   ========================================
   1. 打开'任务计划程序' (taskschd.msc)
   2. 点击'创建基本任务'
   3. 输入名称：'童话故事生成器'
   4. 触发器选择：'每天'
   5. 开始时间：设置当前时间
   6. 重复任务间隔：1小时，持续时间：无限期
   7. 操作：'启动程序'
   8. 程序或脚本：输入python的完整路径
   9. 添加参数：fairy_tale_generator.py
   10. 起始于：输入脚本所在目录
   11. 完成创建
   ========================================
   ```

4. 系统会显示配置信息：
   ```
   Python路径：C:\Users\你的用户名\AppData\Local\Programs\Python\Python39\python.exe
   脚本路径：D:\python_projects\openclaw_demo\winclaw\fairy_tale_generator.py
   工作目录：D:\python_projects\openclaw_demo\winclaw
   ```

## 第六步：验证定时任务

### 验证方法1：查看日志文件
```cmd
type fairy_tale_generator.log
type fairy_tale_scheduler.log
```

### 验证方法2：查看生成的故事
```cmd
dir fairy_tales
```

### 验证方法3：手动触发测试
等待1小时，检查是否有新故事生成。

## 第七步：管理和维护

### 查看所有故事
运行控制台并选择选项3：
```cmd
python setup_scheduler.py
```
选择 `3` 查看状态和故事列表。

### 手动生成故事
```cmd
python fairy_tale_generator.py
```
或通过控制台选择选项2。

### 停止后台调度器
如果使用后台调度器，按 `Ctrl+C` 停止。

### 删除Windows定时任务
1. 打开"任务计划程序"
2. 找到"童话故事生成器"任务
3. 右键选择"删除"

## 故障排除

### 问题1：Python命令不可用
**症状**：`'python' 不是内部或外部命令`
**解决**：
1. 重新安装Python，确保勾选"Add Python to PATH"
2. 或使用完整路径：`C:\Python39\python.exe`

### 问题2：缺少schedule库
**症状**：`ModuleNotFoundError: No module named 'schedule'`
**解决**：
```cmd
pip install schedule
```

### 问题3：权限问题
**症状**：无法创建文件或目录
**解决**：
1. 以管理员身份运行命令提示符
2. 确保有写入权限

### 问题4：定时任务不运行
**解决**：
1. 检查任务计划程序中任务的状态
2. 确保Python路径正确
3. 检查日志文件中的错误信息

### 问题5：编码问题（中文乱码）
**解决**：
1. 确保Python文件使用UTF-8编码
2. 在命令提示符中设置代码页：
   ```cmd
   chcp 65001
   ```

## 高级配置

### 修改生成间隔
编辑 `setup_scheduler.py`，找到：
```python
scheduler.start_scheduler(1)  # 1小时
```
改为你想要的间隔（小时）。

### 自定义故事元素
编辑 `fairy_tale_generator.py`，在 `__init__` 方法中添加更多元素到对应的列表中。

### 修改输出目录
在代码中修改：
```python
generator = FairyTaleGenerator(output_dir="my_custom_folder")
```

## 安全注意事项

1. **文件位置**：故事保存在本地，不会上传到互联网
2. **资源使用**：程序占用资源很少，不会影响系统性能
3. **权限**：只需要文件读写权限
4. **数据安全**：所有数据保存在本地，可随时删除

## 卸载

1. 停止所有运行中的程序（按Ctrl+C）
2. 删除Windows定时任务（如果设置了）
3. 删除项目目录（可选）
4. 删除依赖（可选）：
   ```cmd
   pip uninstall schedule
   ```

## 获取帮助

如果遇到问题：
1. 查看日志文件：`fairy_tale_generator.log`
2. 检查错误信息
3. 确保按照步骤操作
4. 验证Python安装和路径

## 开始你的童话之旅！

现在你已经成功安装了童话故事定时生成器。系统会每隔1小时自动生成一个独特的童话故事，保存在 `fairy_tales` 目录中。

享受这些自动生成的童话故事吧！每个故事都是独一无二的，包含不同的角色、情节和寓意。

---
*让魔法在每个小时绽放！*