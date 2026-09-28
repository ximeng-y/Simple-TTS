"""Simple TTS 入口。"""

from __future__ import annotations

import os
import sys


def _icon_path() -> str:
    """图标文件路径：打包后随 datas 进 _internal/icons/，源码运行时在仓库根 icons/。"""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "icons", "icon.png")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "icon.png")


def main() -> int:
    # Qt 自带 per-monitor DPI 处理，无需再像 Tk 那样手动声明感知级别
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from simple_tts.app import App
    from simple_tts.ui import theme

    qt_app = QApplication(sys.argv)
    theme.apply(qt_app)

    # 应用级图标：主窗口与所有子对话框（设置/更新/消息框）统一继承。
    # 图标只在这里设一次，各窗口无需各自 setWindowIcon。
    qt_app.setWindowIcon(QIcon(_icon_path()))

    window = App()
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
