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

## 版本日志

### v1.2.1 BUG修复 2026年2月17日

**定时任务系统稳定性修复**

1. **修复定时任务 UI 编辑对话框崩溃**：QHBoxLayout 没有 setVisible 方法，将触发类型切换控件包装为 QWidget
2. **修复定时任务参数缺失导致 KeyError 崩溃**：所有 cron 动作方法增加参数验证，返回清晰错误提示
3. **修复 AI 误用 Linux 命令创建定时任务**：
   - 增强 System Prompt 定时任务工具选择指南，引导 AI 使用 add_ai_task 而非 add_cron
   - 工具描述明确区分 Shell 命令任务和 AI 任务
   - 任务恢复时自动检测并清理使用 Linux 命令（如 notify_send）的无效任务
   - 命令执行前预检查，发现无效命令直接移除任务
4. **修复文件追加结果失败**：`_handle_ai_task_result` 中改用 `execute("write", {append: True})` 替代不存在的 `file_tool.read/write` 方法
5. **修复命令执行编码问题**：subprocess 指定 `encoding='utf-8'` + `errors='replace'`，避免 GBK 解码错误
6. **改善 file.write 受限提示**：被拒绝的文件类型错误信息建议使用 shell.run 替代

### v1.2.0 更新日志 2026年2月18日

**录音功能整体优化**

1. **新增 `record_audio` 录音保存动作**：
   - VoiceInputTool 新增纯录音动作，录制音频并保存为 WAV 文件
   - 支持自定义保存路径或自动生成到 `generated/audio/` 目录
   - AI Agent 可独立调用录音功能，无需同时做语音转文字

2. **VAD 智能录音（说完自动停止）**：
   - 基于 RMS 能量阈值的语音活动检测（Voice Activity Detection）
   - 使用 sounddevice InputStream 流式录音，检测到持续静音后自动停止
   - 可配置参数：静音阈值、静音持续时间、最大录音时长
   - 最短录音保护（1秒），防止误触发

3. **修复持续对话模式信号链断裂**：
   - 修复对话模式只能对话一次的核心 Bug
   - 根因：gui_app 的 TTS 路径（VoiceOutputTool）播放完毕后不通知 ConversationManager，导致状态机卡在 THINKING 状态
   - 修复方案：对话模式下统一走 conversation TTS 路径（TTSPlayer），正确触发 `on_tts_finished()` 恢复监听
   - 补充：TTS 未开启时也正确恢复监听状态

4. **录音配置化**：
   - 移除 gui_app.py 中多处硬编码的 5 秒录音时长
   - 新增 `[voice]` 配置节：`max_duration`、`auto_stop`、`silence_threshold`、`silence_duration`
   - 录音弹窗支持 VAD 模式 UI（显示已录时长，说完自动停止提示）

### v1.1.0 更新日志 2026年2月17日

**Phase 7：全链路追踪与新工具纳入规范**

1. **TaskTrace 全链路追踪系统**（新增 `task_trace.py`）：
   - 记录用户请求从意图识别到任务完成的完整轨迹
   - 数据结构：trace_id、session_id、意图识别结果、工具暴露策略、工具调用序列、最终状态
   - 敏感信息自动脱敏（api_key、password、token 等）
   - JSONL 文件存储，按日期分文件，自动清理过期文件
   - 配置项：`[agent.trace] enabled/trace_dir/max_output_preview/max_trace_days`

2. **agent.py 采集埋点**：
   - chat() 和 chat_stream() 方法完整采集轨迹数据
   - 记录每次工具调用的参数、状态、耗时、错误信息
   - 记录层级升级事件

3. **全链路一致性校验脚本**（新增 `validate_tool_chain.py`）：
   - 7 项一致性检查：INTENT_TOOL_MAPPING 覆盖、引用有效性、INTENT_PRIORITY_MAP 引用、_extract_tool_name 覆盖、dependencies 引用、_build_init_kwargs 覆盖、三表 key 对齐
   - 支持 MCP 动态工具识别
   - 支持 `--fix-suggestions` 输出修复建议

