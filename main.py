"""Simple TTS 入口。"""

from __future__ import annotations

import sys


def main() -> int:
    # Qt 自带 per-monitor DPI 处理，无需再像 Tk 那样手动声明感知级别
    from PySide6.QtWidgets import QApplication

    from simple_tts.app import App
    from simple_tts.ui import theme

    qt_app = QApplication(sys.argv)
    theme.apply(qt_app)

    window = App()
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
