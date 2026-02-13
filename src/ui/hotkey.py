"""全局快捷键监听。

使用 pynput 监听全局键盘快捷键（默认 Win+Shift+Space），
在任何时候按快捷键都能快速唤起/隐藏 WinClaw 主窗口。

功能：
- 后台线程监听键盘
- 可自定义快捷键组合
- 线程安全：通过 Qt 信号通知 UI 线程
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 默认快捷键
DEFAULT_HOTKEY = "<cmd>+<shift>+space"


class GlobalHotkey(QObject):
    """全局快捷键管理器。"""

    # 信号：在 UI 线程中触发
    triggered = Signal()

    def __init__(self, hotkey: str = DEFAULT_HOTKEY) -> None:
        super().__init__()
        self._hotkey = hotkey
        self._listener_thread: threading.Thread | None = None
        self._hotkey_listener: object | None = None
        self._running = False

    def start(self) -> None:
        """启动全局快捷键监听（后台线程）。"""
        if self._running:
            return

        self._running = True
        self._listener_thread = threading.Thread(
            target=self._run_listener,
            daemon=True,
            name="WinClaw-Hotkey",
        )
        self._listener_thread.start()
        logger.info("全局快捷键已启动: %s", self._hotkey)

    def stop(self) -> None:
        """停止监听。"""
        self._running = False
        if self._hotkey_listener is not None:
            try:
                self._hotkey_listener.stop()  # type: ignore
            except Exception:
                pass
        self._hotkey_listener = None
        logger.info("全局快捷键已停止")

    def set_hotkey(self, hotkey: str) -> None:
        """更新快捷键（需要重启监听器）。"""
        was_running = self._running
        if was_running:
            self.stop()
        self._hotkey = hotkey
        if was_running:
            self.start()

    @property
    def hotkey(self) -> str:
        return self._hotkey

    def _run_listener(self) -> None:
        """在后台线程中运行 pynput 监听器。"""
        try:
            from pynput import keyboard

            def on_activate() -> None:
                """快捷键被触发。"""
                logger.debug("全局快捷键触发")
                # 通过 Qt 信号通知 UI 线程
                self.triggered.emit()

            hotkey_set = keyboard.HotKey(
                keyboard.HotKey.parse(self._hotkey),
                on_activate,
            )

            def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> None:
                try:
                    hotkey_set.press(key)  # type: ignore
                except Exception:
                    pass

            def on_release(key: keyboard.Key | keyboard.KeyCode | None) -> None:
                try:
                    hotkey_set.release(key)  # type: ignore
                except Exception:
                    pass

            with keyboard.Listener(
                on_press=on_press,
                on_release=on_release,
            ) as listener:
                self._hotkey_listener = listener
                listener.join()

        except ImportError:
            logger.warning("pynput 未安装，全局快捷键不可用")
        except Exception as e:
            logger.error("全局快捷键监听异常: %s", e)
        finally:
            self._running = False
