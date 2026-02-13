"""WinClaw UI 模块。

提供 PySide6 构建的图形用户界面。

模块结构：
- async_bridge: Qt + asyncio 事件循环桥接
- chat: 聊天界面组件（消息气泡、Markdown 渲染、流式输出）
- main_window: 主窗口（菜单栏、工具栏、聊天区、状态面板）
- gui_app: GUI 应用入口（Agent 集成、信号连接）

注意：导入本模块需要 PySide6 和 qasync 依赖。
如未安装，请执行: pip install PySide6 qasync
"""

from __future__ import annotations


def __getattr__(name: str):
    """懒导入：仅在实际访问时导入 PySide6 相关模块。"""
    _exports = {
        "AsyncBridge": ".async_bridge",
        "TaskRunner": ".async_bridge",
        "create_application": ".async_bridge",
        "setup_async_bridge": ".async_bridge",
        "ChatWidget": ".chat",
        "MessageBubble": ".chat",
        "MainWindow": ".main_window",
        "GuiAgent": ".gui_app",
        "WinClawGuiApp": ".gui_app",
        "gui_main": ".gui_app",
        "SystemTray": ".tray",
        "GlobalHotkey": ".hotkey",
        "SettingsDialog": ".settings_dialog",
        "Theme": ".theme",
        "apply_theme": ".theme",
    }

    module_path = _exports.get(name)
    if module_path is None:
        raise AttributeError(f"module 'src.ui' has no attribute '{name}'")

    import importlib

    try:
        mod = importlib.import_module(module_path, package=__name__)
    except ImportError as e:
        raise ImportError(
            f"无法导入 UI 模块 ({e})。"
            f"请安装 GUI 依赖: pip install PySide6 qasync"
        ) from e

    attr = name if name != "gui_main" else "main"
    return getattr(mod, attr)


__all__ = [
    "AsyncBridge",
    "TaskRunner",
    "create_application",
    "setup_async_bridge",
    "ChatWidget",
    "MessageBubble",
    "MainWindow",
    "GuiAgent",
    "WinClawGuiApp",
    "gui_main",
    "SystemTray",
    "GlobalHotkey",
    "SettingsDialog",
    "Theme",
    "apply_theme",
]
