"""聊天界面组件。

支持：
- 消息气泡（用户/AI 区分）
- Markdown 渲染（代码块高亮）
- 智能内容格式化（思考块、工具卡片、引用块等）
- 语法高亮（Python/JS/JSON/HTML/CSS/Bash）
- 自动滚动
- 流式输出显示
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QToolButton,
)
from PySide6.QtCore import Signal

if TYPE_CHECKING:
    from PySide6.QtGui import QTextDocument

# ---------- 模块级别主题色彩（默认亮色） ----------
_theme_colors: dict[str, str] = {
    "chat_bg": "#f8f9fa",
    "chat_bg_gradient": "linear-gradient(180deg, #f8f9fa 0%, #ffffff 100%)",
    "user_bubble_bg": "#0078d4",
    "user_bubble_bg_gradient": "linear-gradient(135deg, #0078d4 0%, #005a9e 100%)",
    "user_bubble_text": "white",
    "ai_bubble_bg": "white",
    "ai_bubble_text": "#333",
    "ai_bubble_border": "#e0e0e0",
    "ai_bubble_shadow": "0 2px 8px rgba(0,0,0,0.08)",
    "code_bg": "#f4f4f4",
    "code_border": "#e1e4e8",
    "code_header_bg": "#f6f8fa",
    "syntax_keyword": "#cf222e",
    "syntax_string": "#0a3069",
    "syntax_comment": "#6e7781",
    "syntax_function": "#8250df",
    "syntax_number": "#0550ae",
    "syntax_builtin": "#953800",
    "think_bg": "#f0f4ff",
    "think_border": "#6366f1",
    "think_text": "#6366f1",
    "tool_card_bg": "linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)",
    "tool_card_border": "#cbd5e1",
    "tool_name_color": "#0078d4",
    "blockquote_border": "#0078d4",
    "blockquote_text": "#555",
    "link_color": "#0078d4",
    "scrollbar_bg": "#f0f0f0",
    "scrollbar_handle": "#c0c0c0",
    "scrollbar_handle_hover": "#a0a0a0",
}


def set_chat_theme(colors: dict[str, str]) -> None:
    """更新聊天组件的主题颜色。"""
    _theme_colors.update(colors)
    # 补充滚动条色彩（theme.py 未提供时自动推断）
    if "scrollbar_bg" not in colors:
        chat_bg = _theme_colors.get("chat_bg", "#fff")
        # 暗色主题背景通常是深蓝/深灰/深棕（以#0或#1开头）
        is_dark = chat_bg.startswith("#0") or chat_bg.startswith("#1") or chat_bg.startswith("#2")
        _theme_colors["scrollbar_bg"] = "#2d2d2d" if is_dark else "#f0f0f0"
        _theme_colors["scrollbar_handle"] = "#555" if is_dark else "#c0c0c0"
        _theme_colors["scrollbar_handle_hover"] = "#777" if is_dark else "#a0a0a0"


# ---------- 语法高亮器 ----------
class SyntaxHighlighter:
    """简单语法高亮器，支持多种语言。"""

    # 语言关键字定义
    KEYWORDS = {
        "python": {
            "keywords": ["def", "class", "if", "else", "elif", "for", "while", "try", "except",
                        "finally", "with", "as", "import", "from", "return", "yield", "raise",
                        "break", "continue", "pass", "lambda", "and", "or", "not", "in", "is",
                        "True", "False", "None", "global", "nonlocal", "assert", "async", "await"],
            "builtins": ["print", "len", "range", "str", "int", "float", "list", "dict", "set",
                        "tuple", "open", "type", "isinstance", "hasattr", "getattr", "setattr"],
        },
        "javascript": {
            "keywords": ["function", "class", "if", "else", "for", "while", "do", "switch", "case",
                        "break", "continue", "return", "try", "catch", "finally", "throw", "new",
                        "this", "super", "extends", "import", "export", "const", "let", "var",
                        "true", "false", "null", "undefined", "async", "await", "yield"],
            "builtins": ["console", "document", "window", "Array", "Object", "String", "Number",
                        "Boolean", "Promise", "JSON", "Math", "Date", "Map", "Set"],
        },
        "json": {"keywords": [], "builtins": []},
        "html": {"keywords": [], "builtins": []},
        "css": {
            "keywords": ["@import", "@media", "@keyframes", "@font-face", "@supports"],
            "builtins": [],
        },
        "bash": {
            "keywords": ["if", "then", "else", "elif", "fi", "for", "while", "do", "done",
                        "case", "esac", "function", "return", "exit", "export", "source",
                        "echo", "read", "true", "false"],
            "builtins": ["cd", "ls", "cp", "mv", "rm", "mkdir", "touch", "cat", "grep", "sed",
                        "awk", "find", "chmod", "chown", "sudo", "apt", "yum", "pip", "npm"],
        },
    }

    # 默认使用 python 的关键字
    KEYWORDS["py"] = KEYWORDS["python"]
    KEYWORDS["js"] = KEYWORDS["javascript"]
    KEYWORDS["sh"] = KEYWORDS["bash"]
    KEYWORDS["shell"] = KEYWORDS["bash"]

    @classmethod
    def highlight(cls, code: str, language: str) -> str:
        """高亮代码，返回带 span 标签的 HTML。"""
        c = _theme_colors
        lang = language.lower() if language else "text"

        # 转义 HTML
        code = code.replace("&", "&amp;")
        code = code.replace("<", "&lt;")
        code = code.replace(">", "&gt;")

        if lang not in cls.KEYWORDS:
            # 未知语言，只处理字符串和注释
            return cls._highlight_strings_and_comments(code, c)

        lang_config = cls.KEYWORDS[lang]

        # 按顺序处理：注释 -> 字符串 -> 数字 -> 关键字 -> 内置函数
        result = code

        # 处理注释
        if lang in ("python", "py"):
            result = re.sub(
                r"(#.*)$",
                f'<span style="color:{c["syntax_comment"]}">\\1</span>',
                result,
                flags=re.MULTILINE,
            )
        elif lang in ("javascript", "js", "bash", "sh", "shell"):
            result = re.sub(
                r"(//.*)$",
                f'<span style="color:{c["syntax_comment"]}">\\1</span>',
                result,
                flags=re.MULTILINE,
            )
            result = re.sub(
                r"(#.*)$",
                f'<span style="color:{c["syntax_comment"]}">\\1</span>',
                result,
                flags=re.MULTILINE,
            )

        # 处理字符串（单引号和双引号）
        result = re.sub(
            r'("[^"]*")',
            f'<span style="color:{c["syntax_string"]}">\\1</span>',
            result,
        )
        result = re.sub(
            r"('[^']*')",
            f'<span style="color:{c["syntax_string"]}">\\1</span>',
            result,
        )

        # 处理数字
        result = re.sub(
            r"\b(\d+\.?\d*)\b",
            f'<span style="color:{c["syntax_number"]}">\\1</span>',
            result,
        )

        # 处理关键字
        for kw in lang_config.get("keywords", []):
            result = re.sub(
                rf"\b({kw})\b",
                f'<span style="color:{c["syntax_keyword"]};font-weight:600">\\1</span>',
                result,
            )

        # 处理内置函数
        for builtin in lang_config.get("builtins", []):
            result = re.sub(
                rf"\b({builtin})\b",
                f'<span style="color:{c["syntax_builtin"]}">\\1</span>',
                result,
            )

        # 处理函数调用
        result = re.sub(
            r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
            f'<span style="color:{c["syntax_function"]}">\\1</span>(',
            result,
        )

        return result

    @classmethod
    def _highlight_strings_and_comments(cls, code: str, c: dict) -> str:
        """仅高亮字符串和注释。"""
        result = code
        result = re.sub(
            r'("[^"]*")',
            f'<span style="color:{c["syntax_string"]}">\\1</span>',
            result,
        )
        result = re.sub(
            r"('[^']*')",
            f'<span style="color:{c["syntax_string"]}">\\1</span>',
            result,
        )
        result = re.sub(
            r"(#.*)$",
            f'<span style="color:{c["syntax_comment"]}">\\1</span>',
            result,
            flags=re.MULTILINE,
        )
        result = re.sub(
            r"(//.*)$",
            f'<span style="color:{c["syntax_comment"]}">\\1</span>',
            result,
            flags=re.MULTILINE,
        )
        return result


# ---------- 内容格式化器 ----------
class ContentFormatter:
    """智能内容格式化器，识别不同类型的内容并应用样式。"""

    @classmethod
    def format_think_block(cls, content: str) -> str:
        """格式化思考块。"""
        c = _theme_colors
        return (
            f'<div style="background:{c["think_bg"]};border-left:3px solid {c["think_border"]};'
            f'padding:8px 12px;margin:8px 0;border-radius:4px;font-size:13px;'
            f'color:{c["think_text"]};opacity:0.9;">'
            f'<div style="font-weight:600;margin-bottom:4px;">💭 思考过程</div>'
            f'<div style="white-space:pre-wrap;">{content}</div></div>'
        )

    @classmethod
    def format_tool_card(cls, tool_name: str, params: str = "") -> str:
        """格式化工具调用卡片。"""
        c = _theme_colors
        params_html = ""
        if params:
            # 转义并格式化参数
            params_escaped = params.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            params_html = f'<div style="font-size:12px;color:#666;margin-top:6px;font-family:Consolas,monospace;">{params_escaped}</div>'
        return (
            f'<div style="background:{c["tool_card_bg"]};border:1px solid {c["tool_card_border"]};'
            f'border-radius:8px;padding:12px;margin:8px 0;">'
            f'<div style="color:{c["tool_name_color"]};font-weight:600;font-family:Consolas,monospace;">🔧 {tool_name}</div>'
            f'{params_html}</div>'
        )

    @classmethod
    def format_blockquote(cls, content: str) -> str:
        """格式化引用块。"""
        c = _theme_colors
        return (
            f'<blockquote style="border-left:4px solid {c["blockquote_border"]};'
            f'padding-left:12px;margin:8px 0;color:{c["blockquote_text"]};font-style:italic;">'
            f'{content}</blockquote>'
        )

    @classmethod
    def format_code_block(cls, code: str, language: str) -> str:
        """格式化代码块，带语法高亮和语言标签。"""
        c = _theme_colors
        highlighted = SyntaxHighlighter.highlight(code, language)
        lang_label = language if language else "code"
        return (
            f'<div style="margin:8px 0;border-radius:6px;overflow:hidden;border:1px solid {c["code_border"]};">'
            f'<div style="background:{c["code_header_bg"]};padding:4px 10px;font-size:11px;'
            f'color:#666;border-bottom:1px solid {c["code_border"]};display:flex;justify-content:space-between;">'
            f'<span>{lang_label}</span><span style="cursor:pointer;">复制</span></div>'
            f'<pre style="background:{c["code_bg"]};padding:12px;margin:0;overflow-x:auto;"><code '
            f'style="font-family:Consolas,Courier New,monospace;font-size:13px;color:{c["ai_bubble_text"]};">'
            f'{highlighted}</code></pre></div>'
        )

    @classmethod
    def detect_and_format_tool_call(cls, text: str) -> str:
        """检测并格式化工具调用。"""
        # 匹配模式：Tool: tool_name 或 调用工具: tool_name 等
        patterns = [
            r"(?:Tool|工具|调用)[:：]\s*(\w+)\s*\n?(.*)",
            r"🔧\s*(\w+)\s*[:：]?\s*\n?(.*)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                tool_name = match.group(1)
                params = match.group(2).strip() if len(match.groups()) > 1 else ""
                return cls.format_tool_card(tool_name, params)
        return text


class ReasoningBlock(QFrame):
    """可折叠的思考过程块。
    
    显示AI的思考过程，可以展开/折叠，默认折叠状态。
    """
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._reasoning_text = ""
        self._setup_ui()
        self._apply_styles()
        
    def _setup_ui(self) -> None:
        """设置UI。"""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 6, 8, 6)
        self._layout.setSpacing(4)
        
        # 头部区域（标题 + 展开/折叠按钮）
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        # 展开/折叠按钮
        self._toggle_btn = QToolButton()
        self._toggle_btn.setText("▶")
        self._toggle_btn.setFixedSize(20, 20)
        self._toggle_btn.setStyleSheet("""
            QToolButton {
                border: none;
                background: transparent;
                font-size: 12px;
                color: #6366f1;
            }
            QToolButton:hover {
                background: rgba(99, 102, 241, 0.1);
                border-radius: 4px;
            }
        """)
        self._toggle_btn.clicked.connect(self._toggle_expanded)
        header_layout.addWidget(self._toggle_btn)
        
        # 标题标签
        self._title_label = QLabel("💭 思考过程")
        self._title_label.setStyleSheet("font-weight: 600; font-size: 13px; color: #6366f1;")
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()
        
        self._layout.addLayout(header_layout)
        
        # 内容区域（ QTextBrowser ）
        self._content_browser = QTextBrowser()
        self._content_browser.setFrameStyle(QFrame.Shape.NoFrame)
        self._content_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._content_browser.setMaximumHeight(200)  # 默认最大高度
        self._content_browser.hide()  # 默认隐藏
        self._content_browser.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                font-size: 12px;
                color: #4b5563;
                line-height: 1.4;
            }
        """)
        self._layout.addWidget(self._content_browser)
        
        self._is_expanded = False
        
    def _apply_styles(self) -> None:
        """应用样式。"""
        c = _theme_colors
        self.setStyleSheet(f"""
            ReasoningBlock {{
                background: {c.get("think_bg", "#f0f4ff")};
                border-left: 3px solid {c.get("think_border", "#6366f1")};
                border-radius: 6px;
            }}
        """)
        
    def _toggle_expanded(self) -> None:
        """切换展开/折叠状态。"""
        self._is_expanded = not self._is_expanded
        if self._is_expanded:
            self._toggle_btn.setText("▼")
            self._content_browser.show()
            self._update_content()
        else:
            self._toggle_btn.setText("▶")
            self._content_browser.hide()
            
    def _update_content(self) -> None:
        """更新内容显示。"""
        if self._reasoning_text:
            # 转义HTML并保留换行
            text = self._reasoning_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            text = text.replace("\n", "<br>")
            self._content_browser.setHtml(f"""
                <html><head><style>
                    body {{ 
                        font-family: "Segoe UI", Arial, sans-serif; 
                        font-size: 12px;
                        line-height: 1.4; 
                        margin: 0; 
                        padding: 4px 0;
                    }}
                </style></head>
                <body>{text}</body></html>
            """)
            
    def append_reasoning(self, text: str) -> None:
        """追加思考内容。"""
        self._reasoning_text += text
        if self._is_expanded:
            self._update_content()

    def append_reasoning_incremental(self, text: str) -> None:
        """增量追加思考内容（流式输出优化版）。

        使用延迟渲染策略，减少UI线程阻塞。
        """
        self._reasoning_text += text

        # 如果正在展开状态，使用延迟渲染
        if self._is_expanded:
            if not hasattr(self, '_pending_render') or not self._pending_render:
                self._pending_render = True
                QTimer.singleShot(50, self._do_incremental_render)

    def _do_incremental_render(self) -> None:
        """执行延迟的思考内容渲染。"""
        self._pending_render = False
        if self._is_expanded:
            self._update_content()
            
    def set_reasoning(self, text: str) -> None:
        """设置思考内容（替换）。"""
        self._reasoning_text = text
        if self._is_expanded:
            self._update_content()
            
    def finish_reasoning(self) -> None:
        """完成思考过程。"""
        # 可以在这里添加完成状态的视觉提示
        self._title_label.setText("💭 思考完成")
        
    def apply_theme(self, colors: dict[str, str]) -> None:
        """应用主题颜色。"""
        self.setStyleSheet(f"""
            ReasoningBlock {{
                background: {colors.get("think_bg", "#f0f4ff")};
                border-left: 3px solid {colors.get("think_border", "#6366f1")};
                border-radius: 6px;
            }}
        """)
        self._title_label.setStyleSheet(
            f"font-weight: 600; font-size: 13px; color: {colors.get('think_text', '#6366f1')};"
        )


