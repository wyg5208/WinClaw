"""Notify 工具 — Windows 系统通知（Sprint 2.3）。

支持动作：
- send: 发送一条 Windows 系统通知（Toast Notification）
- send_with_action: 发送带按钮的通知（可选）
"""

from __future__ import annotations

import logging
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


class NotifyTool(BaseTool):
    """Windows 系统通知工具。

    使用 winotify 发送 Windows 10/11 原生 Toast 通知。
    """

    name = "notify"
    emoji = "🔔"
    title = "系统通知"
    description = "发送 Windows 系统通知（Toast Notification），支持标题、正文和图标"

    def __init__(self, app_id: str = "WinClaw"):
        self.app_id = app_id

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="send",
                description="发送一条 Windows 系统通知。通知会显示在右下角通知中心。",
                parameters={
                    "title": {
                        "type": "string",
                        "description": "通知标题",
                    },
                    "message": {
                        "type": "string",
                        "description": "通知正文内容",
                    },
                    "duration": {
                        "type": "string",
                        "description": "通知显示时长: 'short'(约5秒) 或 'long'(约25秒)。默认 'short'。",
                    },
                    "icon": {
                        "type": "string",
                        "description": "图标文件路径（可选，支持 .ico/.png）",
                    },
                },
                required_params=["title", "message"],
            ),
            ActionDef(
                name="send_with_action",
                description="发送带动作按钮的通知。点击按钮可打开指定 URL。",
                parameters={
                    "title": {
                        "type": "string",
                        "description": "通知标题",
                    },
                    "message": {
                        "type": "string",
                        "description": "通知正文内容",
                    },
                    "button_text": {
                        "type": "string",
                        "description": "按钮显示文字",
                    },
                    "button_url": {
                        "type": "string",
                        "description": "点击按钮后打开的 URL 或文件路径",
                    },
                    "duration": {
                        "type": "string",
                        "description": "通知显示时长: 'short' 或 'long'。默认 'short'。",
                    },
                },
                required_params=["title", "message", "button_text", "button_url"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "send": self._send,
            "send_with_action": self._send_with_action,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return await handler(params)

    async def _send(self, params: dict[str, Any]) -> ToolResult:
        title = params.get("title", "").strip()
        message = params.get("message", "").strip()
        duration = params.get("duration", "short")
        icon = params.get("icon", "")

        if not title or not message:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="标题和消息内容不能为空",
            )

        try:
            from winotify import Notification, audio

            toast = Notification(
                app_id=self.app_id,
                title=title,
                msg=message,
                duration=duration,
            )
            if icon:
                toast.set_audio(audio.Default, loop=False)
                toast.icon = icon

            toast.show()
            logger.info("发送通知: %s - %s", title, message[:50])
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已发送通知: {title}",
                data={"title": title, "message": message},
            )
        except ImportError:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="winotify 未安装。请运行: pip install winotify",
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"发送通知失败: {e}")

    async def _send_with_action(self, params: dict[str, Any]) -> ToolResult:
        title = params.get("title", "").strip()
        message = params.get("message", "").strip()
        button_text = params.get("button_text", "").strip()
        button_url = params.get("button_url", "").strip()
        duration = params.get("duration", "short")

        if not title or not message:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="标题和消息内容不能为空",
            )
        if not button_text or not button_url:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="按钮文字和 URL 不能为空",
            )

        try:
            from winotify import Notification

            toast = Notification(
                app_id=self.app_id,
                title=title,
                msg=message,
                duration=duration,
            )
            toast.add_actions(label=button_text, launch=button_url)
            toast.show()

            logger.info("发送带按钮通知: %s [%s → %s]", title, button_text, button_url)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已发送通知: {title} (带按钮: {button_text})",
                data={"title": title, "message": message, "button": button_text},
            )
        except ImportError:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="winotify 未安装。请运行: pip install winotify",
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"发送通知失败: {e}")
