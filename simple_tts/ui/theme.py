"""界面外观：字体探测与间距常量。

中文界面若落到不含中文字形的字体上会显示成方框，因此显式挑一个系统中文字体，
并通过 ttk.Style().configure(".") 统一应用。
"""

from __future__ import annotations

import tkinter.font as tkfont
from tkinter import ttk

# 间距常量，避免各控件各写各的魔法数字
PAD = 8
PAD_L = 12
GAP = 6
RIGHT_COL_W = 320

# 依次尝试，取第一个系统里存在的
_PREFERRED_FONTS = ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Tahoma")


def pick_font() -> str:
    """返回系统中可用的首选中文字体族名。"""
    available = set(tkfont.families())
    for family in _PREFERRED_FONTS:
        if family in available:
            return family
    return "TkDefaultFont"


def apply(style: ttk.Style) -> None:
    """选定主题并统一字体。需在创建控件之前调用。"""
    # vista 主题调用 Windows 原生 Visual Styles 渲染，外观跟随系统
    if "vista" in style.theme_names():
        style.theme_use("vista")

    family = pick_font()
    style.configure(".", font=(family, 9))
    style.configure("Hint.TLabel", foreground="#666666")
    style.configure("Title.TLabel", font=(family, 9, "bold"))
    style.configure("Heading.TLabel", font=(family, 10, "bold"))
