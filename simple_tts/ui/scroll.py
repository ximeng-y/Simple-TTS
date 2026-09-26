"""可纵向滚动的容器。

参数区内容比窗口高，必须能滚动查看；Tk 里做滚动区域只有 tk.Canvas 一个原语
（ttk 无对应控件），此处与 tk.Text 一样属于必要例外。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    """自身可纵向滚动的 Frame，内容放进 .body。"""

    def __init__(self, parent, padding=(0, 0, 0, 0)) -> None:
        super().__init__(parent)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, takefocus=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._canvas.configure(yscrollcommand=scrollbar.set)

        self.body = ttk.Frame(self._canvas, padding=padding)
        self._window = self._canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.body.bind("<Configure>", self._on_body_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        # 滚轮只在指针位于本区域时生效，避免抢走文本框的滚动
        self._canvas.bind("<Enter>", self._bind_wheel)
        self._canvas.bind("<Leave>", self._unbind_wheel)

    # ---------------------------------------------------------------- 内部

    def _on_body_configure(self, _event) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        # 让内容宽度跟随画布，否则内部控件不会换行、而是横向溢出
        self._canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, _event) -> None:
        self._canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _event) -> None:
        self._canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event) -> None:
        if self._canvas.bbox("all") is None:
            return
        first, last = self._canvas.yview()
        if first <= 0.0 and event.delta > 0:
            return
        if last >= 1.0 and event.delta < 0:
            return
        self._canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
