"""更新对话框 — 显示新版本信息和下载进度。

功能:
1. 显示新版本信息和更新日志
2. 下载进度条
3. 立即更新/稍后提醒按钮
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src.updater.github_updater import UpdateInfo

logger = logging.getLogger(__name__)


class DownloadThread(QThread):
    """下载线程。"""
    
    progress_updated = Signal(int, int)  # (downloaded, total)
    download_completed = Signal(str)  # file_path
    download_failed = Signal(str)  # error_message
    
    def __init__(
        self,
        download_url: str,
        target_dir: Path | str | None = None,
        parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.download_url = download_url
        self.target_dir = target_dir
        self._cancelled = False
    
    def run(self) -> None:
        """执行下载。"""
        import asyncio
        
        async def download():
            try:
                from src.updater.github_updater import GitHubUpdater, UpdateInfo
                
                # 创建临时 UpdateInfo
                update_info = UpdateInfo(
                    version="",
                    release_url="",
                    download_url=self.download_url,
                    download_size=0,
                    release_notes="",
                    published_at="",
                )
                
                async with GitHubUpdater() as updater:
                    file_path = await updater.download_update(
                        update_info,
                        self.target_dir,
                        progress_callback=lambda d, t: self.progress_updated.emit(d, t),
                    )
                    
                    if file_path and not self._cancelled:
                        self.download_completed.emit(str(file_path))
                    elif not self._cancelled:
                        self.download_failed.emit("下载失败")
            
            except Exception as e:
                if not self._cancelled:
                    self.download_failed.emit(str(e))
        
        # 运行异步下载
        asyncio.run(download())
    
    def cancel(self) -> None:
        """取消下载。"""
        self._cancelled = True


class UpdateDialog(QDialog):
    """更新对话框。"""
    
    # 信号
    update_now_requested = Signal()
    remind_later_requested = Signal()
    
    def __init__(
        self,
        update_info: UpdateInfo,
        current_version: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._update_info = update_info
        self._current_version = current_version
        self._download_thread: DownloadThread | None = None
        self._downloaded_file: str | None = None
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """初始化界面。"""
        self.setWindowTitle("发现新版本")
        self.setMinimumSize(500, 400)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # 版本信息
        version_layout = QHBoxLayout()
        
        current_label = QLabel(f"当前版本: <b>{self._current_version}</b>")
        version_layout.addWidget(current_label)
        
        version_layout.addStretch()
        
        new_label = QLabel(f"新版本: <b style='color: #4CAF50;'>{self._update_info.version}</b>")
        version_layout.addWidget(new_label)
        
        layout.addLayout(version_layout)
        
        # 发布日期
        if self._update_info.published_at:
            date_str = self._update_info.published_at[:10]  # 取日期部分
            date_label = QLabel(f"发布日期: {date_str}")
            date_label.setStyleSheet("color: #666;")
            layout.addWidget(date_label)
        
        # 更新日志
        notes_label = QLabel("更新内容:")
        notes_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(notes_label)
        
        self._notes_browser = QTextBrowser()
        self._notes_browser.setOpenExternalLinks(True)
        self._notes_browser.setMarkdown(self._update_info.release_notes or "暂无更新说明")
        layout.addWidget(self._notes_browser, stretch=1)
        
        # 下载进度
        self._progress_widget = QWidget()
        progress_layout = QVBoxLayout(self._progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        
        self._progress_label = QLabel("正在下载...")
        progress_layout.addWidget(self._progress_label)
        
        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        progress_layout.addWidget(self._progress_bar)
        
        self._progress_widget.setVisible(False)
        layout.addWidget(self._progress_widget)
        
        # 下载大小
        if self._update_info.download_size > 0:
            size_mb = self._update_info.download_size / (1024 * 1024)
            size_label = QLabel(f"下载大小: {size_mb:.1f} MB")
            size_label.setStyleSheet("color: #666;")
            layout.addWidget(size_label)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self._later_btn = QPushButton("稍后提醒")
        self._later_btn.clicked.connect(self._on_remind_later)
        button_layout.addWidget(self._later_btn)
        
        self._update_btn = QPushButton("立即更新")
        self._update_btn.setDefault(True)
        self._update_btn.clicked.connect(self._on_update_now)
        button_layout.addWidget(self._update_btn)
        
        layout.addLayout(button_layout)
    
    def _on_update_now(self) -> None:
        """处理立即更新。"""
        if self._downloaded_file:
            # 已下载完成,执行安装
            self._install_update()
            return
        
        if not self._update_info.download_url:
            QMessageBox.warning(self, "错误", "没有可用的下载链接")
            return
        
        # 开始下载
        self._start_download()
    
    def _start_download(self) -> None:
        """开始下载。"""
        self._update_btn.setEnabled(False)
        self._later_btn.setEnabled(False)
        self._progress_widget.setVisible(True)
        
        self._download_thread = DownloadThread(self._update_info.download_url, parent=self)
        self._download_thread.progress_updated.connect(self._on_progress)
        self._download_thread.download_completed.connect(self._on_download_completed)
        self._download_thread.download_failed.connect(self._on_download_failed)
        self._download_thread.start()
    
    def _on_progress(self, downloaded: int, total: int) -> None:
        """更新下载进度。"""
        if total > 0:
            percent = int(downloaded * 100 / total)
            self._progress_bar.setValue(percent)
            
            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            self._progress_label.setText(f"正在下载... {downloaded_mb:.1f} / {total_mb:.1f} MB")
        else:
            downloaded_mb = downloaded / (1024 * 1024)
            self._progress_label.setText(f"正在下载... {downloaded_mb:.1f} MB")
    
    def _on_download_completed(self, file_path: str) -> None:
        """下载完成。"""
        self._downloaded_file = file_path
        self._progress_label.setText("下载完成!")
        self._progress_bar.setValue(100)
        
        # 验证校验和
        if self._update_info.sha256:
            from src.updater.github_updater import GitHubUpdater
            updater = GitHubUpdater()
            if not updater.verify_checksum(file_path, self._update_info.sha256):
                QMessageBox.warning(self, "校验失败", "文件校验失败,可能已损坏。请重新下载。")
                self._downloaded_file = None
                self._update_btn.setEnabled(True)
                self._later_btn.setEnabled(True)
                return
        
        self._update_btn.setText("安装更新")
        self._update_btn.setEnabled(True)
        self._later_btn.setEnabled(True)
    
    def _on_download_failed(self, error: str) -> None:
        """下载失败。"""
        self._progress_label.setText(f"下载失败: {error}")
        self._progress_widget.setVisible(False)
        
        QMessageBox.warning(self, "下载失败", f"下载更新失败:\n{error}")
        
        self._update_btn.setEnabled(True)
        self._later_btn.setEnabled(True)
    
    def _install_update(self) -> None:
        """安装更新。"""
        if not self._downloaded_file:
            return
        
        file_path = Path(self._downloaded_file)
        
        # 询问确认
        reply = QMessageBox.question(
            self,
            "安装更新",
            "即将关闭应用程序并安装更新。\n\n确定要继续吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            if file_path.suffix.lower() == ".exe":
                # 启动安装程序
                subprocess.Popen([str(file_path)], shell=True)
            else:
                # 打开文件所在目录
                subprocess.Popen(["explorer", "/select,", str(file_path)])
            
            # 退出应用
            self.accept()
            sys.exit(0)
        
        except Exception as e:
            QMessageBox.warning(self, "安装失败", f"启动安装程序失败:\n{e}")
    
    def _on_remind_later(self) -> None:
        """稍后提醒。"""
        self.remind_later_requested.emit()
        self.reject()
    
    def closeEvent(self, event) -> None:
        """关闭事件。"""
        if self._download_thread and self._download_thread.isRunning():
            self._download_thread.cancel()
            self._download_thread.wait()
        super().closeEvent(event)


def show_update_dialog(
    update_info: UpdateInfo,
    current_version: str,
    parent: QWidget | None = None,
) -> bool:
    """显示更新对话框。
    
    Args:
        update_info: 更新信息
        current_version: 当前版本
        parent: 父窗口
        
    Returns:
        用户是否选择更新
    """
    dialog = UpdateDialog(update_info, current_version, parent)
    return dialog.exec() == QDialog.DialogCode.Accepted
