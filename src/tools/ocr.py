"""
OCR 工具 - 基于 RapidOCR 的文字识别

支持:
- 图片文字识别 (截图、照片等)
- 批量识别
- 多语言支持
- 高准确率的离线识别

Phase 4.6 优化：
- 延迟导入：RapidOCR/PIL 仅在实际使用时导入
- 启动速度大幅提升
"""
import asyncio
from pathlib import Path
from typing import Any

# 延迟导入标记
OCR_AVAILABLE: bool | None = None

# 模块引用（延迟加载后赋值）
_RapidOCR = None
_Image = None


def _check_ocr_dependencies() -> bool:
    """检查 OCR 依赖是否可用，延迟导入。"""
    global OCR_AVAILABLE, _RapidOCR, _Image
    if OCR_AVAILABLE is not None:
        return OCR_AVAILABLE

    try:
        from rapidocr_onnxruntime import RapidOCR
        from PIL import Image

        _RapidOCR = RapidOCR
        _Image = Image
        OCR_AVAILABLE = True
    except ImportError:
        OCR_AVAILABLE = False

    return OCR_AVAILABLE


from .base import ActionDef, BaseTool, ToolResult, ToolResultStatus


class OCRTool(BaseTool):
    """OCR 文字识别工具"""

    name = "ocr"
    emoji = "📝"
    title = "文字识别"
    description = "图片文字识别工具,支持截图和照片识别"

    def __init__(self):
        super().__init__()
        self._ocr_engine = None
        # 不在初始化时检查依赖，延迟到实际使用时

    def _check_available(self) -> bool:
        """检查 OCR 功能是否可用。"""
        if not _check_ocr_dependencies():
            raise ImportError("OCR 功能不可用。请安装依赖: pip install rapidocr-onnxruntime pillow")
        return True

    def _get_engine(self):
        """延迟加载 OCR 引擎"""
        self._check_available()
        if self._ocr_engine is None:
            self._ocr_engine = _RapidOCR()
        return self._ocr_engine

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="recognize_file",
                description="识别图片文件中的文字",
                parameters={
                    "image_path": {
                        "type": "string",
                        "description": "图片文件路径 (支持 jpg/png/bmp 等)",
                    },
                    "merge_lines": {
                        "type": "boolean",
                        "description": "是否合并多行文本,默认 True",
                        "default": True,
                    },
                },
                required_params=["image_path"],
            ),
            ActionDef(
                name="recognize_region",
                description="识别图片指定区域的文字",
                parameters={
                    "image_path": {
                        "type": "string",
                        "description": "图片文件路径",
                    },
                    "x": {"type": "integer", "description": "区域左上角 X 坐标"},
                    "y": {"type": "integer", "description": "区域左上角 Y 坐标"},
                    "width": {"type": "integer", "description": "区域宽度"},
                    "height": {"type": "integer", "description": "区域高度"},
                    "merge_lines": {
                        "type": "boolean",
                        "description": "是否合并多行",
                        "default": True,
                    },
                },
                required_params=["image_path", "x", "y", "width", "height"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        """执行 OCR 操作"""
        if action == "recognize_file":
            return await self._recognize_file(**params)
        elif action == "recognize_region":
            return await self._recognize_region(**params)
        else:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"未知动作: {action}",
                output=f"可用动作: {[a.name for a in self.get_actions()]}",
            )

    async def _recognize_file(self, image_path: str, merge_lines: bool = True) -> ToolResult:
        """识别整个图片的文字"""
        try:
            path = Path(image_path).expanduser().resolve()
            if not path.exists():
                return ToolResult(status=ToolResultStatus.ERROR, error=f"图片文件不存在: {image_path}")

            # 检查文件大小 (限制 20MB)
            file_size_mb = path.stat().st_size / (1024 * 1024)
            if file_size_mb > 20:
                return ToolResult(
                    status=ToolResultStatus.ERROR, error=f"图片过大: {file_size_mb:.1f}MB (限制 20MB)"
                )

            # 在线程池中执行 OCR
            loop = asyncio.get_event_loop()
            ocr_engine = self._get_engine()
            result = await loop.run_in_executor(None, ocr_engine, str(path))

            if result is None or len(result) == 0:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS, output="未识别到文字", data={"text": "", "boxes": []}
                )

            # 解析结果
            text_lines = []
            boxes = []

            for line in result[0]:
                if line:
                    box = line[0]  # 坐标框
                    text = line[1]  # 识别文字
                    confidence = line[2]  # 置信度

                    text_lines.append(text)
                    boxes.append(
                        {"text": text, "confidence": float(confidence), "box": [[int(x), int(y)] for x, y in box]}
                    )

            # 合并文本
            full_text = "\n".join(text_lines) if not merge_lines else " ".join(text_lines)

            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"识别成功: {len(text_lines)} 行文字",
                data={"text": full_text, "boxes": boxes, "line_count": len(text_lines)},
            )

        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"识别失败: {e}")

    async def _recognize_region(
        self, image_path: str, x: int, y: int, width: int, height: int, merge_lines: bool = True
    ) -> ToolResult:
        """识别图片指定区域的文字"""
        try:
            path = Path(image_path).expanduser().resolve()
            if not path.exists():
                return ToolResult(status=ToolResultStatus.ERROR, error=f"图片文件不存在: {image_path}")

            self._check_available()

            # 裁剪图片区域
            loop = asyncio.get_event_loop()

            def crop_image():
                img = _Image.open(path)
                region = img.crop((x, y, x + width, y + height))
                return region

            region_img = await loop.run_in_executor(None, crop_image)

            # OCR 识别
            ocr_engine = self._get_engine()
            result = await loop.run_in_executor(None, ocr_engine, region_img)

            if result is None or len(result) == 0:
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    output="区域内未识别到文字",
                    data={"text": "", "region": {"x": x, "y": y, "width": width, "height": height}},
                )

            # 解析结果
            text_lines = []
            boxes = []

            for line in result[0]:
                if line:
                    box = line[0]
                    text = line[1]
                    confidence = line[2]

                    text_lines.append(text)
                    # 坐标偏移
                    adjusted_box = [[int(px + x), int(py + y)] for px, py in box]
                    boxes.append({"text": text, "confidence": float(confidence), "box": adjusted_box})

            full_text = "\n".join(text_lines) if not merge_lines else " ".join(text_lines)

            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"区域识别成功: {len(text_lines)} 行文字",
                data={
                    "text": full_text,
                    "boxes": boxes,
                    "line_count": len(text_lines),
                    "region": {"x": x, "y": y, "width": width, "height": height},
                },
            )

        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=f"区域识别失败: {e}")
