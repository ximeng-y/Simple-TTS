"""Simple TTS 入口。

高 DPI 需要在创建 Tk 窗口之前显式声明感知级别，否则界面会被系统拉伸模糊。
"""

from __future__ import annotations

import sys


def enable_dpi_awareness() -> None:
    """开启高 DPI 感知。

    优先使用 per-monitor v2（Win10 1703+），失败则退回系统级 DPI 感知（Win8.1+）；
    再失败就放弃 —— 界面仍可用，只是在高分屏上会被系统缩放。
    """
    if sys.platform != "win32":
        return

    import ctypes

    # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == -4
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass

    # PROCESS_SYSTEM_DPI_AWARE == 1
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except (AttributeError, OSError):
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def main() -> int:
    enable_dpi_awareness()

    from simple_tts.app import App

    App().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
