"""Clipboard 工具 — 系统剪贴板读写（Sprint 2.3）。

支持动作：
- read: 读取剪贴板文本内容
- write: 写入文本到剪贴板
- read_image: 读取剪贴板中的图片（返回 base64）
- clear: 清空剪贴板
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


class ClipboardTool(BaseTool):
    """系统剪贴板读写工具。

    使用 pyperclip 处理文本，使用 Pillow + Win32 API 处理图片。
    """

    name = "clipboard"
    emoji = "📋"
    title = "剪贴板"
    description = "读取、写入剪贴板文本和图片内容，清空剪贴板"

    def __init__(self, max_text_length: int = 50000):
        self.max_text_length = max_text_length

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="read",
                description="读取剪贴板中的文本内容。",
                parameters={},
                required_params=[],
            ),
            ActionDef(
                name="write",
                description="将文本写入剪贴板。",
                parameters={
                    "text": {
                        "type": "string",
                        "description": "要写入剪贴板的文本",
                    },
                },
                required_params=["text"],
            ),
            ActionDef(
                name="read_image",
                description="读取剪贴板中的图片，返回 base64 编码的 PNG。",
                parameters={},
                required_params=[],
            ),
            ActionDef(
                name="clear",
                description="清空剪贴板内容。",
                parameters={},
                required_params=[],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "read": self._read,
            "write": self._write,
            "read_image": self._read_image,
            "clear": self._clear,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return await handler(params)

    async def _read(self, params: dict[str, Any]) -> ToolResult:
        try:
            import pyperclip
            text = pyperclip.paste()
            if not text:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output="剪贴板为空（无文本内容）",
                    data={"has_text": False},
                )

            if len(text) > self.max_text_length:
                text = text[:self.max_text_length] + f"\n...(已截断，共 {len(text)} 字符)"

            logger.info("读取剪贴板: %d 字符", len(text))
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"剪贴板内容 ({len(text)} 字符):\n{text}",
                data={"has_text": True, "length": len(text)},
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"读取剪贴板失败: {e}")

    async def _write(self, params: dict[str, Any]) -> ToolResult:
        text = params.get("text", "")
        if not text:
            return ToolResult(status=ToolResultStatus.ERROR, error="文本内容不能为空")

        try:
            import pyperclip
            pyperclip.copy(text)
            logger.info("写入剪贴板: %d 字符", len(text))
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已写入剪贴板 ({len(text)} 字符)",
                data={"length": len(text)},
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"写入剪贴板失败: {e}")

    async def _read_image(self, params: dict[str, Any]) -> ToolResult:
        try:
            from PIL import ImageGrab

            img = ImageGrab.grabclipboard()
            if img is None:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output="剪贴板中没有图片",
                    data={"has_image": False},
                )

            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            img_bytes = buffer.getvalue()
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            logger.info("读取剪贴板图片: %dx%d (%.1fKB)", img.width, img.height, len(img_bytes) / 1024)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"剪贴板图片: {img.width}x{img.height} ({len(img_bytes) / 1024:.1f}KB)",
                data={
                    "has_image": True,
                    "base64": img_b64,
                    "width": img.width,
                    "height": img.height,
                    "size_bytes": len(img_bytes),
                },
            )
        except ImportError:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="Pillow 未安装，无法读取剪贴板图片",
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"读取剪贴板图片失败: {e}")

    async def _clear(self, params: dict[str, Any]) -> ToolResult:
        try:
            import ctypes
            ctypes.windll.user32.OpenClipboard(0)
            ctypes.windll.user32.EmptyClipboard()
            ctypes.windll.user32.CloseClipboard()
            logger.info("剪贴板已清空")
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="剪贴板已清空",
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"清空剪贴板失败: {e}")