class ChatWidget(QWidget):
    """聊天组件。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._current_ai_bubble: MessageBubble | None = None
        self._current_reasoning_block: ReasoningBlock | None = None

    def _setup_ui(self) -> None:
        """设置 UI。"""
        # 顶层布局：只有滚动区域（按钮已移至main_window工具栏）
        top_layout = QVBoxLayout(self)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 消息容器
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(4)  # 减小消息间距（68%的6px≈4px）
        self._layout.addStretch()

        scroll.setWidget(self._container)
        top_layout.addWidget(scroll)

        self._scroll_area = scroll
        self._apply_theme_styles()

    def copy_all_conversation(self) -> str:
        """获取所有对话内容。"""
        conversation_text = ""
        for i in range(self._layout.count() - 1):  # 最后一个是stretch
            item = self._layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                # 检查是否是MessageBubble
                if isinstance(widget, MessageBubble):
                    role = "用户" if widget.is_user else "AI"
                    text = widget.get_text()
                    conversation_text += f"{role}: {text}\n\n"
        return conversation_text

    def _on_copy_all_conversation(self) -> None:
        """复制所有对话内容到剪贴板。"""
        from PySide6.QtWidgets import QApplication
        # 收集所有消息
        conversation_text = ""
        for i in range(self._layout.count() - 1):  # 最后一个是stretch
            item = self._layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                # 检查是否是MessageBubble
                if isinstance(widget, MessageBubble):
                    role = "用户" if widget.is_user else "AI"
                    text = widget.get_text()
                    conversation_text += f"{role}: {text}\n\n"
        
        # 复制到剪贴板
        clipboard = QApplication.clipboard()
        clipboard.setText(conversation_text)
        
        # 显示反馈
        self._copy_all_btn.setText("✓ 已复制")
        QTimer.singleShot(1500, lambda: self._copy_all_btn.setText("📋 复制对话区"))

    def add_user_message(self, text: str) -> None:
        """添加用户消息。"""
        bubble = MessageBubble(text, is_user=True)
        # 在 stretch 之前插入
        self._layout.insertWidget(self._layout.count() - 1, bubble)
        self._scroll_to_bottom()
        self._current_ai_bubble = None
        self._current_reasoning_block = None

    def add_ai_message(self, text: str) -> None:
        """添加 AI 消息（完整消息）。"""
        bubble = MessageBubble(text, is_user=False)
        self._layout.insertWidget(self._layout.count() - 1, bubble)
        self._scroll_to_bottom()
        self._current_ai_bubble = None
        self._current_reasoning_block = None

    def append_ai_message(self, text: str) -> None:
        """追加 AI 消息（流式输出）。

        优化：使用增量追加模式，避免频繁渲染 Markdown。
        """
        if self._current_ai_bubble is None:
            self._current_ai_bubble = MessageBubble("", is_user=False)
            self._layout.insertWidget(
                self._layout.count() - 1, self._current_ai_bubble
            )

        self._current_ai_bubble.append_text_incremental(text)  # 使用增量追加
        self._scroll_to_bottom()

    def start_reasoning(self) -> None:
        """开始显示思考过程。"""
        if self._current_reasoning_block is None:
            self._current_reasoning_block = ReasoningBlock()
            self._layout.insertWidget(
                self._layout.count() - 1, self._current_reasoning_block
            )
        self._scroll_to_bottom()

    def append_reasoning(self, text: str) -> None:
        """追加思考内容（流式输出优化版）。"""
        if self._current_reasoning_block is None:
            self.start_reasoning()
        self._current_reasoning_block.append_reasoning_incremental(text)
        self._scroll_to_bottom()

    def finish_reasoning(self) -> None:
        """完成思考过程。"""
        if self._current_reasoning_block:
            self._current_reasoning_block.finish_reasoning()
        self._current_reasoning_block = None

    def clear(self) -> None:
        """清空所有消息。"""
        # 移除所有消息气泡（保留 stretch）
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._current_ai_bubble = None
        self._current_reasoning_block = None

    def apply_theme(self, colors: dict[str, str]) -> None:
        """应用主题到聊天区域，包括所有已有气泡。"""
        set_chat_theme(colors)
        self._apply_theme_styles()
        # 重建所有已有气泡的样式
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, MessageBubble):
                w._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        """根据当前 _theme_colors 设置容器和滚动区域样式。"""
        c = _theme_colors
        # 根据背景色亮度判断主题类型
        chat_bg = c.get("chat_bg", "#f8f9fa")
        # 暗色主题背景通常是深蓝/深灰/深棕（以#0或#1开头）
        is_dark = (
            chat_bg.startswith("#0") or  # 深蓝(#0a0f1a)、深棕(#0a0806)
            chat_bg.startswith("#1") or  # 暗色(#1a1a2e)
            chat_bg.startswith("#2")     # 深灰(#252525)
        )
        
        # 使用主题配置的背景色，而非硬编码
        bg_color = chat_bg
        
        scrollbar_bg = c.get("scrollbar_bg", "#2d2d2d" if is_dark else "#f0f0f0")
        scrollbar_handle = c.get("scrollbar_handle", "#555" if is_dark else "#c0c0c0")
        scrollbar_handle_hover = c.get("scrollbar_handle_hover", "#777" if is_dark else "#a0a0a0")
        
        self._scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {bg_color};
            }}
            QScrollBar:vertical {{
                background: {scrollbar_bg};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {scrollbar_handle};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {scrollbar_handle_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        self._container.setStyleSheet(f"background-color: {bg_color};")

    def _scroll_to_bottom(self) -> None:
        """滚动到底部（带节流优化）。

        使用延迟执行策略，避免频繁滚动导致的UI抖动。
        """
        # 使用属性检查是否已有待处理的滚动任务
        if not hasattr(self, '_pending_scroll') or not self._pending_scroll:
            self._pending_scroll = True
            QTimer.singleShot(30, self._do_scroll_to_bottom)

    def _do_scroll_to_bottom(self) -> None:
        """执行滚动到底部。"""
        self._pending_scroll = False
        sb = self._scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())


class MessageBubble(QFrame):
    """消息气泡。"""

    # 类级别的TTS播放器，所有消息共享
    _tts_player = None
    _current_playing_bubble = None  # 当前正在播放的气泡

    def __init__(self, text: str, is_user: bool = False) -> None:
        super().__init__()
        self._is_user = is_user
        self._full_text = text
        self._is_playing = False  # 当前气泡是否在播放
        self._is_collapsed = False  # AI消息是否处于收起状态
        self._setup_ui()
        self._render_text(text)
        
        # 连接销毁信号，气泡销毁时停止播放
        self.destroyed.connect(self._on_destroyed)

    def _on_destroyed(self) -> None:
        """气泡销毁时停止播放。"""
        if MessageBubble._current_playing_bubble == self:
            player = self._get_tts_player()
            if player:
                player.stop()
            MessageBubble._current_playing_bubble = None

    @property
    def is_user(self) -> bool:
        """返回是否是用户消息。"""
        return self._is_user

    def get_text(self) -> str:
        """返回消息文本。"""
        return self._full_text

    @classmethod
    def _get_tts_player(cls):
        """获取或创建TTS播放器。"""
        if cls._tts_player is None:
            try:
                from ..conversation.tts_player import TTSPlayer, TTSEngine
                cls._tts_player = TTSPlayer(engine=TTSEngine.PYTTSX3)
            except Exception:
                return None
        return cls._tts_player

    def _on_play_toggle(self) -> None:
        """切换播放/暂停状态。"""
        player = self._get_tts_player()
        if player is None:
            return

        if self._is_playing:
            # 当前正在播放，停止
            player.stop()
            self._is_playing = False
            self._update_play_button()
            if MessageBubble._current_playing_bubble == self:
                MessageBubble._current_playing_bubble = None
        else:
            # 开始播放，先停止其他气泡的播放
            if MessageBubble._current_playing_bubble and MessageBubble._current_playing_bubble != self:
                MessageBubble._current_playing_bubble._is_playing = False
                MessageBubble._current_playing_bubble._update_play_button()
                player.stop()
            
            # 清理文本中的HTML标签和特殊标记用于TTS
            text_for_tts = self._full_text
            # 移除<think>标签内容
            import re
            text_for_tts = re.sub(r'<think>.*?</think>', '', text_for_tts, flags=re.DOTALL)
            text_for_tts = re.sub(r'&lt;think&gt;.*?&lt;/think&gt;', '', text_for_tts, flags=re.DOTALL)
            # 移除HTML标签
            text_for_tts = re.sub(r'<[^>]+>', '', text_for_tts)
            # 还原HTML实体
            text_for_tts = text_for_tts.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
            
            if text_for_tts.strip():
                player.speak(text_for_tts)
                self._is_playing = True
                MessageBubble._current_playing_bubble = self
                self._update_play_button()
                
                # 监听播放完成信号（只连接一次，使用weak flag避免重复连接问题）
                if not hasattr(player, '_chat_bubble_connected'):
                    player.playback_finished.connect(self._on_playback_finished)
                    player._chat_bubble_connected = True

    def _on_playback_finished(self) -> None:
        """播放完成时的回调。"""
        # 只有当前气泡仍在播放时才更新状态
        if MessageBubble._current_playing_bubble == self:
            self._is_playing = False
            self._update_play_button()
            MessageBubble._current_playing_bubble = None

    def _update_play_button(self) -> None:
        """更新播放按钮图标。"""
        try:
            if self._is_playing:
                self._play_btn.setText("⏹")
                self._play_btn.setToolTip("停止播放")
            else:
                self._play_btn.setText("▶")
                self._play_btn.setToolTip("播放消息")
        except RuntimeError:
            pass

    def _on_toggle_collapse(self) -> None:
        """切换收起/展开状态。"""
        self._is_collapsed = not self._is_collapsed
        self._adjust_height()
        
        # 更新按钮图标和提示
        if self._is_collapsed:
            self._collapse_btn.setText("▼")
            self._collapse_btn.setToolTip("展开消息")
        else:
            self._collapse_btn.setText("▲")
            self._collapse_btn.setToolTip("收起消息")

    def _setup_ui(self) -> None:
        """设置 UI。"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)

        if self._is_user:
            main_layout.setContentsMargins(6, 2, 6, 2)
        else:
            main_layout.setContentsMargins(6, 3, 6, 3)

        # 内容行：文本浏览器 + 按钮（上下排列）
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # 文本浏览器
        self._text_browser = QTextBrowser()
        self._text_browser.setOpenExternalLinks(True)
        self._text_browser.setFrameStyle(QFrame.Shape.NoFrame)
        self._text_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._text_browser.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self._text_browser.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        # 用户和 AI 都使用全部可用宽度
        self._text_browser.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        content_layout.addWidget(self._text_browser)

        # 按钮容器（垂直排列，固定在右上角）
        btn_container = QVBoxLayout()
        btn_container.setSpacing(2)
        btn_container.setContentsMargins(0, 0, 0, 0)

        # 复制按钮
        self._copy_btn = QPushButton("📋")
        self._copy_btn.setFixedSize(24, 24)
        self._copy_btn.setToolTip("复制消息内容")
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.clicked.connect(self._on_copy)
        self._copy_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn_container.addWidget(self._copy_btn)

        # 播放按钮
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(24, 24)
        self._play_btn.setToolTip("播放消息")
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.clicked.connect(self._on_play_toggle)
        self._play_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn_container.addWidget(self._play_btn)

        # AI消息添加收起/展开按钮
        if not self._is_user:
            self._collapse_btn = QPushButton("▲")
            self._collapse_btn.setFixedSize(24, 24)
            self._collapse_btn.setToolTip("收起消息")
            self._collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._collapse_btn.clicked.connect(self._on_toggle_collapse)
            self._collapse_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn_container.addWidget(self._collapse_btn)

        # 添加弹性空间，将按钮固定在顶部
        btn_container.addStretch()

        content_layout.addLayout(btn_container)

        main_layout.addLayout(content_layout)

        # 应用当前主题颜色
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        """根据当前 _theme_colors 设置气泡和文本样式。"""
        c = _theme_colors
        if self._is_user:
            # 用户消息不使用气泡容器，简化为透明背景 + 靠右对齐
            text_color = c["user_bubble_text"]
            copy_btn_color = "rgba(255,255,255,0.5)"
            copy_btn_hover = "rgba(255,255,255,0.8)"
            self.setStyleSheet("""
                MessageBubble {
                    background: transparent;
                    border: none;
                }
            """)
        else:
            # AI 气泡使用纯色
            bg_style = c["ai_bubble_bg"]
            text_color = c["ai_bubble_text"]
            border_radius = "14px 14px 14px 4px"
            border = f"1px solid {c['ai_bubble_border']}"
            copy_btn_color = "rgba(0,0,0,0.15)"
            copy_btn_hover = "rgba(0,0,0,0.3)"
            self.setStyleSheet(f"""
                MessageBubble {{
                    background: {bg_style};
                    border-radius: {border_radius};
                    border: {border};
                }}
            """)
        self._text_browser.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                color: %s;
                font-size: 12px;
            }
        """ % text_color)
        self._copy_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 16px;
                color: %s;
                padding: 0;
            }
            QPushButton:hover {
                background: %s;
            }
        """ % (copy_btn_color, copy_btn_hover))
        self._play_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 18px;
                color: %s;
                padding: 0;
            }
            QPushButton:hover {
                background: %s;
            }
        """ % (copy_btn_color, copy_btn_hover))
        
        # 设置收起/展开按钮样式（仅AI消息有此按钮）
        if not self._is_user:
            self._collapse_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    font-size: 16px;
                    color: %s;
                    padding: 0;
                }
                QPushButton:hover {
                    background: %s;
                }
            """ % (copy_btn_color, copy_btn_hover))

        # 如果已有内容，重新渲染以更新 HTML 内嵌颜色
        if self._full_text:
            self._render_text(self._full_text)

    def _render_text(self, text: str) -> None:
        """渲染文本（支持 Markdown）。"""
        if self._is_user:
            # 用户消息：HTML 渲染以支持自动换行
            self._text_browser.setHtml(self._plain_to_html(text))
        else:
            # AI 消息：Markdown 渲染（带智能格式化）
            # 检查是否包含 base64 图片，如果有则混合渲染
            if "data:image/" in text:
                # 包含 base64 图片，提取图片并转换 Markdown
                self._render_mixed_content(text)
            else:
                html = self._markdown_to_html(text)
                self._text_browser.setHtml(html)

        # 自适应高度
        self._adjust_height()

    def append_text(self, text: str) -> None:
        """追加文本（流式输出）。"""
        self._full_text += text
        if self._is_user:
            self._text_browser.setHtml(self._plain_to_html(self._full_text))
        else:
            # 检查是否包含 base64 图片
            if "data:image/" in self._full_text:
                # 提取 base64 图片部分，剩余文本进行 Markdown 转换
                self._render_mixed_content(self._full_text)
            else:
                html = self._markdown_to_html(self._full_text)
                self._text_browser.setHtml(html)
        self._adjust_height()

    def append_text_incremental(self, text: str) -> None:
        """增量追加文本（流式输出优化版）。

        优化策略：
        1. 累加原始文本到 _full_text
        2. 使用 QTimer 延迟渲染 Markdown，避免频繁重绘
        3. 延迟调整高度，减少布局计算

        这样可以显著减少 UI 线程阻塞，提高响应流畅度。
        """
        self._full_text += text

        # 标记需要渲染，避免重复创建定时器
        if not hasattr(self, '_pending_render') or not self._pending_render:
            self._pending_render = True
            # 延迟 50ms 渲染，合并多次快速追加
            QTimer.singleShot(50, self._do_incremental_render)

    def _do_incremental_render(self) -> None:
        """执行延迟的增量渲染。"""
        self._pending_render = False
        if self._is_user:
            self._text_browser.setHtml(self._plain_to_html(self._full_text))
        else:
            if "data:image/" in self._full_text:
                self._render_mixed_content(self._full_text)
            else:
                html = self._markdown_to_html(self._full_text)
                self._text_browser.setHtml(html)

        # 延迟调整高度
        QTimer.singleShot(20, self._adjust_height)

    def _render_mixed_content(self, text: str) -> None:
        """渲染同时包含 Markdown 和 base64 图片的内容。"""
        import re
        # 提取所有 base64 图片标签
        img_pattern = r'(<img src="data:image/[^"]+"[^>]*>)'
        parts = re.split(img_pattern, text)
        
        html_parts = []
        for part in parts:
            if part.startswith('<img src="data:image/'):
                # 直接保留 base64 图片标签
                html_parts.append(part)
            elif part.strip():
                # 对 Markdown 文本进行转换
                html = self._markdown_to_html(part)
                html_parts.append(html)
        
        combined_html = "".join(html_parts)
        self._text_browser.setHtml(combined_html)

    def _on_copy(self) -> None:
        """复制消息内容到剪贴板。"""
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._full_text)
            # 临时改变按钮文字表示已复制
            self._copy_btn.setText("✅")
            # 使用延迟回调恢复按钮文字，需要捕获可能的对象已删除异常
            copy_btn = self._copy_btn
            QTimer.singleShot(1500, lambda btn=copy_btn: self._restore_copy_button(btn))

    def _restore_copy_button(self, btn: QPushButton) -> None:
        """恢复复制按钮的文字。"""
        try:
            btn.setText("📋")
        except RuntimeError:
            # 按钮对象已被删除，忽略异常
            pass

    def _adjust_height(self) -> None:
        """调整高度以适应内容。"""
        doc = self._text_browser.document()
        margin = doc.documentMargin()  # 默认4px
        max_w = self._text_browser.maximumWidth()
        if max_w > 0 and max_w < 16777215:
            # 减去文档边距以获得准确的文本宽度
            doc.setTextWidth(max_w - 2 * margin)
        else:
            vw = self._text_browser.viewport().width()
            doc.setTextWidth((vw or 600) - 2 * margin)
        content_height = int(doc.size().height() + 2 * margin) + 4
        
        if self._is_user:
            # 用户消息：使用适当高度，确保不被截断
            self._text_browser.setMinimumHeight(max(content_height, 30))
            self._text_browser.setMaximumHeight(max(content_height, 500))
            # 用户消息不需要滚动条
            self._text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            # AI消息：根据收起状态调整高度
            if self._is_collapsed:
                # 收起状态：显示两行文本（约50px）
                collapsed_height = 50
                self._text_browser.setMinimumHeight(collapsed_height)
                self._text_browser.setMaximumHeight(collapsed_height)
                self._text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            else:
                # 展开状态：显示全部内容，无高度限制
                self._text_browser.setMinimumHeight(max(content_height, 30))
                self._text_browser.setMaximumHeight(16777215)  # 移除最大高度限制
                self._text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    @staticmethod
    def _plain_to_html(text: str) -> str:
        """纯文本转 HTML（支持自动换行和转义）。"""
        c = _theme_colors
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        text = text.replace("\n", "<br>")
        return (
            '<html><head><style>'
            'body { font-family: "Segoe UI", Arial, sans-serif; font-size: 12px;'
            f'  line-height: 1.4; margin: 0; padding: 0; color: {c["user_bubble_text"]};'
            '  word-wrap: break-word; overflow-wrap: break-word; }'
            '</style></head>'
            f'<body>{text}</body></html>'
        )

    def _markdown_to_html(self, text: str) -> str:
        """智能 Markdown 转 HTML（支持思考块、工具卡片、代码高亮等）。"""
        c = _theme_colors
        code_bg = c["code_bg"]
        link_color = c["link_color"]
        text_color = c["ai_bubble_text"]

        # 转义 HTML
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")

        # ---------- 1. 处理思考块 <think&gt;...&lt;/think&gt; ----------
        think_pattern = r"&lt;think&gt;(.*?)&lt;/think&gt;"
        think_matches = list(re.finditer(think_pattern, text, re.DOTALL))
        think_blocks: dict[str, str] = {}
        for i, match in enumerate(think_matches):
            placeholder = f"\x00THINKBLOCK{i}\x00"
            think_content = match.group(1).strip()
            think_blocks[placeholder] = ContentFormatter.format_think_block(think_content)
            text = text.replace(match.group(0), placeholder)

        # ---------- 2. 提取代码块，用占位符替代 ----------
        code_blocks: dict[str, str] = {}
        _code_idx = 0

        def _code_block_repl(match: re.Match) -> str:
            nonlocal _code_idx
            lang = match.group(1) or ""
            code = match.group(2)
            placeholder = f"\x00CODEBLOCK{_code_idx}\x00"
            code_blocks[placeholder] = ContentFormatter.format_code_block(code, lang)
            _code_idx += 1
            return placeholder

        text = re.sub(r"```(\w*)\n(.*?)```", _code_block_repl, text, flags=re.DOTALL)

        # ---------- 3. 行内格式 ----------
        # 行内代码
        text = re.sub(
            r"`([^`]+)`",
            f'<code style="background:{code_bg};padding:2px 5px;border-radius:4px;'
            f'font-family:Consolas,monospace;font-size:13px;color:{text_color};">\\1</code>',
            text,
        )
        # 粗体
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # 斜体
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
        # 链接
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            f'<a href="\\2" style="color:{link_color};text-decoration:none;border-bottom:1px dashed {link_color};">\\1</a>',
            text,
        )

        # ---------- 4. 逐行处理：标题 / 列表 / 引用 / 段落 ----------
        lines = text.split("\n")
        html_parts: list[str] = []
        paragraph_lines: list[str] = []  # 收集普通文本行
        in_ul = False
        in_ol = False

        def _flush_paragraph() -> None:
            """将已收集的普通文本行输出为 <p>。"""
            if paragraph_lines:
                html_parts.append("<p>" + "<br>".join(paragraph_lines) + "</p>")
                paragraph_lines.clear()

        def _close_list() -> None:
            nonlocal in_ul, in_ol
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            if in_ol:
                html_parts.append("</ol>")
                in_ol = False

        for line in lines:
            stripped = line.strip()

            # 空行 → 结束当前段落 / 列表
            if not stripped:
                _close_list()
                _flush_paragraph()
                continue

            # 代码块占位符
            if stripped.startswith("\x00CODEBLOCK"):
                _close_list()
                _flush_paragraph()
                html_parts.append(code_blocks.get(stripped, stripped))
                continue

            # 思考块占位符
            if stripped.startswith("\x00THINKBLOCK"):
                _close_list()
                _flush_paragraph()
                html_parts.append(think_blocks.get(stripped, stripped))
                continue

            # 引用块
            if stripped.startswith("&gt; ") or stripped.startswith("> "):
                _close_list()
                _flush_paragraph()
                quote_content = stripped[6:] if stripped.startswith("&gt; ") else stripped[2:]
                html_parts.append(ContentFormatter.format_blockquote(quote_content))
                continue

            # 标题
            heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
            if heading:
                _close_list()
                _flush_paragraph()
                lvl = len(heading.group(1))
                html_parts.append(f"<h{lvl}>{heading.group(2)}</h{lvl}>")
                continue

            # 无序列表
            if stripped.startswith(("- ", "* ")):
                _flush_paragraph()
                if not in_ul:
                    _close_list()
                    html_parts.append("<ul>")
                    in_ul = True
                html_parts.append(f"<li>{stripped[2:]}</li>")
                continue

            # 有序列表
            ol_match = re.match(r"^\d+\.\s+(.+)$", stripped)
            if ol_match:
                _flush_paragraph()
                if not in_ol:
                    _close_list()
                    html_parts.append("<ol>")
                    in_ol = True
                html_parts.append(f"<li>{ol_match.group(1)}</li>")
                continue

            # 普通文本 → 收集到当前段落
            paragraph_lines.append(stripped)

        # 处理末尾残留
        _close_list()
        _flush_paragraph()

        body = "\n".join(html_parts)

        # 恢复占位符
        for placeholder, html in code_blocks.items():
            body = body.replace(placeholder, html)
        for placeholder, html in think_blocks.items():
            body = body.replace(placeholder, html)

        return (
            '<html><head><style>'
            'body { font-family: "Segoe UI", Arial, sans-serif;'
            f'  line-height: 1.0; color: {text_color}; margin: 0; padding: 0; }}'
            'h1, h2, h3 { margin-top: 4px; margin-bottom: 2px; font-weight: 600; }'
            'h1 { font-size: 1.35em; } h2 { font-size: 1.2em; } h3 { font-size: 1.05em; }'
            'ul, ol { margin: 2px 0; padding-left: 20px; }'
            'li { margin: 1px 0; line-height: 1.0; }'
            'p { margin: 2px 0; line-height: 1.0; }'
            f'a {{ color: {link_color}; text-decoration: none; }}'
            'a:hover { text-decoration: underline; }'
            '</style></head>'
            f'<body>{body}</body></html>'
        )
