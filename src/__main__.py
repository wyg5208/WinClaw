"""允许 python -m src 运行 WinClaw。

支持命令行参数：
    无参数或 --gui    启动 GUI 模式
    --cli              启动 CLI 模式（终端命令行）
"""

import sys


def main():
    # 检查命令行参数
    args = sys.argv[1:]

    if "--cli" in args:
        # CLI 模式
        from src.app import main as cli_main
        cli_main()
    else:
        # GUI 模式（默认）
        from src.ui.gui_app import main as gui_main
        gui_main()


if __name__ == "__main__":
    main()
