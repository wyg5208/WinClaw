"""
图片输入组件 - 支持粘贴和拖拽图片

功能:
- 粘贴剪贴板图片 (Ctrl+V)
- 拖拽图片文件
- 显示图片预览
- 图片编码为 base64
"""
import base64
import io
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None


class ImageInputWidget(QWidget):
    """图片输入组件 - 支持粘贴、拖拽、显示预览"""

    # 信号
    image_added = Signal(str, str)  # (base64_data, format)
    image_removed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_image: Optional[QImage] = None
        self._setup_ui()
        self.setAcceptDrops(True)

    def _setup_ui(self) -> None:
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # 图片预览区
        self._preview_label = QLabel("📎 无图片 (Ctrl+V 粘贴或拖拽图片)")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(100)
        self._preview_label.setMaximumHeight(200)
        self._preview_label.setStyleSheet("QLabel { border: 2px dashed #ccc; border-radius: 5px; }")
        layout.addWidget(self._preview_label)

        # 按钮行
        btn_layout = QHBoxLayout()
        self._paste_btn = QPushButton("📋 从剪贴板粘贴")
        self._paste_btn.clicked.connect(self._paste_image)
        btn_layout.addWidget(self._paste_btn)

        self._clear_btn = QPushButton("🗑️ 清除图片")
        self._clear_btn.clicked.connect(self._clear_image)
        self._clear_btn.setEnabled(False)
        btn_layout.addWidget(self._clear_btn)

        layout.addLayout(btn_layout)

        # 信息标签
        self._info_label = QLabel("")
        self._info_label.setStyleSheet("QLabel { color: #666; font-size: 11px; }")
        layout.addWidget(self._info_label)

    def _paste_image(self) -> None:
        """从剪贴板粘贴图片"""
        clipboard = QApplication.clipboard()
        image = clipboard.image()

        if image.isNull():
            self._info_label.setText("❌ 剪贴板中没有图片")
            return

        self._load_image(image)

    def _clear_image(self) -> None:
        """清除当前图片"""
        self._current_image = None
        self._preview_label.setText("📎 无图片 (Ctrl+V 粘贴或拖拽图片)")
        self._preview_label.setPixmap(QPixmap())
        self._clear_btn.setEnabled(False)
        self._info_label.setText("")
        self.image_removed.emit()

    def _load_image(self, image: QImage) -> None:
        """加载图片并显示预览"""
        if image.isNull():
            return

        self._current_image = image

        # 显示预览 (等比缩放)
        pixmap = QPixmap.fromImage(image)
        scaled_pixmap = pixmap.scaled(
            self._preview_label.width() - 20,
            self._preview_label.height() - 20,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(scaled_pixmap)
        self._clear_btn.setEnabled(True)

        # 显示信息
        width = image.width()
        height = image.height()
        self._info_label.setText(f"✅ 图片已加载: {width}x{height} 像素")

        # 编码为 base64 并发射信号
        base64_data = self._image_to_base64(image)
        self.image_added.emit(base64_data, "png")

    def _image_to_base64(self, image: QImage) -> str:
        """将 QImage 转为 base64 字符串"""
        # 转为 PNG 格式的字节数组
        byte_array = io.BytesIO()
        
        if PIL_AVAILABLE:
            # 使用 PIL 压缩图片以减小大小
            buffer = io.BytesIO()
            # 将 QImage 转为 PIL Image
            img_bytes = image.bits().tobytes()
            pil_image = Image.frombytes("RGBA", (image.width(), image.height()), img_bytes)
            # 转为 RGB (去除 alpha 通道)
            if pil_image.mode == "RGBA":
                pil_image = pil_image.convert("RGB")
            # 压缩保存
            pil_image.save(buffer, format="JPEG", quality=85)
            base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
        else:
            # 使用 Qt 原生方法
            from PySide6.QtCore import QBuffer, QIODevice
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, "PNG")
            base64_data = base64.b64encode(buffer.data().data()).decode("utf-8")

        return base64_data

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """拖拽进入事件"""
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        """拖拽放下事件"""
        mime_data = event.mimeData()

        # 优先处理图片数据
        if mime_data.hasImage():
            image = QImage(mime_data.imageData())
            self._load_image(image)
            event.acceptProposedAction()
            return

        # 处理文件路径
        if mime_data.hasUrls():
            urls = mime_data.urls()
            if urls:
                file_path = urls[0].toLocalFile()
                path = Path(file_path)

                # 检查是否为图片文件
                if path.suffix.lower() in [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"]:
                    image = QImage(str(path))
                    if not image.isNull():
                        self._load_image(image)
                        event.acceptProposedAction()
                    else:
                        self._info_label.setText(f"❌ 无法加载图片: {path.name}")
                else:
                    self._info_label.setText(f"❌ 不支持的文件类型: {path.suffix}")

    def keyPressEvent(self, event) -> None:
        """键盘事件 - 支持 Ctrl+V 粘贴"""
        if event.matches(Qt.StandardKey.Paste):
            self._paste_image()
        else:
            super().keyPressEvent(event)

    def get_current_image_base64(self) -> Optional[str]:
        """获取当前图片的 base64 编码"""
        if self._current_image is None:
            return None
        return self._image_to_base64(self._current_image)

    def has_image(self) -> bool:
        """是否有图片"""
        return self._current_image is not None
