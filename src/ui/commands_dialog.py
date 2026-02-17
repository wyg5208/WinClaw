"""命令选择对话框 - 标签平铺式显示所有命令"""

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QWidget,
    QScrollArea,
    QGridLayout,
    QLineEdit,
)
from PySide6.QtGui import QFont


class CommandsDialog(QDialog):
    """命令选择对话框 - 标签平铺式显示所有命令"""

    # 当用户选择一个命令时发出信号
    command_selected = Signal(str)

    def __init__(self, parent=None, title: str = "选择命令", category_data: dict = None):
        super().__init__(parent)
        self._category_data = category_data
        self._setup_ui(title)

    def _setup_ui(self, title: str) -> None:
        """设置UI"""
        self.setWindowTitle(f"选择{title}")
        self.setMinimumSize(1000, 500)
        self.resize(1100, 600)

        # 主布局
        main_layout = QVBoxLayout(self)

        # 标题行
        header_layout = QHBoxLayout()
        title_label = QLabel(f"📋 {title}")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)

        # 搜索框
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("搜索命令...")
        self._search_box.textChanged.connect(self._on_search_changed)
        self._search_box.setMaximumWidth(300)
        header_layout.addWidget(self._search_box)

        main_layout.addLayout(header_layout)

        # 标签平铺式命令区域
        self._tab_widget = QTabWidget()

        # 添加"全部"标签
        all_widget = self._create_all_commands_tab()
        self._tab_widget.addTab(all_widget, "📂 全部")

        # 为每个分类创建标签页
        if self._category_data:
            subgroups = self._category_data.get("subgroups", {})
            for subgroup_key, subgroup_data in subgroups.items():
                emoji = subgroup_data.get("emoji", "📁")
                tab_widget = self._create_commands_grid(subgroup_data.get("commands", []))
                self._tab_widget.addTab(tab_widget, f"{emoji} {subgroup_data.get('name', subgroup_key)}")

        main_layout.addWidget(self._tab_widget)

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        main_layout.addLayout(button_layout)

    def _create_all_commands_tab(self) -> QWidget:
        """创建全部命令标签页"""
        all_commands = []

        if self._category_data:
            subgroups = self._category_data.get("subgroups", {})
            for subgroup_key, subgroup_data in subgroups.items():
                all_commands.extend(subgroup_data.get("commands", []))

        return self._create_commands_grid(all_commands)

    def _create_commands_grid(self, commands: list) -> QWidget:
        """创建命令网格布局"""
        widget = QWidget()

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # 使用整数值兼容不同 PySide6 版本
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # 网格布局
        grid_layout = QGridLayout()
        grid_layout.setSpacing(8)

        # 每行显示命令，宽度足够
        for i, cmd in enumerate(commands):
            row = i // 2  # 每行2个
            col = i % 2

            btn = QPushButton(cmd)
            btn.setToolTip(cmd)
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(450)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 5px 10px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #0078d4;
                    color: white;
                }
            """)
            btn.clicked.connect(lambda checked, c=cmd: self._on_command_clicked(c))

            grid_layout.addWidget(btn, row, col)

        widget.setLayout(grid_layout)
        scroll.setWidget(widget)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(scroll)

        return container

    def _on_command_clicked(self, command: str) -> None:
        """命令按钮点击"""
        self.command_selected.emit(command)
        self.accept()

    def _on_search_changed(self, text: str) -> None:
        """搜索框文本改变"""
        text = text.lower().strip()

        # 遍历所有标签页进行搜索
        for i in range(self._tab_widget.count()):
            tab = self._tab_widget.widget(i)
            if tab is None:
                continue

            # 查找该标签页中的所有按钮
            buttons = tab.findChildren(QPushButton)
            for btn in buttons:
                cmd = btn.text()
                if text and text in cmd.lower():
                    btn.setVisible(True)
                elif text:
                    btn.setVisible(False)
                else:
                    btn.setVisible(True)
