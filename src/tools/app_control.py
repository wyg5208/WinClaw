"""App Control 工具 — 基于 pywinauto 的 Windows 应用控制（Sprint 2.3）。

支持动作：
- launch: 启动应用程序
- list_windows: 列出当前所有可见窗口
- switch_window: 切换到指定窗口（激活/前置）
- close_window: 关闭指定窗口
- get_window_info: 获取窗口详细信息（标题、位置、大小、控件树）
"""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes
import logging
import subprocess
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


class AppControlTool(BaseTool):
    """Windows 应用控制工具。

    通过 pywinauto 和 Win32 API 实现应用启动、窗口管理等操作。
    """

    name = "app_control"
    emoji = "🪟"
    title = "应用控制"
    description = "启动应用、列出窗口、切换窗口、关闭窗口、获取窗口信息"

    def __init__(self, launch_timeout: int = 10):
        self.launch_timeout = launch_timeout

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="launch",
                description="启动一个应用程序。支持可执行文件路径或已注册的程序名。",
                parameters={
                    "program": {
                        "type": "string",
                        "description": "程序路径或名称，如 'notepad', 'calc', 'C:\\\\Program Files\\\\app.exe'",
                    },
                    "args": {
                        "type": "string",
                        "description": "命令行参数（可选）",
                    },
                },
                required_params=["program"],
            ),
            ActionDef(
                name="list_windows",
                description="列出当前所有可见的窗口。返回窗口标题、句柄、进程名。",
                parameters={
                    "filter": {
                        "type": "string",
                        "description": "按标题关键词过滤（可选，不区分大小写）",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="switch_window",
                description="切换到指定窗口（激活并置于前台）。",
                parameters={
                    "title": {
                        "type": "string",
                        "description": "窗口标题（部分匹配）",
                    },
                    "hwnd": {
                        "type": "integer",
                        "description": "窗口句柄（精确定位，优先于 title）",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="close_window",
                description="关闭指定窗口。",
                parameters={
                    "title": {
                        "type": "string",
                        "description": "窗口标题（部分匹配）",
                    },
                    "hwnd": {
                        "type": "integer",
                        "description": "窗口句柄（精确定位，优先于 title）",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="get_window_info",
                description="获取指定窗口的详细信息，包括标题、位置、大小、类名。",
                parameters={
                    "title": {
                        "type": "string",
                        "description": "窗口标题（部分匹配）",
                    },
                    "hwnd": {
                        "type": "integer",
                        "description": "窗口句柄（精确定位，优先于 title）",
                    },
                },
                required_params=[],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "launch": self._launch,
            "list_windows": self._list_windows,
            "switch_window": self._switch_window,
            "close_window": self._close_window,
            "get_window_info": self._get_window_info,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return await handler(params)

    # ------------------------------------------------------------------
    # launch
    # ------------------------------------------------------------------

    async def _launch(self, params: dict[str, Any]) -> ToolResult:
        program = params.get("program", "").strip()
        args = params.get("args", "").strip()

        if not program:
            return ToolResult(status=ToolResultStatus.ERROR, error="程序名不能为空")

        try:
            cmd = [program]
            if args:
                cmd.extend(args.split())

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=True,
            )
            # 短暂等待检查是否立即退出
            await asyncio.sleep(0.5)
            if proc.poll() is not None and proc.returncode != 0:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"程序启动后立即退出，退出码: {proc.returncode}",
                )

            logger.info("启动应用: %s %s (PID: %d)", program, args, proc.pid)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已启动: {program} (PID: {proc.pid})",
                data={"pid": proc.pid, "program": program},
            )
        except FileNotFoundError:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"未找到程序: {program}",
            )
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"启动失败: {e}",
            )

    # ------------------------------------------------------------------
    # list_windows
    # ------------------------------------------------------------------

    async def _list_windows(self, params: dict[str, Any]) -> ToolResult:
        title_filter = params.get("filter", "").lower()

        windows = self._enum_visible_windows()

        if title_filter:
            windows = [w for w in windows if title_filter in w["title"].lower()]

        if not windows:
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="未找到匹配的窗口" if title_filter else "当前没有可见窗口",
                data={"windows": [], "count": 0},
            )

        lines = [f"找到 {len(windows)} 个窗口:\n"]
        for w in windows[:50]:
            lines.append(f"  [{w['hwnd']}] {w['title']}")

        if len(windows) > 50:
            lines.append(f"  ...(仅显示前 50 个，共 {len(windows)} 个)")

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={"windows": windows[:50], "count": len(windows)},
        )

    # ------------------------------------------------------------------
    # switch_window
    # ------------------------------------------------------------------

    async def _switch_window(self, params: dict[str, Any]) -> ToolResult:
        hwnd = self._resolve_hwnd(params)
        if hwnd is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="未找到指定窗口。请提供 title 或 hwnd 参数。",
            )

        try:
            user32 = ctypes.windll.user32
            # 如果窗口最小化，先恢复
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)

            title = self._get_window_title(hwnd)
            logger.info("切换窗口: %s (hwnd=%s)", title, hwnd)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已切换到窗口: {title}",
                data={"hwnd": hwnd, "title": title},
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"切换窗口失败: {e}")

    # ------------------------------------------------------------------
    # close_window
    # ------------------------------------------------------------------

    async def _close_window(self, params: dict[str, Any]) -> ToolResult:
        hwnd = self._resolve_hwnd(params)
        if hwnd is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="未找到指定窗口。请提供 title 或 hwnd 参数。",
            )

        try:
            title = self._get_window_title(hwnd)
            WM_CLOSE = 0x0010
            ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            logger.info("关闭窗口: %s (hwnd=%s)", title, hwnd)
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"已发送关闭请求: {title}",
                data={"hwnd": hwnd, "title": title},
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"关闭窗口失败: {e}")

    # ------------------------------------------------------------------
    # get_window_info
    # ------------------------------------------------------------------

    async def _get_window_info(self, params: dict[str, Any]) -> ToolResult:
        hwnd = self._resolve_hwnd(params)
        if hwnd is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="未找到指定窗口。请提供 title 或 hwnd 参数。",
            )

        try:
            user32 = ctypes.windll.user32
            title = self._get_window_title(hwnd)

            # 获取位置和大小
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            x, y = rect.left, rect.top
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            # 获取类名
            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_buf, 256)
            class_name = class_buf.value

            # 获取进程 ID
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            is_visible = bool(user32.IsWindowVisible(hwnd))
            is_minimized = bool(user32.IsIconic(hwnd))
            is_maximized = bool(user32.IsZoomed(hwnd))

            info = {
                "hwnd": hwnd,
                "title": title,
                "class_name": class_name,
                "pid": pid.value,
                "position": {"x": x, "y": y},
                "size": {"width": w, "height": h},
                "visible": is_visible,
                "minimized": is_minimized,
                "maximized": is_maximized,
            }

            lines = [
                f"窗口信息: {title}",
                f"  句柄: {hwnd}",
                f"  类名: {class_name}",
                f"  进程ID: {pid.value}",
                f"  位置: ({x}, {y})",
                f"  大小: {w} x {h}",
                f"  状态: {'可见' if is_visible else '隐藏'}"
                f"{', 最小化' if is_minimized else ''}"
                f"{', 最大化' if is_maximized else ''}",
            ]

            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output="\n".join(lines),
                data=info,
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"获取窗口信息失败: {e}")

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _enum_visible_windows(self) -> list[dict[str, Any]]:
        """枚举所有可见窗口。"""
        windows: list[dict[str, Any]] = []
        user32 = ctypes.windll.user32

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def callback(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value.strip()
                    if title:
                        windows.append({"hwnd": hwnd, "title": title})
            return True

        user32.EnumWindows(callback, 0)
        return windows

    def _resolve_hwnd(self, params: dict[str, Any]) -> int | None:
        """从参数中解析窗口句柄。"""
        hwnd = params.get("hwnd")
        if hwnd is not None:
            return int(hwnd)

        title = params.get("title", "")
        if not title:
            return None

        title_lower = title.lower()
        for w in self._enum_visible_windows():
            if title_lower in w["title"].lower():
                return w["hwnd"]
        return None

    @staticmethod
    def _get_window_title(hwnd: int) -> str:
        """获取窗口标题。"""
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        return "(无标题)"
