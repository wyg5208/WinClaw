"""录音可视化弹窗。

提供录音过程中的可视化反馈，让用户清楚地知道：
- 何时可以开始说话
- 录音进行中的状态（倒计时、音量指示）
- 识别处理中的状态
- 最终结果

支持三种录音模式：
1. 定时录音：显示倒计时进度条
2. VAD录音：显示已录音时长，说完自动停止
3. 对话模式持续监听：显示动态监听状态
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QFont, QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QWidget,
    QSizePolicy,
)

logger = logging.getLogger(__name__)


class RecordState(Enum):
    """录音状态。"""
    PREPARING = "preparing"       # 准备中
    RECORDING = "recording"       # 录音中
    PROCESSING = "processing"     # 识别处理中
    SUCCESS = "success"           # 识别成功
    ERROR = "error"               # 出错
    CANCELLED = "cancelled"       # 已取消


class VoiceWaveWidget(QWidget):
    """语音波形动画控件。

    在录音时显示跳动的音量条动画，给用户直观的视觉反馈。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._bars = 7
        self._bar_heights = [0.3] * self._bars
        self._active = False
        self._tick = 0
        self.setMinimumSize(120, 50)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._animate)

    def start(self) -> None:
        """启动动画。"""
        self._active = True
        self._tick = 0
        self._timer.start()
        self.update()

    def stop(self) -> None:
        """停止动画。"""
        self._active = False
        self._timer.stop()
        self._bar_heights = [0.3] * self._bars
        self.update()

    def _animate(self) -> None:
        """更新动画帧。"""
        import math
        self._tick += 1
        for i in range(self._bars):
            # 生成节奏感的波动效果
            phase = self._tick * 0.5 + i * 0.8
            self._bar_heights[i] = 0.3 + 0.7 * abs(math.sin(phase))
        self.update()

    def paintEvent(self, event) -> None:
        """绘制音量条。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        bar_width = max(6, w // (self._bars * 2))
        gap = max(3, bar_width // 2)
        total_width = self._bars * bar_width + (self._bars - 1) * gap
        x_start = (w - total_width) // 2

        for i in range(self._bars):
            bar_h = int(h * self._bar_heights[i])
            x = x_start + i * (bar_width + gap)
            y = (h - bar_h) // 2

            if self._active:
                color = QColor("#ff4444")
            else:
                color = QColor("#cccccc")

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(x, y, bar_width, bar_h, bar_width // 2, bar_width // 2)

        painter.end()


class VoiceRecordDialog(QDialog):
    """录音可视化弹窗。

    在录音过程中弹出，提供清晰的视觉反馈：
    - 大图标 + 状态文字
    - 波形动画
    - 倒计时进度条
    - 停止按钮
    """

    # 信号
    stop_requested = Signal()          # 用户请求停止录音
    cancelled = Signal()               # 用户取消

    def __init__(
        self,
        duration: float = 30.0,
        parent: Optional[QWidget] = None,
        *,
        vad_mode: bool = True,
    ):
        """初始化录音弹窗。

        Args:
            duration: 录音时长(秒), VAD模式下为最大上限
            parent: 父窗口
            vad_mode: 是否为VAD模式（说完自动停止）
        """
        super().__init__(parent)
        self._duration = duration
        self._elapsed = 0.0
        self._state = RecordState.PREPARING
        self._result_text = ""
        self._vad_mode = vad_mode

        self._countdown_timer: Optional[QTimer] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """初始化界面。"""
        self.setWindowTitle("语音录入")
        self.setFixedSize(380, 320)
        self.setModal(False)  # 非模态，不阻塞主窗口
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # === 状态图标 ===
        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_font = QFont()
        icon_font.setPointSize(48)
        self._icon_label.setFont(icon_font)
        self._icon_label.setText("🎤")
        layout.addWidget(self._icon_label)

        # === 状态文字 ===
        self._status_label = QLabel("准备录音...")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_font = QFont()
        status_font.setPointSize(14)
        status_font.setBold(True)
        self._status_label.setFont(status_font)
        layout.addWidget(self._status_label)

        # === 提示文字 ===
        self._hint_label = QLabel("即将开始，请准备说话")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(self._hint_label)

        # === 波形动画 ===
        self._wave_widget = VoiceWaveWidget()
        layout.addWidget(self._wave_widget)

        # === 进度条 (倒计时) ===
        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(int(self._duration * 10))  # 0.1秒精度
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat(f"0.0 / {self._duration:.0f} 秒")
        self._progress_bar.setStyleSheet(
            "QProgressBar {"
            "  border: 1px solid #ddd;"
            "  border-radius: 6px;"
            "  text-align: center;"
            "  height: 22px;"
            "  background: #f0f0f0;"
            "}"
            "QProgressBar::chunk {"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            "    stop:0 #ff6b6b, stop:1 #ee5a24);"
            "  border-radius: 5px;"
            "}"
        )
        layout.addWidget(self._progress_bar)

        # === 结果文字区域 ===
        self._result_label = QLabel("")
        self._result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_label.setWordWrap(True)
        self._result_label.setStyleSheet("color: #333; font-size: 13px;")
        self._result_label.setVisible(False)
        self._result_label.setMaximumHeight(60)
        layout.addWidget(self._result_label)

        # === 按钮栏 ===
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self._stop_btn = QPushButton("⏹ 停止录音")
        self._stop_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #ff4444;"
            "  color: white;"
            "  border: none;"
            "  border-radius: 6px;"
            "  padding: 8px 24px;"
            "  font-size: 13px;"
            "  font-weight: bold;"
            "}"
            "QPushButton:hover {"
            "  background-color: #cc3333;"
            "}"
        )
        self._stop_btn.clicked.connect(self._on_stop)
        btn_layout.addWidget(self._stop_btn)

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #f0f0f0;"
            "  border: 1px solid #ddd;"
            "  border-radius: 6px;"
            "  padding: 8px 24px;"
            "  font-size: 13px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #e0e0e0;"
            "}"
        )
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)

        layout.addLayout(btn_layout)

    # ====== 状态切换 ======

    def start_recording(self) -> None:
        """切换到录音中状态。"""
        self._state = RecordState.RECORDING
        self._elapsed = 0.0

        self._icon_label.setText("🔴")
        self._status_label.setText("录音中...")
        self._status_label.setStyleSheet("color: #ff4444; font-size: 14px; font-weight: bold;")

        if self._vad_mode:
            # VAD 模式：显示"说完自动停止"提示，无倒计时
            self._hint_label.setText("请说话，说完后自动停止")
            self._hint_label.setStyleSheet("color: #ff6b6b; font-size: 13px; font-weight: bold;")
            self._progress_bar.setVisible(False)
        else:
            # 定时模式：显示倒计时
            self._hint_label.setText("请开始说话")
            self._hint_label.setStyleSheet("color: #ff6b6b; font-size: 13px; font-weight: bold;")
            self._progress_bar.setVisible(True)

        self._wave_widget.start()
        self._stop_btn.setEnabled(True)
        self._result_label.setVisible(False)

        # 启动计时器（VAD模式显示已录时长，定时模式显示倒计时）
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(100)  # 100ms 更新一次
        self._countdown_timer.timeout.connect(self._on_countdown_tick)
        self._countdown_timer.start()

        self.show()
        self.raise_()
        self.activateWindow()

    def set_processing(self) -> None:
        """切换到识别处理中状态。"""
        self._state = RecordState.PROCESSING

        if self._countdown_timer:
            self._countdown_timer.stop()

        self._wave_widget.stop()
        self._icon_label.setText("⏳")
        self._status_label.setText("识别中...")
        self._status_label.setStyleSheet("color: #f39c12; font-size: 14px; font-weight: bold;")
        self._hint_label.setText("正在将语音转为文字，请稍候...")
        self._hint_label.setStyleSheet("color: #888; font-size: 12px;")

        self._progress_bar.setMaximum(0)  # 不确定进度（动画）
        self._progress_bar.setFormat("处理中...")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setText("处理中...")

    def set_success(self, text: str) -> None:
        """切换到识别成功状态。

        Args:
            text: 识别出的文字
        """
        self._state = RecordState.SUCCESS
        self._result_text = text

        self._icon_label.setText("✅")
        self._status_label.setText("识别完成")
        self._status_label.setStyleSheet("color: #27ae60; font-size: 14px; font-weight: bold;")

        display_text = text if len(text) <= 60 else text[:57] + "..."
        self._hint_label.setText("\u201c" + display_text + "\u201d")
        self._hint_label.setStyleSheet("color: #333; font-size: 13px;")

        self._progress_bar.setVisible(False)
        self._stop_btn.setVisible(False)
        self._cancel_btn.setText("关闭")

        # 2秒后自动关闭
        QTimer.singleShot(2000, self._auto_close)

    def set_error(self, error_msg: str) -> None:
        """切换到错误状态。

        Args:
            error_msg: 错误信息
        """
        self._state = RecordState.ERROR

        if self._countdown_timer:
            self._countdown_timer.stop()
        self._wave_widget.stop()

        self._icon_label.setText("❌")
        self._status_label.setText("识别失败")
        self._status_label.setStyleSheet("color: #e74c3c; font-size: 14px; font-weight: bold;")
        self._hint_label.setText(error_msg)
        self._hint_label.setStyleSheet("color: #e74c3c; font-size: 12px;")

        self._progress_bar.setVisible(False)
        self._stop_btn.setVisible(False)
        self._cancel_btn.setText("关闭")

        # 3秒后自动关闭
        QTimer.singleShot(3000, self._auto_close)

    def set_no_speech(self) -> None:
        """未检测到语音。"""
        self._state = RecordState.ERROR

        if self._countdown_timer:
            self._countdown_timer.stop()
        self._wave_widget.stop()

        self._icon_label.setText("🔇")
        self._status_label.setText("未检测到语音")
        self._status_label.setStyleSheet("color: #f39c12; font-size: 14px; font-weight: bold;")
        self._hint_label.setText("请确认麦克风是否正常工作，然后重试")
        self._hint_label.setStyleSheet("color: #888; font-size: 12px;")

        self._progress_bar.setVisible(False)
        self._stop_btn.setVisible(False)
        self._cancel_btn.setText("关闭")

        # 3秒后自动关闭
        QTimer.singleShot(3000, self._auto_close)

    # ====== 对话模式支持 ======

    def start_listening(self) -> None:
        """切换到持续监听状态（对话模式）。

        不显示倒计时进度条，显示动态监听提示。
        """
        self._state = RecordState.RECORDING

        self._icon_label.setText("🔴")
        self._status_label.setText("监听中...")
        self._status_label.setStyleSheet("color: #ff4444; font-size: 14px; font-weight: bold;")
        self._hint_label.setText("请说话，系统会自动识别")
        self._hint_label.setStyleSheet("color: #ff6b6b; font-size: 13px; font-weight: bold;")

        self._wave_widget.start()
        self._progress_bar.setVisible(False)
        self._stop_btn.setText("⏹ 停止监听")
        self._stop_btn.setEnabled(True)

        self.show()
        self.raise_()
        self.activateWindow()

    # ====== 内部方法 ======

    def _on_countdown_tick(self) -> None:
        """倒计时/计时更新。"""
        self._elapsed += 0.1

        if self._vad_mode:
            # VAD 模式：显示已录时长
            self._status_label.setText(f"录音中... {self._elapsed:.1f}s")
            # 达到最大时长自动停止计时器
            if self._elapsed >= self._duration:
                if self._countdown_timer:
                    self._countdown_timer.stop()
        else:
            # 定时模式：显示倒计时进度条
            progress = int(self._elapsed * 10)
            self._progress_bar.setValue(min(progress, self._progress_bar.maximum()))
            self._progress_bar.setFormat(f"{self._elapsed:.1f} / {self._duration:.0f} 秒")

            if self._elapsed >= self._duration:
                if self._countdown_timer:
                    self._countdown_timer.stop()

    def _on_stop(self) -> None:
        """停止录音按钮。"""
        self.stop_requested.emit()

    def _on_cancel(self) -> None:
        """取消按钮。"""
        if self._countdown_timer:
            self._countdown_timer.stop()
        self._wave_widget.stop()
        self.cancelled.emit()
        self.close()

    def _auto_close(self) -> None:
        """自动关闭（成功/失败后延迟关闭）。"""
        if self.isVisible():
            self.close()

    def closeEvent(self, event) -> None:
        """关闭事件。"""
        if self._countdown_timer:
            self._countdown_timer.stop()
        self._wave_widget.stop()
        super().closeEvent(event)
