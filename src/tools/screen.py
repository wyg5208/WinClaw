"""Screen 工具 — 屏幕截图能力（Phase 1.3 增强版）。

增强内容：
- 指定窗口截图（通过 hwnd）
- 截图压缩（控制发送给模型的图片大小）
- 多显示器支持 + list_monitors 动作
- JPEG 格式可选（更小体积）
"""

from __future__ import annotations

import base64
import ctypes
import io
import logging
from pathlib import Path
from typing import Any

import mss
from PIL import Image

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


class ScreenTool(BaseTool):
    """屏幕截图工具。

    Phase 1.3 增强：
    - capture_window: 按窗口句柄截图
    - list_monitors: 列出所有显示器信息
    - model_max_width: 发送给模型的压缩宽度
    - 支持 JPEG 格式（更小体积）
    """

    name = "screen"
    emoji = "📸"
    title = "屏幕截图"
    description = "截取屏幕内容，支持全屏、指定区域、指定窗口截图，多显示器支持"

    def __init__(
        self,
        max_width: int = 1920,
        quality: int = 85,
        model_max_width: int = 1280,
    ):
        self.max_width = max_width
        self.quality = quality
        self.model_max_width = model_max_width

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="capture",
                description="截取屏幕截图。可以截取全屏或指定区域。返回截图的 base64 编码和图片描述信息。",
                parameters={
                    "region": {
                        "type": "object",
                        "description": "截图区域（可选）。不指定则截取全屏。",
                        "properties": {
                            "left": {"type": "integer", "description": "左上角 X 坐标"},
                            "top": {"type": "integer", "description": "左上角 Y 坐标"},
                            "width": {"type": "integer", "description": "宽度"},
                            "height": {"type": "integer", "description": "高度"},
                        },
                    },
                    "monitor": {
                        "type": "integer",
                        "description": "显示器编号（0=全部, 1=主显示器, 2=第二显示器...）。默认1。",
                    },
                    "for_model": {
                        "type": "boolean",
                        "description": "是否为发送给AI模型优化（压缩到更小尺寸）。默认true。",
                    },
                    "save_path": {
                        "type": "string",
                        "description": "截图保存路径（可选）。如 '/path/to/screenshot.png'。不指定则不保存文件。",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="capture_window",
                description="截取指定窗口的截图（通过窗口标题匹配）。",
                parameters={
                    "title": {
                        "type": "string",
                        "description": "窗口标题（支持部分匹配）",
                    },
                    "for_model": {
                        "type": "boolean",
                        "description": "是否为发送给AI模型优化。默认true。",
                    },
                    "save_path": {
                        "type": "string",
                        "description": "截图保存路径（可选）。不指定则不保存文件。",
                    },
                },
                required_params=["title"],
            ),
            ActionDef(
                name="list_monitors",
                description="列出所有显示器信息（分辨率、位置）。",
                parameters={},
                required_params=[],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "capture": self._capture,
            "capture_window": self._capture_window,
            "list_monitors": self._list_monitors,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return await handler(params)

    # ------------------------------------------------------------------
    # capture（增强：for_model 压缩）
    # ------------------------------------------------------------------

    async def _capture(self, params: dict[str, Any]) -> ToolResult:
        region = params.get("region")
        monitor = params.get("monitor", 1)
        for_model = params.get("for_model", True)
        save_path = params.get("save_path")

        try:
            with mss.mss() as sct:
                if region:
                    grab_area = {
                        "left": region.get("left", 0),
                        "top": region.get("top", 0),
                        "width": region.get("width", 800),
                        "height": region.get("height", 600),
                    }
                    screenshot = sct.grab(grab_area)
                else:
                    if monitor < 0 or monitor >= len(sct.monitors):
                        monitor = 1
                    screenshot = sct.grab(sct.monitors[monitor])

                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                return self._encode_image(img, for_model, save_path)

        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"截图失败: {e}",
            )

    # ------------------------------------------------------------------
    # capture_window（新增：窗口截图）
    # ------------------------------------------------------------------

    async def _capture_window(self, params: dict[str, Any]) -> ToolResult:
        title = params.get("title", "")
        for_model = params.get("for_model", True)
        save_path = params.get("save_path")

        if not title:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="窗口标题不能为空",
            )

        try:
            hwnd = self._find_window_by_title(title)
            if hwnd is None:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"未找到标题包含 '{title}' 的窗口",
                )

            # 获取窗口位置和大小
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            left = rect.left
            top = rect.top
            width = rect.right - rect.left
            height = rect.bottom - rect.top

            if width <= 0 or height <= 0:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"窗口 '{title}' 尺寸异常 ({width}x{height})，可能已最小化",
                )

            with mss.mss() as sct:
                grab_area = {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                }
                screenshot = sct.grab(grab_area)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                return self._encode_image(img, for_model, save_path)

        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"窗口截图失败: {e}",
            )

    def _find_window_by_title(self, title: str) -> int | None:
        """通过标题查找窗口句柄（部分匹配）。"""
        import ctypes
        import ctypes.wintypes

        found_hwnd = [None]
        title_lower = title.lower()

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def enum_callback(hwnd, lparam):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                if title_lower in buf.value.lower():
                    if ctypes.windll.user32.IsWindowVisible(hwnd):
                        found_hwnd[0] = hwnd
                        return False  # 停止枚举
            return True

        ctypes.windll.user32.EnumWindows(enum_callback, 0)
        return found_hwnd[0]

    # ------------------------------------------------------------------
    # list_monitors（新增）
    # ------------------------------------------------------------------

    async def _list_monitors(self, params: dict[str, Any]) -> ToolResult:
        try:
            with mss.mss() as sct:
                monitors = sct.monitors
                lines = [f"检测到 {len(monitors) - 1} 个显示器:\n"]

                for i, mon in enumerate(monitors):
                    if i == 0:
                        lines.append(
                            f"  [虚拟屏幕] {mon['width']}x{mon['height']} "
                            f"@ ({mon['left']}, {mon['top']})"
                        )
                    else:
                        lines.append(
                            f"  [显示器 {i}] {mon['width']}x{mon['height']} "
                            f"@ ({mon['left']}, {mon['top']})"
                            f"{' (主)' if i == 1 else ''}"
                        )

                output = "\n".join(lines)
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output=output,
                    data={"monitors": monitors, "count": len(monitors) - 1},
                )

        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"获取显示器信息失败: {e}",
            )

    # ------------------------------------------------------------------
    # 图片编码（公共方法）
    # ------------------------------------------------------------------

    def _encode_image(self, img: Image.Image, for_model: bool = True, save_path: str | None = None) -> ToolResult:
        """压缩并编码图片为 base64，可选保存到文件。"""
        max_w = self.model_max_width if for_model else self.max_width

        if img.width > max_w:
            ratio = max_w / img.width
            new_size = (max_w, int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        img_bytes = buffer.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

        info = f"截图完成: {img.width}x{img.height} 像素, {len(img_bytes) / 1024:.1f}KB"
        if for_model:
            info += " (已为模型优化)"

        # 保存到文件（如果指定了路径）
        saved_path = None
        if save_path:
            try:
                path = Path(save_path).expanduser().resolve()
                path.parent.mkdir(parents=True, exist_ok=True)
                img.save(path, format="PNG")
                saved_path = str(path)
                info += f"\n已保存到: {path}"
                logger.info("截图已保存: %s", path)
            except Exception as e:
                logger.warning("保存截图失败: %s", e)
                info += f"\n保存失败: {e}"

        logger.info(info)

        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=info,
            data={
                "base64": img_base64,
                "width": img.width,
                "height": img.height,
                "size_bytes": len(img_bytes),
                "image_path": saved_path,  # 返回保存的文件路径
            },
        )