4. **新工具纳入规范**（`tools.json` onboarding_checklist）：
   - 10 项标准化检查清单
   - 确保新工具在全链路中一致注册

5. **工具废弃流程**：
   - 工具配置支持 `deprecated`、`deprecation_message`、`migrate_to` 字段
   - 废弃工具调用时返回友好提示和替代方案
   - chat() 和 chat_stream() 方法均支持

6. **离线分析脚本**（新增 `analyze_traces.py`）：
   - 意图识别准确率统计
   - 工具使用频率分析
   - 失败模式识别
   - 层级升级频率统计
   - 支持按日期/最近 N 天/全部分析

### v1.0.24 更新日志 2026年2月17日

**Phase 6：工具调用全链路优化**

1. **渐进式工具暴露引擎**（新增 `tool_exposure.py`）：
   - 根据意图置信度分三层暴露工具 Schema（推荐集 ~10 → 扩展集 ~20 → 全量集 35+）
   - 核心工具（shell/file/screen/search）始终保留
   - 连续失败 >= 2 次自动升级到更大工具集

2. **多维度意图识别增强**（`prompts.py`）：
   - 10 个意图维度关键词匹配 + 归一化置信度评估（0.0-1.0）
   - 意图-工具映射表、意图-优先级映射表
   - 可选的模型辅助意图分类（默认关闭）

3. **Schema 动态优先级标注**：
   - 在工具 description 前添加 `[推荐]`/`[备选]` 前缀引导模型决策
   - 不删除任何工具，只做标注引导

4. **单次工具调用数量限制**：
   - 硬性限制 `MAX_TOOLS_PER_CALL = 3`，直接拦截超限调用
   - 新增前置校验器模块（`tool_validator.py`）

5. **分级错误反馈**（`base.py`）：
   - 首次失败返回简短版、第 2 次返回标准版（含建议）、第 3 次+返回详细版

6. **工具依赖自动解析**（`tools.json`）：
   - 通过 `dependencies.input_sources` 字段避免过滤掉内容源工具

7. **任务锚定机制优化**（`agent.py`）：
   - 锚定消息包含执行状态摘要（步数、工具调用次数、连续失败次数）

8. **审计日志增强**（`audit.py`）：
   - 新增 intent/confidence/tool_tier/consecutive_failures/user_input 字段

9. **配置化开关**（`default.toml [agent.tool_optimization]`）：
   - 所有优化功能可通过独立开关启用/关闭，支持随时回退

### v1.0.23 更新日志 2026年2月16日

**新功能：**

1. **录音可视化弹窗**：
   - 新增 `VoiceRecordDialog` 录音弹窗组件，录音时弹出可视化窗口
   - 显示录音状态（准备→录音中→识别中→完成/失败）
   - 音量波形动画提示用户可以说话
   - 倒计时进度条显示录音时长
   - 支持手动停止录音和取消
   - 识别成功/失败后自动关闭
   - 支持对话模式持续监听状态显示
   - 支持两种触发路径：工具栏录音按钮点击 和 AI Agent 调用 voice_input 工具

### v1.0.22 更新日志 2026年2月16日

**Bug修复：**

1. **修复 CronJobCard._pause_btn 属性错误**：
   - 修复打开定时任务对话框时的 `AttributeError: 'CronJobCard' object has no attribute '_pause_btn'`
   - 原因：`_update_status_display` 在 `_pause_btn` 按钮创建之前被调用

2. **修复 browser_use ChatOpenAI provider 属性错误**：
   - 修复 `'ChatOpenAI' object has no attribute 'provider'` 错误
   - browser-use 内部检查 `llm.provider` 属性，但 LangChain 的 ChatOpenAI 没有此属性
   - 解决方案：优先使用 browser-use 内置的 ChatBrowserUse，或手动添加 provider 属性

3. **修复 MCP 工具重复注册警告**：
   - 修复 `工具 'mcp_xxx' 已注册，将被覆盖` 重复警告
   - 在注册前检查工具是否已存在，实现幂等性

4. **改进全局快捷键异常处理**：
   - 增加快捷键解析错误的详细日志
   - 捕获并记录 pynput 解析异常

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
