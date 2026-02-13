"""帮助对话框。

Phase 4.10 实现：
- 内嵌帮助页
- 快速入门指南
- FAQ
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 帮助内容
HELP_CONTENTS = {
    "quick_start": {
        "title": "快速入门",
        "content": """
<h2>快速入门</h2>

<h3>1. 配置 API Key</h3>
<p>首次使用需要配置 AI 模型的 API Key：</p>
<ul>
  <li>打开 设置 → API 密钥</li>
  <li>输入你的 API Key（如 OpenAI API Key）</li>
  <li>点击保存</li>
</ul>

<h3>2. 开始对话</h3>
<p>在聊天框中输入问题，按 Enter 发送。AI 会自动调用合适的工具来帮助你。</p>

<h3>3. 可用工具</h3>
<p>WinClaw 内置了多种工具：</p>
<ul>
  <li>💻 命令行 - 执行系统命令</li>
  <li>📄 文件操作 - 读写文件</li>
  <li>📸 屏幕截图 - 截取屏幕内容</li>
  <li>🌐 浏览器 - 自动化网页操作</li>
  <li>🔍 搜索 - 本地和网页搜索</li>
</ul>

<h3>4. 快捷键</h3>
<ul>
  <li><b>Win+Shift+Space</b> - 显示/隐藏窗口</li>
  <li><b>Ctrl+N</b> - 新建对话</li>
  <li><b>Ctrl+S</b> - 保存对话</li>
</ul>
""",
    },
    "features": {
        "title": "功能介绍",
        "content": """
<h2>功能介绍</h2>

<h3>AI 对话</h3>
<p>WinClaw 支持多种 AI 模型：</p>
<ul>
  <li>OpenAI GPT-4 / GPT-3.5</li>
  <li>DeepSeek</li>
  <li>Claude (通过 OpenAI 兼容接口)</li>
  <li>Ollama 本地模型</li>
</ul>

<h3>工具调用</h3>
<p>AI 可以自动调用工具完成任务：</p>
<ul>
  <li>执行命令行操作</li>
  <li>读写文件</li>
  <li>截图和图像识别</li>
  <li>浏览器自动化</li>
  <li>语音输入/输出</li>
</ul>

<h3>MCP 扩展</h3>
<p>通过 MCP 协议连接更多工具：</p>
<ul>
  <li>filesystem - 文件系统访问</li>
  <li>fetch - 网页抓取</li>
  <li>github - GitHub 操作</li>
</ul>
""",
    },
    "tools": {
        "title": "工具列表",
        "content": """
<h2>工具列表</h2>

<table border="1" cellpadding="8">
  <tr><th>工具</th><th>描述</th><th>风险等级</th></tr>
  <tr><td>💻 shell</td><td>执行系统命令</td><td>🔴 高</td></tr>
  <tr><td>📄 file</td><td>文件读写操作</td><td>🟡 中</td></tr>
  <tr><td>📸 screen</td><td>屏幕截图</td><td>🟢 低</td></tr>
  <tr><td>🌐 browser</td><td>浏览器自动化</td><td>🟡 中</td></tr>
  <tr><td>🪟 app_control</td><td>应用控制</td><td>🟡 中</td></tr>
  <tr><td>📋 clipboard</td><td>剪贴板操作</td><td>🟢 低</td></tr>
  <tr><td>🔔 notify</td><td>系统通知</td><td>🟢 低</td></tr>
  <tr><td>🔍 search</td><td>搜索功能</td><td>🟢 低</td></tr>
  <tr><td>⏰ cron</td><td>定时任务</td><td>🟡 中</td></tr>
  <tr><td>🎤 voice_input</td><td>语音输入</td><td>🟢 低</td></tr>
  <tr><td>🔊 voice_output</td><td>语音输出</td><td>🟢 低</td></tr>
  <tr><td>📝 ocr</td><td>文字识别</td><td>🟢 低</td></tr>
</table>
""",
    },
    "faq": {
        "title": "常见问题",
        "content": """
<h2>常见问题</h2>

<h3>Q: API Key 如何获取？</h3>
<p>各平台的 API Key 获取方式：</p>
<ul>
  <li><b>OpenAI</b>: https://platform.openai.com/api-keys</li>
  <li><b>DeepSeek</b>: https://platform.deepseek.com/</li>
  <li><b>Ollama</b>: 本地运行，无需 API Key</li>
</ul>

<h3>Q: 为什么 AI 没有响应？</h3>
<p>可能的原因：</p>
<ul>
  <li>API Key 未配置或无效</li>
  <li>网络连接问题</li>
  <li>API 配额已用完</li>
  <li>模型服务暂时不可用</li>
</ul>

<h3>Q: 如何使用本地模型？</h3>
<p>安装 Ollama 后，WinClaw 会自动检测并显示可用模型。</p>
<ol>
  <li>安装 Ollama: https://ollama.ai</li>
  <li>运行 <code>ollama pull llama3.2</code> 下载模型</li>
  <li>重启 WinClaw，在模型列表中选择 Ollama 模型</li>
</ol>

<h3>Q: 如何添加 MCP 工具？</h3>
<p>编辑 <code>config/mcp_servers.json</code> 文件，添加新的 Server 配置。</p>

<h3>Q: 工具调用失败怎么办？</h3>
<p>检查：</p>
<ul>
  <li>相关依赖是否安装（如 Playwright、Whisper）</li>
  <li>权限是否足够</li>
  <li>查看日志了解详细错误</li>
</ul>
""",
    },
}


class HelpDialog(QDialog):
    """帮助对话框。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("帮助文档")
        self.setMinimumSize(700, 500)
        self.resize(800, 600)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """构建 UI。"""
        layout = QVBoxLayout(self)

        # 分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧导航
        nav_tree = QTreeWidget()
        nav_tree.setHeaderLabel("目录")
        nav_tree.setMaximumWidth(200)

        for key, item in HELP_CONTENTS.items():
            tree_item = QTreeWidgetItem([item["title"]])
            tree_item.setData(0, Qt.ItemDataRole.UserRole, key)
            nav_tree.addTopLevelItem(tree_item)

        nav_tree.currentItemChanged.connect(self._on_nav_changed)
        splitter.addWidget(nav_tree)

        # 右侧内容
        self._content_browser = QTextBrowser()
        self._content_browser.setOpenExternalLinks(True)
        self._content_browser.setHtml(HELP_CONTENTS["quick_start"]["content"])
        splitter.addWidget(self._content_browser)

        splitter.setSizes([150, 550])
        layout.addWidget(splitter)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        # 默认选中第一项
        nav_tree.setCurrentItem(nav_tree.topLevelItem(0))

    def _on_nav_changed(
        self, current: QTreeWidgetItem, previous: QTreeWidgetItem
    ) -> None:
        """导航项切换。"""
        if current is None:
            return

        key = current.data(0, Qt.ItemDataRole.UserRole)
        if key in HELP_CONTENTS:
            self._content_browser.setHtml(HELP_CONTENTS[key]["content"])
