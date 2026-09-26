"""设置页。

本版本仅做前端形态演示，点「确定」只把值写回内存中的 AppState，不落盘；
重启后回到默认值。
"""

from __future__ import annotations

from tkinter import filedialog, ttk
import tkinter as tk

from .. import catalog
from . import theme

_NOTE = "本版本仅前端形态演示，配置只保存在内存中，不会写入磁盘。"


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, state) -> None:
        super().__init__(parent)
        self._state = state
        self._confirmed = False

        self.title("设置")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew", padx=theme.PAD_L, pady=theme.PAD)
        notebook.add(self._build_api_page(notebook), text="  API  ")
        notebook.add(self._build_general_page(notebook), text="  通用  ")

        ttk.Label(self, text=_NOTE, style="Hint.TLabel").grid(
            row=1, column=0, sticky="w", padx=theme.PAD_L
        )

        buttons = ttk.Frame(self, padding=(theme.PAD_L, theme.PAD, theme.PAD_L, theme.PAD))
        buttons.grid(row=2, column=0, sticky="e")
        ttk.Button(buttons, text="确定", command=self._confirm, width=10).grid(row=0, column=0)
        ttk.Button(buttons, text="取消", command=self.destroy, width=10).grid(
            row=0, column=1, padx=(theme.GAP, 0)
        )

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._load()
        self._center_on(parent)

    # ================================================================ 页面

    def _build_api_page(self, parent) -> ttk.Frame:
        page = ttk.Frame(parent, padding=theme.PAD_L)
        page.columnconfigure(1, weight=1)

        ttk.Label(page, text="API Base URL", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self._base_var = tk.StringVar()
        ttk.Entry(page, textvariable=self._base_var, width=46).grid(
            row=0, column=1, sticky="ew", padx=(theme.PAD, 0)
        )
        ttk.Label(page, text="OpenAI Chat Completions 风格接口，例如 https://api.xiaomimimo.com/v1",
                  style="Hint.TLabel").grid(row=1, column=1, sticky="w", padx=(theme.PAD, 0), pady=(2, theme.PAD))

        ttk.Label(page, text="API Key", style="Title.TLabel").grid(row=2, column=0, sticky="w")
        key_row = ttk.Frame(page)
        key_row.grid(row=2, column=1, sticky="ew", padx=(theme.PAD, 0))
        key_row.columnconfigure(0, weight=1)
        self._key_var = tk.StringVar()
        self._key_entry = ttk.Entry(key_row, textvariable=self._key_var, show="*")
        self._key_entry.grid(row=0, column=0, sticky="ew")
        self._show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            key_row, text="显示", variable=self._show_key_var, command=self._toggle_key
        ).grid(row=0, column=1, padx=(theme.GAP, 0))

        ttk.Label(page, text="仅保存在本次运行的内存中", style="Hint.TLabel").grid(
            row=3, column=1, sticky="w", padx=(theme.PAD, 0), pady=(2, 0)
        )
        return page

    def _build_general_page(self, parent) -> ttk.Frame:
        page = ttk.Frame(parent, padding=theme.PAD_L)
        page.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(page, text="默认保存目录", style="Title.TLabel").grid(row=row, column=0, sticky="w")
        self._dir_var = tk.StringVar()
        dir_row = ttk.Frame(page)
        dir_row.grid(row=row, column=1, sticky="ew", padx=(theme.PAD, 0))
        dir_row.columnconfigure(0, weight=1)
        ttk.Entry(dir_row, textvariable=self._dir_var, width=40).grid(row=0, column=0, sticky="ew")
        ttk.Button(dir_row, text="浏览…", command=self._pick_dir, width=8).grid(
            row=0, column=1, padx=(theme.GAP, 0)
        )
        row += 1

        ttk.Label(page, text="默认音频格式", style="Title.TLabel").grid(
            row=row, column=0, sticky="w", pady=(theme.PAD, 0)
        )
        self._format_var = tk.StringVar()
        formats = ttk.Frame(page)
        formats.grid(row=row, column=1, sticky="w", padx=(theme.PAD, 0), pady=(theme.PAD, 0))
        for index, (fmt_id, label, _note) in enumerate(catalog.FORMATS):
            ttk.Radiobutton(formats, text=label, value=fmt_id, variable=self._format_var).grid(
                row=0, column=index, padx=(0, theme.PAD)
            )
        row += 1

        self._autoplay_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(page, text="合成后自动试听", variable=self._autoplay_var).grid(
            row=row, column=1, sticky="w", padx=(theme.PAD, 0), pady=(theme.GAP, 0)
        )
        row += 1

        self._history_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(page, text="保留合成历史记录", variable=self._history_var).grid(
            row=row, column=1, sticky="w", padx=(theme.PAD, 0)
        )
        row += 1

        self._overwrite_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(page, text="覆盖同名文件前确认", variable=self._overwrite_var).grid(
            row=row, column=1, sticky="w", padx=(theme.PAD, 0)
        )
        return page

    # ================================================================ 数据

    def _load(self) -> None:
        self._base_var.set(self._state.api_base)
        self._key_var.set(self._state.api_key)
        self._dir_var.set(self._state.output_dir)
        self._format_var.set(self._state.audio_format)
        self._autoplay_var.set(self._state.auto_play)
        self._history_var.set(self._state.keep_history)
        self._overwrite_var.set(self._state.confirm_overwrite)

    def _confirm(self) -> None:
        state = self._state
        state.api_base = self._base_var.get().strip() or catalog.DEFAULT_API_BASE
        state.api_key = self._key_var.get()
        state.output_dir = self._dir_var.get()
        state.audio_format = self._format_var.get() or "wav"
        state.auto_play = self._autoplay_var.get()
        state.keep_history = self._history_var.get()
        state.confirm_overwrite = self._overwrite_var.get()
        self._confirmed = True
        self.destroy()

    @property
    def confirmed(self) -> bool:
        return self._confirmed

    # ================================================================ 内部

    def _toggle_key(self) -> None:
        self._key_entry.configure(show="" if self._show_key_var.get() else "*")

    def _pick_dir(self) -> None:
        path = filedialog.askdirectory(
            parent=self, title="选择默认保存目录", initialdir=self._dir_var.get() or None
        )
        if path:
            self._dir_var.set(path)

    def _center_on(self, parent) -> None:
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
