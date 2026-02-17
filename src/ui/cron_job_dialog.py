"""定时任务管理对话框 — 管理 Cron 定时任务。

功能：
- 显示所有定时任务列表
- 新增定时任务（支持 AI 任务和命令任务）
- 编辑/删除/暂停/恢复任务
- 查看任务状态和历史执行结果
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src.tools.cron import CronTool

logger = logging.getLogger(__name__)


class CronJobCard(QFrame):
    """单个定时任务卡片组件。"""

    pause_requested = Signal(str)  # 请求暂停任务
    resume_requested = Signal(str)  # 请求恢复任务
    edit_requested = Signal(str)  # 请求编辑任务
    delete_requested = Signal(str)  # 请求删除任务
    view_result_requested = Signal(str)  # 请求查看执行结果

    def __init__(self, job_info: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("cronJobCard")
        self._job_info = job_info
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 图标和类型
        job_type = self._job_info.get("job_type", "command")
        type_icon = "🤖" if job_type == "ai_task" else "💻"
        icon_label = QLabel(type_icon)
        icon_label.setFont(QFont("", 20))
        icon_label.setFixedWidth(36)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        # 中间信息区
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # 任务ID和描述
        job_id = self._job_info.get("id", "unknown")
        description = self._job_info.get("name", "") or job_id
        name_label = QLabel(f"<b>{description}</b> <span style='color: gray;'>({job_id})</span>")
        name_label.setTextFormat(Qt.TextFormat.RichText)
        info_layout.addWidget(name_label)

        # 触发方式
        trigger_info = self._format_trigger_info()
        next_run = self._job_info.get("next_run", "")
        next_run_str = next_run if next_run else "未调度"
        trigger_label = QLabel(f"触发: {trigger_info} | 下次: {next_run_str}")
        trigger_label.setObjectName("detailLabel")
        info_layout.addWidget(trigger_label)

        # 状态和上次执行
        status_layout = QHBoxLayout()
        status_layout.setSpacing(8)

        self._status_label = QLabel()
        self._status_label.setObjectName("statusLabel")
        # 先不调用 _update_status_display，等按钮创建后再调用
        status_layout.addWidget(self._status_label)

        last_run = self._job_info.get("last_run", "从未执行")
        last_result = self._job_info.get("last_result", "")
        result_preview = last_result[:30] + "..." if len(last_result) > 30 else last_result
        last_info = f"上次: {last_run}"
        if result_preview:
            last_info += f" | {result_preview}"
        last_label = QLabel(last_info)
        last_label.setObjectName("detailLabel")
        status_layout.addWidget(last_label)
        status_layout.addStretch()

        info_layout.addLayout(status_layout)
        layout.addLayout(info_layout, stretch=1)

        # 操作按钮
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(4)

        # 第一行：暂停/恢复 + 编辑
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(4)

        self._pause_btn = QPushButton("暂停")
        self._pause_btn.setFixedWidth(50)
        self._pause_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pause_btn.clicked.connect(self._on_pause_resume)
        row1_layout.addWidget(self._pause_btn)

        edit_btn = QPushButton("编辑")
        edit_btn.setFixedWidth(50)
        edit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._job_info.get("id", "")))
        row1_layout.addWidget(edit_btn)

        btn_layout.addLayout(row1_layout)

        # 第二行：删除 + 查看结果
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(4)

        delete_btn = QPushButton("删除")
        delete_btn.setFixedWidth(50)
        delete_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        delete_btn.clicked.connect(self._on_delete)
        row2_layout.addWidget(delete_btn)

        result_btn = QPushButton("结果")
        result_btn.setFixedWidth(50)
        result_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        result_btn.clicked.connect(lambda: self.view_result_requested.emit(self._job_info.get("id", "")))
        row2_layout.addWidget(result_btn)

        btn_layout.addLayout(row2_layout)
        layout.addLayout(btn_layout)
        
        # 按钮创建后，再更新状态显示
        self._update_status_display(self._job_info.get("status", "active"))

    def _format_trigger_info(self) -> str:
        """格式化触发信息。"""
        trigger = self._job_info.get("trigger", "")
        if "cron" in trigger.lower():
            # 尝试解析 cron 表达式
            return f"Cron: {trigger.split(':')[-1].strip() if ':' in trigger else trigger}"
        elif "interval" in trigger.lower():
            return f"间隔: {trigger}"
        elif "date" in trigger.lower():
            return f"一次性: {trigger}"
        return trigger or "未知"

    def _update_status_display(self, status: str):
        """更新状态显示。"""
        self._status_label.setProperty("status", status)
        # 刷新样式
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
        
        if status == "active":
            self._status_label.setText("▶ 活动")
            if hasattr(self, '_pause_btn') and self._pause_btn:
                self._pause_btn.setText("暂停")
        else:
            self._status_label.setText("⏸ 暂停")
            if hasattr(self, '_pause_btn') and self._pause_btn:
                self._pause_btn.setText("恢复")

    def _on_pause_resume(self):
        """暂停/恢复任务。"""
        job_id = self._job_info.get("id", "")
        status = self._job_info.get("status", "active")
        if status == "active":
            self.pause_requested.emit(job_id)
        else:
            self.resume_requested.emit(job_id)

    def _on_delete(self):
        """删除任务。"""
        job_id = self._job_info.get("id", "")
        self.delete_requested.emit(job_id)

    def update_job_info(self, job_info: dict):
        """更新任务信息。"""
        self._job_info = job_info
        self._update_status_display(job_info.get("status", "active"))


class CronJobEditDialog(QDialog):
    """新增/编辑定时任务对话框。"""

    def __init__(self, cron_tool: "CronTool", job_info: dict | None = None, parent=None):
        super().__init__(parent)
        self._cron_tool = cron_tool
        self._job_info = job_info  # None 表示新增，否则为编辑
        self._result = None
        self._setup_ui()
        if job_info:
            self._populate_fields()

    def _setup_ui(self):
        is_edit = self._job_info is not None
        title = "编辑定时任务" if is_edit else "新增定时任务"
        self.setWindowTitle(title)
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 任务ID
        id_layout = QHBoxLayout()
        id_label = QLabel("任务ID:")
        id_label.setFixedWidth(80)
        self._id_input = QLineEdit()
        self._id_input.setPlaceholderText("唯一标识符，如: daily_report")
        if is_edit:
            self._id_input.setReadOnly(True)
        id_layout.addWidget(id_label)
        id_layout.addWidget(self._id_input)
        layout.addLayout(id_layout)

        # 描述
        desc_layout = QHBoxLayout()
        desc_label = QLabel("描述:")
        desc_label.setFixedWidth(80)
        self._desc_input = QLineEdit()
        self._desc_input.setPlaceholderText("任务描述（可选）")
        desc_layout.addWidget(desc_label)
        desc_layout.addWidget(self._desc_input)
        layout.addLayout(desc_layout)

        # 任务类型
        type_group = QGroupBox("任务类型")
        type_layout = QHBoxLayout(type_group)
        self._ai_radio = QRadioButton("AI 任务")
        self._ai_radio.setChecked(True)
        self._cmd_radio = QRadioButton("命令任务")
        type_layout.addWidget(self._ai_radio)
        type_layout.addWidget(self._cmd_radio)
        type_layout.addStretch()
        layout.addWidget(type_group)

        # 触发方式
        trigger_group = QGroupBox("触发方式")
        trigger_layout = QVBoxLayout(trigger_group)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("触发类型:"))
        self._trigger_type_combo = QComboBox()
        self._trigger_type_combo.addItems(["Cron表达式", "间隔执行", "一次性"])
        self._trigger_type_combo.currentIndexChanged.connect(self._on_trigger_type_changed)
        type_row.addWidget(self._trigger_type_combo)
        type_row.addStretch()
        trigger_layout.addLayout(type_row)

        # Cron 表达式输入 - 包装在 QWidget 中以便控制可见性
        self._cron_widget = QWidget()
        self._cron_layout = QHBoxLayout(self._cron_widget)
        self._cron_layout.setContentsMargins(0, 0, 0, 0)
        self._cron_layout.addWidget(QLabel("Cron表达式:"))
        self._cron_input = QLineEdit()
        self._cron_input.setPlaceholderText("分 时 日 月 周，如: 0 9 * * * (每天9点)")
        self._cron_layout.addWidget(self._cron_input)
        trigger_layout.addWidget(self._cron_widget)

        # 间隔输入 - 包装在 QWidget 中以便控制可见性
        self._interval_widget = QWidget()
        self._interval_layout = QHBoxLayout(self._interval_widget)
        self._interval_layout.setContentsMargins(0, 0, 0, 0)
        self._interval_layout.addWidget(QLabel("间隔秒数:"))
        self._interval_input = QSpinBox()
        self._interval_input.setRange(1, 86400 * 30)
        self._interval_input.setValue(3600)
        self._interval_layout.addWidget(self._interval_input)
        self._interval_layout.addWidget(QLabel("秒"))
        self._interval_layout.addStretch()
        trigger_layout.addWidget(self._interval_widget)

        # 一次性执行时间 - 包装在 QWidget 中以便控制可见性
        self._once_widget = QWidget()
        self._once_layout = QHBoxLayout(self._once_widget)
        self._once_layout.setContentsMargins(0, 0, 0, 0)
        self._once_layout.addWidget(QLabel("执行时间:"))
        self._once_input = QLineEdit()
        self._once_input.setPlaceholderText("YYYY-MM-DD HH:MM:SS")
        self._once_layout.addWidget(self._once_input)
        trigger_layout.addWidget(self._once_widget)

        # 默认显示 Cron 表达式
        self._on_trigger_type_changed(0)
        layout.addWidget(trigger_group)

        # AI 任务配置
        self._ai_group = QGroupBox("AI 任务配置")
        ai_layout = QVBoxLayout(self._ai_group)

        instruction_label = QLabel("AI指令:")
        ai_layout.addWidget(instruction_label)
        self._instruction_input = QTextEdit()
        self._instruction_input.setPlaceholderText("输入要执行的 AI 指令...")
        self._instruction_input.setMaximumHeight(100)
        ai_layout.addWidget(self._instruction_input)

        config_row = QHBoxLayout()
        config_row.addWidget(QLabel("最大步数:"))
        self._max_steps_input = QSpinBox()
        self._max_steps_input.setRange(1, 200)
        self._max_steps_input.setValue(60)
        config_row.addWidget(self._max_steps_input)
        
        config_row.addWidget(QLabel("结果处理:"))
        self._result_action_combo = QComboBox()
        self._result_action_combo.addItems(["发送通知", "追加到文件", "忽略"])
        config_row.addWidget(self._result_action_combo)
        
        config_row.addWidget(QLabel("文件路径:"))
        self._result_file_input = QLineEdit()
        self._result_file_input.setPlaceholderText("文件路径（可选）")
        config_row.addWidget(self._result_file_input)
        
        ai_layout.addLayout(config_row)
        layout.addWidget(self._ai_group)

        # 命令任务配置
        self._cmd_group = QGroupBox("命令任务配置")
        cmd_layout = QVBoxLayout(self._cmd_group)
        cmd_layout.addWidget(QLabel("执行命令:"))
        self._command_input = QLineEdit()
        self._command_input.setPlaceholderText("如: python script.py 或 PowerShell 命令")
        cmd_layout.addWidget(self._command_input)
        self._cmd_group.setVisible(False)
        layout.addWidget(self._cmd_group)

        # 连接任务类型切换
        self._ai_radio.toggled.connect(self._on_task_type_changed)
        self._on_task_type_changed()

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)

    def _on_trigger_type_changed(self, index: int):
        """触发类型切换。"""
        # 直接控制各个输入 widget 的可见性
        self._cron_widget.setVisible(index == 0)
        self._interval_widget.setVisible(index == 1)
        self._once_widget.setVisible(index == 2)

    def _on_task_type_changed(self):
        """任务类型切换。"""
        is_ai = self._ai_radio.isChecked()
        self._ai_group.setVisible(is_ai)
        self._cmd_group.setVisible(not is_ai)

    def _populate_fields(self):
        """填充编辑字段。"""
        if not self._job_info:
            return

        self._id_input.setText(self._job_info.get("id", ""))
        self._desc_input.setText(self._job_info.get("name", ""))

        job_type = self._job_info.get("job_type", "command")
        self._ai_radio.setChecked(job_type == "ai_task")
        self._cmd_radio.setChecked(job_type != "ai_task")

        # 根据触发类型填充
        trigger = self._job_info.get("trigger", "")
        if "cron" in trigger.lower():
            self._trigger_type_combo.setCurrentIndex(0)
            # 尝试提取 cron 表达式
        elif "interval" in trigger.lower():
            self._trigger_type_combo.setCurrentIndex(1)
        else:
            self._trigger_type_combo.setCurrentIndex(2)

    def _on_save(self):
        """保存任务。"""
        job_id = self._id_input.text().strip()
        if not job_id:
            QMessageBox.warning(self, "错误", "请输入任务ID")
            return

        description = self._desc_input.text().strip()
        is_ai = self._ai_radio.isChecked()
        trigger_type = self._trigger_type_combo.currentIndex()

        # 收集参数
        params = {"job_id": job_id, "description": description}

        if trigger_type == 0:
            # Cron
            params["trigger_type"] = "cron"
            cron_expr = self._cron_input.text().strip()
            if not cron_expr:
                QMessageBox.warning(self, "错误", "请输入 Cron 表达式")
                return
            params["cron_expr"] = cron_expr
        elif trigger_type == 1:
            # Interval
            params["trigger_type"] = "interval"
            params["interval_seconds"] = self._interval_input.value()
        else:
            # Once
            params["trigger_type"] = "once"
            run_date = self._once_input.text().strip()
            if not run_date:
                QMessageBox.warning(self, "错误", "请输入执行时间")
                return
            params["run_date"] = run_date

        if is_ai:
            params["task_instruction"] = self._instruction_input.toPlainText().strip()
            if not params["task_instruction"]:
                QMessageBox.warning(self, "错误", "请输入 AI 指令")
                return
            params["max_steps"] = self._max_steps_input.value()
            result_action_map = {0: "notify", 1: "append_file", 2: "ignore"}
            params["result_action"] = result_action_map[self._result_action_combo.currentIndex()]
            params["result_file"] = self._result_file_input.text().strip()
            
            action = "add_ai_task"
        else:
            params["command"] = self._command_input.text().strip()
            if not params["command"]:
                QMessageBox.warning(self, "错误", "请输入执行命令")
                return
            
            # 根据触发类型选择动作
            if trigger_type == 0:
                action = "add_cron"
                params["cron_expr"] = self._cron_input.text().strip()
            elif trigger_type == 1:
                action = "add_interval"
                params["interval_seconds"] = self._interval_input.value()
            else:
                action = "add_once"
                params["run_date"] = self._once_input.text().strip()

        # 执行 - 直接操作存储层和调度器
        try:
            # 确保调度器已初始化
            self._cron_tool._ensure_scheduler()
            
            # 导入必要模块
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.interval import IntervalTrigger
            from apscheduler.triggers.date import DateTrigger
            from src.tools.cron_storage import StoredJob, JobStatus, JobType, TriggerType
            
            # 创建触发器
            trigger = None
            trigger_config = {}
            
            if trigger_type == 0:
                # Cron
                parts = params["cron_expr"].split()
                if len(parts) != 5:
                    QMessageBox.warning(self, "错误", "Cron 表达式格式错误，应为：minute hour day month day_of_week")
                    return
                trigger_config = {
                    "minute": parts[0],
                    "hour": parts[1],
                    "day": parts[2],
                    "month": parts[3],
                    "day_of_week": parts[4],
                }
                trigger = CronTrigger(**trigger_config)
                trigger_type_str = "cron"
                
            elif trigger_type == 1:
                # Interval
                trigger_config = {"seconds": params["interval_seconds"]}
                trigger = IntervalTrigger(**trigger_config)
                trigger_type_str = "interval"
                
            else:
                # Once
                run_date = datetime.strptime(params["run_date"], "%Y-%m-%d %H:%M:%S")
                trigger_config = {"run_date": run_date.isoformat()}
                trigger = DateTrigger(run_date=run_date)
                trigger_type_str = "once"
            
            # 选择执行函数
            if is_ai:
                func = self._cron_tool._execute_ai_task
                args = [
                    params["task_instruction"],
                    job_id,
                    params["max_steps"],
                    params["result_action"],
                    params["result_file"],
                ]
                job_type = JobType.AI_TASK
                command = ""
                task_instruction = params["task_instruction"]
                max_steps = params["max_steps"]
                result_action = params["result_action"]
                result_file = params["result_file"]
            else:
                func = self._cron_tool._execute_command
                args = [params["command"], job_id]
                job_type = JobType.COMMAND
                command = params["command"]
                task_instruction = ""
                max_steps = 10
                result_action = "notify"
                result_file = ""
            
            # 添加到调度器
            job = self._cron_tool.scheduler.add_job(
                func=func,
                trigger=trigger,
                args=args,
                id=job_id,
                name=description or job_id,
                replace_existing=True,
            )
            
            # 保存到存储层
            stored_job = StoredJob(
                job_id=job_id,
                trigger_type=TriggerType.CRON if trigger_type_str == "cron" else (TriggerType.INTERVAL if trigger_type_str == "interval" else TriggerType.DATE),
                trigger_config=trigger_config,
                command=command,
                description=description,
                created_at=datetime.now(),
                last_run=None,
                status=JobStatus.ACTIVE,
                job_type=job_type,
                task_instruction=task_instruction,
                max_steps=max_steps,
                result_action=result_action,
                result_file=result_file,
            )
            self._cron_tool.storage.save_job(stored_job)
            
            self._result = {"job_id": job_id, "next_run": str(job.next_run_time) if job.next_run_time else None}
            self.accept()
            
        except Exception as e:
            import traceback
            logger.error(f"保存任务失败: {e}\n{traceback.format_exc()}")
            QMessageBox.warning(self, "保存失败", str(e))

    def get_result(self) -> Any:
        """获取保存结果。"""
        return self._result


class JobResultDialog(QDialog):
    """任务执行结果对话框。"""

    def __init__(self, job_info: dict, parent=None):
        super().__init__(parent)
        self._job_info = job_info
        self._setup_ui()

    def _setup_ui(self):
        job_id = self._job_info.get("id", "unknown")
        description = self._job_info.get("name", job_id)
        self.setWindowTitle(f"执行结果 - {description}")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 基本信息
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel(f"任务ID: {job_id}"))
        info_layout.addStretch()
        last_run = self._job_info.get("last_run", "从未执行")
        info_layout.addWidget(QLabel(f"上次执行: {last_run}"))
        layout.addLayout(info_layout)

        # 执行结果
        result_group = QGroupBox("执行结果")
        result_layout = QVBoxLayout(result_group)
        self._result_text = QTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setPlainText(self._job_info.get("last_result", "暂无执行结果"))
        result_layout.addWidget(self._result_text)
        layout.addWidget(result_group)

        # 关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)


class CronJobDialog(QDialog):
    """定时任务管理对话框。"""

    def __init__(self, cron_tool: "CronTool", parent=None):
        super().__init__(parent)
        self._cron_tool = cron_tool
        self._jobs: list[dict] = []
        self._setup_ui()
        self._load_jobs()

    def _setup_ui(self):
        self.setWindowTitle("⏰ 定时任务管理")
        self.setMinimumSize(700, 550)
        self.resize(800, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 顶部标题
        header_layout = QHBoxLayout()
        title_label = QLabel("⏰ 定时任务管理")
        title_label.setFont(QFont("", 14, QFont.Weight.Bold))
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self._count_label = QLabel("")
        header_layout.addWidget(self._count_label)
        layout.addLayout(header_layout)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # 筛选区域
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        filter_layout.addWidget(QLabel("筛选:"))
        self._status_filter = QComboBox()
        self._status_filter.addItems(["全部", "活动", "暂停"])
        self._status_filter.setFixedWidth(80)
        self._status_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self._status_filter)

        filter_layout.addWidget(QLabel("搜索:"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("输入任务ID或描述...")
        self._search_input.setMinimumWidth(200)
        self._search_input.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self._search_input)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # 操作按钮
        action_layout = QHBoxLayout()
        new_btn = QPushButton("+ 新增任务")
        new_btn.clicked.connect(self._on_new_job)
        action_layout.addWidget(new_btn)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self._load_jobs)
        action_layout.addWidget(refresh_btn)

        action_layout.addStretch()
        layout.addLayout(action_layout)

        # 任务列表
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._job_list_widget = QWidget()
        self._job_list_layout = QVBoxLayout(self._job_list_widget)
        self._job_list_layout.setContentsMargins(0, 0, 0, 0)
        self._job_list_layout.setSpacing(6)

        self._scroll_area.setWidget(self._job_list_widget)
        layout.addWidget(self._scroll_area, stretch=1)

        # 空状态提示 - 不添加到布局，由 _refresh_job_list 动态管理
        self._empty_label = None

        # 底部统计
        stats_layout = QHBoxLayout()
        self._stats_label = QLabel("")
        stats_layout.addWidget(self._stats_label)
        stats_layout.addStretch()
        layout.addLayout(stats_layout)

        # 关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _load_jobs(self):
        """加载任务列表。"""
        try:
            # 确保调度器已初始化（这会恢复持久化任务）
            self._cron_tool._ensure_scheduler()
            
            # 直接从存储层获取任务，避免事件循环冲突
            stored_jobs = self._cron_tool.storage.get_all_jobs()
            
            # 获取运行中的任务信息
            running_jobs = {}
            if self._cron_tool.scheduler:
                for job in self._cron_tool.scheduler.get_jobs():
                    running_jobs[job.id] = job
            
            # 转换为字典格式
            self._jobs = []
            for stored in stored_jobs:
                running = running_jobs.get(stored.job_id)
                job_info = {
                    "id": stored.job_id,
                    "name": stored.description or stored.job_id,
                    "job_type": stored.job_type.value if stored.job_type else "command",
                    "trigger": str(running.trigger) if running else stored.trigger_type.value,
                    "next_run": str(running.next_run_time) if running and running.next_run_time else None,
                    "status": stored.status.value,
                    "last_run": stored.last_run.strftime("%Y-%m-%d %H:%M") if stored.last_run else "从未执行",
                    "last_result": stored.last_result or "",
                }
                self._jobs.append(job_info)
        except Exception as e:
            logger.error(f"加载任务异常: {e}")
            self._jobs = []

        self._refresh_job_list()

    def _refresh_job_list(self):
        """刷新任务列表显示。"""
        # 清空现有卡片（不删除 _empty_label）
        while self._job_list_layout.count():
            item = self._job_list_layout.takeAt(0)
            widget = item.widget()
            if widget and widget != self._empty_label:
                widget.deleteLater()

        # 应用筛选
        filtered = self._apply_filter()

        # 更新统计
        total = len(self._jobs)
        active = sum(1 for j in self._jobs if j.get("status") == "active")
        paused = total - active
        self._count_label.setText(f"{len(filtered)} / {total} 个任务")
        self._stats_label.setText(f"总数: {total} | 活动: {active} | 暂停: {paused}")

        if not filtered:
            # 创建新的空状态提示
            self._empty_label = QLabel(
                "🎉 暂无定时任务\n\n"
                "点击「新增任务」创建定时执行的 AI 任务或命令任务。"
            )
            self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._empty_label.setObjectName("detailLabel")
            self._empty_label.setWordWrap(True)
            self._job_list_layout.addWidget(self._empty_label)
            return

        self._empty_label = None

        for job_info in filtered:
            card = CronJobCard(job_info)
            card.pause_requested.connect(self._on_pause_job)
            card.resume_requested.connect(self._on_resume_job)
            card.edit_requested.connect(self._on_edit_job)
            card.delete_requested.connect(self._on_delete_job)
            card.view_result_requested.connect(self._on_view_result)
            self._job_list_layout.addWidget(card)

        # 底部弹性空间
        self._job_list_layout.addStretch()

    def _apply_filter(self) -> list[dict]:
        """应用筛选条件。"""
        status_filter = self._status_filter.currentText()
        search_text = self._search_input.text().strip().lower()

        result = []
        for job in self._jobs:
            # 状态筛选
            if status_filter == "活动" and job.get("status") != "active":
                continue
            if status_filter == "暂停" and job.get("status") != "paused":
                continue

            # 搜索筛选
            if search_text:
                job_id = job.get("id", "").lower()
                name = job.get("name", "").lower()
                if search_text not in job_id and search_text not in name:
                    continue

            result.append(job)

        return result

    def _on_filter_changed(self):
        """筛选条件改变。"""
        self._refresh_job_list()

    def _on_new_job(self):
        """新增任务。"""
        dlg = CronJobEditDialog(self._cron_tool, None, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load_jobs()

    def _on_edit_job(self, job_id: str):
        """编辑任务。"""
        job_info = next((j for j in self._jobs if j.get("id") == job_id), None)
        if not job_info:
            return

        dlg = CronJobEditDialog(self._cron_tool, job_info, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load_jobs()

    def _on_delete_job(self, job_id: str):
        """删除任务。"""
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除任务「{job_id}」？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            # 从调度器删除
            if self._cron_tool._initialized and self._cron_tool.scheduler:
                try:
                    self._cron_tool.scheduler.remove_job(job_id)
                except Exception:
                    pass

            # 从存储删除
            self._cron_tool.storage.delete_job(job_id)
            self._load_jobs()
        except Exception as e:
            QMessageBox.warning(self, "删除失败", str(e))

    def _on_pause_job(self, job_id: str):
        """暂停任务。"""
        try:
            # 暂停调度器中的任务
            if self._cron_tool._initialized and self._cron_tool.scheduler:
                self._cron_tool.scheduler.pause_job(job_id)

            # 更新存储状态
            from src.tools.cron_storage import JobStatus
            self._cron_tool.storage.update_status(job_id, JobStatus.PAUSED)
            self._load_jobs()
        except Exception as e:
            QMessageBox.warning(self, "暂停失败", str(e))

    def _on_resume_job(self, job_id: str):
        """恢复任务。"""
        try:
            # 恢复调度器中的任务
            if self._cron_tool._initialized and self._cron_tool.scheduler:
                self._cron_tool.scheduler.resume_job(job_id)

            # 更新存储状态
            from src.tools.cron_storage import JobStatus
            self._cron_tool.storage.update_status(job_id, JobStatus.ACTIVE)
            self._load_jobs()
        except Exception as e:
            QMessageBox.warning(self, "恢复失败", str(e))

    def _on_view_result(self, job_id: str):
        """查看执行结果。"""
        job_info = next((j for j in self._jobs if j.get("id") == job_id), None)
        if not job_info:
            return

        dlg = JobResultDialog(job_info, self)
        dlg.exec()
