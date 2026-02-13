"""工作流可视化面板 — 显示工作流执行进度和状态。

功能:
1. 显示工作流名称和总进度
2. 展示每个步骤的状态、耗时
3. 实时更新执行状态
4. 提供取消/暂停控制
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# =====================================================================
# 数据结构
# =====================================================================

@dataclass
class StepInfo:
    """步骤信息。"""
    step_id: str
    name: str
    status: str = "pending"  # pending/running/completed/failed/skipped
    elapsed: float = 0.0
    error: str = ""


@dataclass
class WorkflowInfo:
    """工作流信息。"""
    workflow_id: str
    name: str
    status: str = "pending"  # pending/running/completed/failed/cancelled
    steps: list[StepInfo] = field(default_factory=list)
    current_step_index: int = -1
    total_elapsed: float = 0.0
    start_time: float = 0.0


# =====================================================================
# 步骤组件
# =====================================================================

class StepWidget(QFrame):
    """单个步骤的显示组件。"""

    def __init__(self, step_id: str, name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.step_id = step_id
        self._name = name
        self._status = "pending"
        self._elapsed = 0.0
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """初始化界面。"""
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setLineWidth(1)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        
        # 状态图标
        self._status_label = QLabel("○")
        self._status_label.setFixedWidth(20)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)
        
        # 步骤名称
        self._name_label = QLabel(self._name)
        self._name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._name_label)
        
        # 耗时
        self._time_label = QLabel("")
        self._time_label.setFixedWidth(60)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._time_label)
        
        self._update_style()
    
    def set_status(self, status: str, elapsed: float = 0.0) -> None:
        """设置步骤状态。"""
        self._status = status
        self._elapsed = elapsed
        
        # 更新状态图标
        status_icons = {
            "pending": "○",
            "running": "→",
            "completed": "✓",
            "failed": "✗",
            "skipped": "⊘",
        }
        self._status_label.setText(status_icons.get(status, "○"))
        
        # 更新耗时
        if elapsed > 0:
            self._time_label.setText(f"{elapsed:.1f}s")
        elif status == "running":
            self._time_label.setText("...")
        else:
            self._time_label.setText("")
        
        self._update_style()
    
    def _update_style(self) -> None:
        """根据状态更新样式。"""
        colors = {
            "pending": "#888888",
            "running": "#2196F3",
            "completed": "#4CAF50",
            "failed": "#F44336",
            "skipped": "#9E9E9E",
        }
        color = colors.get(self._status, "#888888")
        
        self._status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        
        if self._status == "running":
            self.setStyleSheet("QFrame { background-color: rgba(33, 150, 243, 0.1); }")
        elif self._status == "failed":
            self.setStyleSheet("QFrame { background-color: rgba(244, 67, 54, 0.1); }")
        else:
            self.setStyleSheet("")


# =====================================================================
# 工作流面板
# =====================================================================

class WorkflowPanel(QGroupBox):
    """工作流可视化面板。"""

    # 信号
    cancel_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("工作流", parent)
        self._workflow: WorkflowInfo | None = None
        self._step_widgets: dict[str, StepWidget] = {}
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_elapsed_time)
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """初始化界面。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)
        
        # 头部：工作流名称 + 进度
        header_layout = QHBoxLayout()
        
        self._workflow_name = QLabel("无活动工作流")
        self._workflow_name.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(self._workflow_name)
        
        header_layout.addStretch()
        
        self._progress_label = QLabel("")
        header_layout.addWidget(self._progress_label)
        
        layout.addLayout(header_layout)
        
        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(6)
        layout.addWidget(self._progress_bar)
        
        # 步骤列表（可滚动）
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setMinimumHeight(120)
        self._scroll_area.setMaximumHeight(250)
        
        self._steps_container = QWidget()
        self._steps_layout = QVBoxLayout(self._steps_container)
        self._steps_layout.setContentsMargins(0, 0, 0, 0)
        self._steps_layout.setSpacing(4)
        self._steps_layout.addStretch()
        
        self._scroll_area.setWidget(self._steps_container)
        layout.addWidget(self._scroll_area)
        
        # 底部：总耗时 + 控制按钮
        footer_layout = QHBoxLayout()
        
        self._elapsed_label = QLabel("")
        footer_layout.addWidget(self._elapsed_label)
        
        footer_layout.addStretch()
        
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setFixedWidth(60)
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)
        self._cancel_btn.setEnabled(False)
        footer_layout.addWidget(self._cancel_btn)
        
        layout.addLayout(footer_layout)
        
        # 初始状态：隐藏
        self._show_idle_state()
    
    def _show_idle_state(self) -> None:
        """显示空闲状态。"""
        self._workflow_name.setText("无活动工作流")
        self._progress_label.setText("")
        self._progress_bar.setValue(0)
        self._elapsed_label.setText("")
        self._cancel_btn.setEnabled(False)
    
    def start_workflow(self, workflow_id: str, name: str, steps: list[dict[str, str]]) -> None:
        """开始新工作流。
        
        Args:
            workflow_id: 工作流ID
            name: 工作流名称
            steps: 步骤列表 [{"id": "...", "name": "..."}]
        """
        # 清理旧步骤
        self._clear_steps()
        
        # 创建工作流信息
        self._workflow = WorkflowInfo(
            workflow_id=workflow_id,
            name=name,
            status="running",
            steps=[StepInfo(step_id=s["id"], name=s["name"]) for s in steps],
            start_time=datetime.now().timestamp(),
        )
        
        # 更新UI
        self._workflow_name.setText(name)
        self._progress_label.setText(f"0/{len(steps)}")
        self._progress_bar.setMaximum(len(steps))
        self._progress_bar.setValue(0)
        self._cancel_btn.setEnabled(True)
        
        # 添加步骤组件
        for step in self._workflow.steps:
            widget = StepWidget(step.step_id, step.name)
            self._step_widgets[step.step_id] = widget
            # 插入到 stretch 之前
            self._steps_layout.insertWidget(self._steps_layout.count() - 1, widget)
        
        # 启动计时器
        self._timer.start(100)
    
    def update_step(self, step_id: str, status: str, elapsed: float = 0.0) -> None:
        """更新步骤状态。
        
        Args:
            step_id: 步骤ID
            status: 状态
            elapsed: 耗时（秒）
        """
        if not self._workflow:
            return
        
        # 更新内部数据
        for i, step in enumerate(self._workflow.steps):
            if step.step_id == step_id:
                step.status = status
                step.elapsed = elapsed
                
                if status == "running":
                    self._workflow.current_step_index = i
                break
        
        # 更新UI
        if step_id in self._step_widgets:
            self._step_widgets[step_id].set_status(status, elapsed)
            # 自动滚动到当前步骤
            self._scroll_area.ensureWidgetVisible(self._step_widgets[step_id])
        
        # 更新进度
        completed = sum(1 for s in self._workflow.steps if s.status in ("completed", "skipped"))
        self._progress_label.setText(f"{completed}/{len(self._workflow.steps)}")
        self._progress_bar.setValue(completed)
    
    def finish_workflow(self, status: str, total_elapsed: float) -> None:
        """工作流完成。
        
        Args:
            status: 最终状态
            total_elapsed: 总耗时（秒）
        """
        if not self._workflow:
            return
        
        self._workflow.status = status
        self._workflow.total_elapsed = total_elapsed
        
        # 停止计时器
        self._timer.stop()
        
        # 更新UI
        self._elapsed_label.setText(f"总耗时: {total_elapsed:.1f}s")
        self._cancel_btn.setEnabled(False)
        
        # 更新进度条颜色
        if status == "completed":
            self._progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #4CAF50; }")
        elif status == "failed":
            self._progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #F44336; }")
        elif status == "cancelled":
            self._progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #FF9800; }")
    
    def _update_elapsed_time(self) -> None:
        """更新耗时显示。"""
        if self._workflow and self._workflow.status == "running":
            elapsed = datetime.now().timestamp() - self._workflow.start_time
            self._elapsed_label.setText(f"耗时: {elapsed:.1f}s")
    
    def _clear_steps(self) -> None:
        """清理步骤组件。"""
        for widget in self._step_widgets.values():
            self._steps_layout.removeWidget(widget)
            widget.deleteLater()
        self._step_widgets.clear()
        self._progress_bar.setStyleSheet("")  # 重置样式
    
    def reset(self) -> None:
        """重置面板。"""
        self._timer.stop()
        self._clear_steps()
        self._workflow = None
        self._show_idle_state()
    
    @property
    def is_active(self) -> bool:
        """是否有活动的工作流。"""
        return self._workflow is not None and self._workflow.status == "running"
    
    @property
    def current_workflow_id(self) -> str | None:
        """当前工作流ID。"""
        return self._workflow.workflow_id if self._workflow else None
