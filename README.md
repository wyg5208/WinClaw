# WinClaw

> 轻量级 Windows AI 桌面智能体 - 让 AI 成为你的专属 Windows 助手

WinClaw 是一款基于大语言模型的 Windows 桌面 AI 助手，能够通过自然语言指令帮助你完成各种 Windows 操作任务。

## 功能特性

### 核心能力

- **AI 对话交互**：支持多模型接入（DeepSeek、OpenAI、Claude、Llama 等），自然语言理解与回复
- **智能工具调用**：AI 能够自动调用各种工具执行实际操作，而不仅仅是对话
- **工作流引擎**：支持定义多步骤工作流，自动化复杂任务
- **定时任务**：内置 Cron 定时任务系统，支持计划任务管理

### 实用工具集（22+ 工具）

| 类别 | 工具 |
|------|------|
| **系统操作** | Shell 命令执行、文件管理、屏幕截图、应用控制 |
| **浏览器** | 网页自动化、搜索（本地 + Web） |
| **剪贴板** | 文本/图片复制粘贴 |
| **通知** | 系统Toast通知 |
| **多媒体** | 语音输入（STT）、语音输出（TTS）、OCR 文字识别 |
| **生活管理** | 日程管理、健康记录、服药提醒、日记、记账 |
| **实用计算** | 计算器、天气查询、日期时间、统计 |
| **知识库** | 本地知识库管理、对话历史 |
| **MCP** | MCP 服务器桥接 |

### 用户体验

- **双模式运行**：CLI 终端模式 + GUI 图形界面模式
- **系统托盘**：最小化到托盘，后台运行
- **全局快捷键**：Win+Shift+Space 快速唤起
- **亮/暗主题**：支持跟随系统或手动切换
- **流式输出**：AI 回复实时逐字显示，响应快速
- **生成空间**：AI 生成的文件自动归档管理

## 技术架构

```
winclaw/
├── src/
│   ├── core/          # 核心模块（Agent、事件总线、会话管理、工作流）
│   ├── models/        # 模型管理（注册、选择、成本追踪）
│   ├── tools/         # 工具集（22+ 工具）
│   ├── ui/            # PySide6 图形界面
│   ├── permissions/   # 权限管理
│   └── updater/       # 自动更新
├── config/            # 配置文件（models.toml、tools.json）
├── tests/             # 单元测试和集成测试
├── build/             # PyInstaller 构建产物
└── dist/              # 发布包
```

### 技术栈

- **AI 框架**：LiteLLM + OpenAI SDK
- **GUI 框架**：PySide6 + qasync
- **自动化**：Playwright、pywinauto、pyautogui
- **语音**：Whisper、pyttsx3
- **构建**：PyInstaller + NSIS

## 快速开始

### 环境要求

- Python 3.11+
- Windows 10/11

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/wyg5208/WinClaw.git
cd WinClaw/winclaw

# 2. 创建虚拟环境（推荐）
python -m venv venv
.\venv\Scripts\activate

# 3. 安装依赖
pip install -e ".[all]"

# 或按需安装
pip install -e .           # 核心依赖
pip install -e ".[gui]"    # GUI 依赖
pip install -e ".[browser]" # 浏览器自动化
```

### 配置

1. 复制环境变量模板：
```bash
copy .env.example .env
```

2. 编辑 `.env`，添加你的 API Key：
```env
DEEPSEEK_API_KEY=your_key_here
# 或其他模型 API Key
```

### 运行

```bash
# CLI 模式
python -m src.app

# GUI 模式
python -m src.ui.gui_app

# 或使用快捷脚本
.\start_winclaw.bat      # CLI
.\start_winclaw_gui.bat  # GUI
```

## 项目里程碑

| 里程碑 | 状态 | 说明 |
|--------|------|------|
| M0 - MVP | ✅ | CLI 版本，核心链路跑通 |
| M1 - 核心架构 | ✅ | 配置驱动、事件总线、会话管理 |
| M2 - GUI 应用 | ✅ | 完整桌面应用，8 种工具 |
| M3 - 功能完整 | ✅ | 工作流、语音、多模态、打包 |
| M4 - 正式发布 | 进行中 | 插件系统、性能优化 |

### 已完成功能

- ✅ Phase 0：MVP 快速验证（500行代码跑通核心链路）
- ✅ Phase 1：核心骨架（配置系统、事件总线、会话管理、权限审计）
- ✅ Phase 2：GUI + 扩展工具（PySide6 界面、22+ 工具）
- ✅ Phase 3：高级功能（工作流引擎、定时任务、语音交互、自动更新、打包安装）

## 文档

- [安装指南](INSTALL_GUIDE.md)
- [LLM API 配置指南](llm_api_guide/)
- [开发文档](docs/)
- [研发方案与进度表](../WinClaw详细研发方案与进度表.md)

## 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_smoke.py
pytest tests/test_integration.py

# 带覆盖率
pytest --cov=src tests/
```

## 许可证

MIT License

## 作者

WinClaw Team

---

让 AI 成为你的 Windows 效率助手！
