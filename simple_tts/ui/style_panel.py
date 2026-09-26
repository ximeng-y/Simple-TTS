"""风格辅助面板：可直接点选的风格标签与音频标签。

对应文档里的两种标签控制方式：
  - 开头风格标签 (风格1 风格2)正文 -> 写入合成文本最前面
  - 行内音频标签 [标签]            -> 插入到合成文本的光标处

本面板不持有文本框，只通过构造时传入的回调通知 App，由 App 转交给 TextPanel 执行，
避免 UI 模块之间互相依赖。
"""

from __future__ import annotations

from tkinter import ttk
import tkinter as tk

from .. import catalog
from . import theme

# 每组最多 9 个按钮排成一行，超出的换行
_COLUMNS = 9
_BUTTON_WIDTH = 9
_LABEL_WIDTH = 9


class StylePanel(ttk.LabelFrame):
    def __init__(self, parent, on_opening_style, on_inline_tag, on_sing) -> None:
        super().__init__(parent, text=" 风格辅助 ", padding=(theme.PAD_L, theme.PAD, theme.PAD_L, theme.PAD))
        self._on_opening_style = on_opening_style
        self._on_inline_tag = on_inline_tag
        self._on_sing = on_sing

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew")
        notebook.add(self._build_opening_page(notebook), text="  开头风格  ")
        notebook.add(self._build_inline_page(notebook), text="  行内标签  ")

    # ================================================================ 开头风格

    def _build_opening_page(self, parent) -> ttk.Frame:
        page = ttk.Frame(parent, padding=theme.PAD)
        page.columnconfigure(0, weight=1)

        ttk.Label(
            page,
            text="点击后写入合成文本最开头，形如 (风格1 风格2)正文；再次点击同一项即移除。",
            style="Hint.TLabel",
        ).grid(row=0, column=0, columnspan=1 + _COLUMNS, sticky="w", pady=(0, theme.GAP))

        row = 1

        # 唱歌单独一行：它必须独占文本最开头，不能与其它风格共存
        sing_cell = ttk.Frame(page)
        sing_cell.grid(row=row, column=0, columnspan=1 + _COLUMNS, sticky="ew")
        self._sing_var = tk.BooleanVar(value=False)
        self._sing_check = ttk.Checkbutton(
            sing_cell,
            text="唱歌",
            variable=self._sing_var,
            command=self._handle_sing,
            width=_BUTTON_WIDTH,
        )
        self._sing_check.grid(row=0, column=0, sticky="w")
        ttk.Label(
            sing_cell,
            text="必须在目标文本最开头，且不能与其它风格共存；歌词建议使用中文。",
            style="Hint.TLabel",
        ).grid(row=0, column=1, sticky="w", padx=(theme.PAD, 0))
        row += 1

        for group_name, styles in catalog.OPENING_STYLES:
            self._fill_row(page, row, group_name, styles, self._on_opening_style)
            row += 1

        return page

    # ================================================================ 行内标签

    def _build_inline_page(self, parent) -> ttk.Frame:
        page = ttk.Frame(parent, padding=theme.PAD)
        page.columnconfigure(0, weight=1)

        ttk.Label(
            page,
            text="点击后插入到合成文本的光标位置，形如 [哽咽]；可对语气、情绪做细粒度控制。",
            style="Hint.TLabel",
        ).grid(row=0, column=0, columnspan=1 + _COLUMNS, sticky="w", pady=(0, theme.GAP))

        row = 1
        for group_name, tags in catalog.INLINE_TAGS:
            self._fill_row(page, row, group_name, tags, self._on_inline_tag)
            row += 1

        return page

    # ================================================================ 对外

    def set_sing(self, checked: bool) -> None:
        """由 App 反向同步（例如用户在文本框里手动删掉了 (唱歌) 标签）。"""
        self._sing_var.set(checked)

    # ================================================================ 内部

    def _fill_row(self, page: ttk.Frame, row: int, group_name: str, items: list[str], command) -> None:
        """一组标签占一行：最左是组名，右侧平铺按钮。"""
        ttk.Label(page, text=group_name, style="Hint.TLabel", width=_LABEL_WIDTH, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(0, theme.GAP), pady=1
        )
        for index, item in enumerate(items):
            ttk.Button(
                page,
                text=item,
                width=_BUTTON_WIDTH,
                command=lambda value=item: command(value),
            ).grid(
                row=row + index // _COLUMNS,
                column=1 + index % _COLUMNS,
                sticky="ew",
                padx=1,
                pady=1,
            )

    def _handle_sing(self) -> None:
        self._on_sing(self._sing_var.get())
