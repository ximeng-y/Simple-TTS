"""主窗口。

装配顺序：Header -> 中栏（左文本 / 右配置）-> 风格辅助 -> 播放条。
各 UI 模块之间互不 import，全部通过本类的回调通信 —— 后续换成真实后端时
只需替换 App.on_synthesize 里的假进度，UI 模块无需改动。
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import __version__, catalog
from .player import AudioPlayer
from .state import AppState
from .ui import theme
from .ui.config_panel import ConfigPanel
from .ui.header import Header
from .ui.player_bar import PlayerBar
from .ui.settings_dialog import SettingsDialog
from .ui.style_panel import StylePanel
from .ui.text_panel import TextPanel

_WINDOW_TITLE = "Simple TTS"
_DEFAULT_GEOMETRY = "1100x880"
_MIN_SIZE = (1000, 760)
_RIGHT_COL_W = theme.RIGHT_COL_W


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.state = AppState()
        self.player = AudioPlayer()

        self.title(_WINDOW_TITLE)
        self.geometry(_DEFAULT_GEOMETRY)
        self.minsize(*_MIN_SIZE)

        theme.apply(ttk.Style(self))

        self._build_menu()
        self._build_layout()
        self._bind_shortcuts()
        self._load_model_into_ui()

    # ================================================================ 构建

    def _build_menu(self) -> None:
        # 菜单栏在 Tk 里只有经典 tk.Menu 这一个原语，ttk 无对应控件，此处属必要例外
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="设置…", accelerator="Ctrl+,", command=self.on_settings)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.destroy)
        menubar.add_cascade(label="文件", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="API 使用文档", command=self.on_open_docs)
        help_menu.add_command(label="关于", command=self.on_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        self.configure(menu=menubar)

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.header = Header(self, on_model_change=self.on_model_change)
        self.header.grid(row=0, column=0, sticky="ew")

        # 中栏：左文本弹性伸缩，右配置固定宽度
        middle = ttk.PanedWindow(self, orient="horizontal")
        middle.grid(row=1, column=0, sticky="nsew")

        self.text_panel = TextPanel(middle, on_text_change=self.on_text_change)
        self.config_panel = ConfigPanel(middle, self.state, on_sing_toggle=self.on_sing_from_config)

        middle.add(self.text_panel, weight=3)
        middle.add(self.config_panel, weight=0)

        self.style_panel = StylePanel(
            self,
            on_opening_style=self.on_opening_style,
            on_inline_tag=self.on_inline_tag,
            on_sing=self.on_sing_from_style_panel,
        )
        self.style_panel.grid(row=2, column=0, sticky="ew", padx=theme.PAD_L, pady=(0, theme.PAD))

        self.player_bar = PlayerBar(
            self,
            on_synthesize=self.on_synthesize,
            on_play=self.on_play,
            on_stop=self.on_stop,
            on_seek=self.on_seek,
            on_volume=self.on_volume,
        )
        self.player_bar.grid(row=3, column=0, sticky="ew")
        self.player_bar.set_busy(False)

        # 右列初始宽度按内容给足，避免长文案被压成两行
        self.after(0, lambda: self._init_sash(middle))

    def _init_sash(self, paned: ttk.PanedWindow) -> None:
        try:
            total = paned.winfo_width()
            paned.sashpos(0, max(total - _RIGHT_COL_W, 360))
        except tk.TclError:
            pass

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-Return>", lambda _e: self.on_synthesize())
        self.bind("<F5>", lambda _e: self.on_synthesize())
        self.bind("<Control-comma>", lambda _e: self.on_settings())

    # ================================================================ 模型联动

    def on_model_change(self, model_id: str) -> None:
        """顶部切换模型：先存旧草稿，再载入新模型的配置与文本。"""
        self._save_draft()
        self.state.model_id = model_id
        self._load_model_into_ui()

    def _load_model_into_ui(self) -> None:
        model = self.state.model
        draft = self.state.draft()

        self.config_panel.apply_model()
        self.text_panel.set_model(model)
        self.text_panel.set_style_prompt(draft.style_prompt)
        self.text_panel.set_text(draft.text)
        self._sync_sing_ui()

    def _save_draft(self) -> None:
        """把界面上的输入写回当前模型的草稿（仅内存）。"""
        draft = self.state.draft()
        draft.style_prompt = self.text_panel.get_style_prompt()
        draft.text = self.text_panel.get_text()
        self.config_panel.commit()

    # ================================================================ 文本与标签

    def on_text_change(self) -> None:
        """文本框内容变化：同步唱歌状态。草稿在切模型/合成时统一保存。"""
        self._sync_sing_ui()

    def on_opening_style(self, style: str) -> None:
        self.text_panel.apply_opening(style)
        self._sync_sing_ui()

    def on_inline_tag(self, tag: str) -> None:
        self.text_panel.insert_inline(tag)

    def on_sing_from_config(self, checked: bool) -> None:
        """右侧「唱歌模式」复选框被点击。"""
        self.text_panel.set_sing(checked)
        self._sync_sing_ui()

    def on_sing_from_style_panel(self, checked: bool) -> None:
        """风格辅助里的「唱歌」复选框被点击。"""
        self.text_panel.set_sing(checked)
        self._sync_sing_ui()

    def _sync_sing_ui(self) -> None:
        """两处唱歌入口与文本框内容保持一致。

        (唱歌) 是写在文本里的标签，用户也可能手输或删除，因此以文本内容为准回写控件。
        """
        singing = self.text_panel.is_singing()
        self.config_panel.set_sing(singing)
        self.style_panel.set_sing(singing)

    # ================================================================ 合成与播放

    def on_synthesize(self) -> None:
        """触发合成。

        本版本后端尚未接入：只走一遍假进度后复位，不落盘、不弹提示、不播放。
        接入后把这里的假进度换成 provider.synthesize(...) 即可。
        """
        self._save_draft()
        self.player.stop()
        self.player_bar.set_busy(True)
        self.player_bar.start_fake_progress(self._on_synthesize_done)

    def _on_synthesize_done(self) -> None:
        self.player_bar.set_busy(False)

    def on_play(self) -> None:
        self.player.play()

    def on_stop(self) -> None:
        self.player.stop()

    def on_seek(self, _value: str) -> None:
        self.player.seek(self.player_bar.seek_scale.get())

    def on_volume(self, value: str) -> None:
        self.player.set_volume(int(float(value)))

    # ================================================================ 菜单动作

    def on_settings(self) -> None:
        dialog = SettingsDialog(self, self.state)
        self.wait_window(dialog)
        if dialog.confirmed:
            self.config_panel.apply_settings()

    def on_open_docs(self) -> None:
        webbrowser.open(catalog.DOC_URL)

    def on_about(self) -> None:
        # messagebox 是 Tk 提供的原生对话框，无 ttk 对应实现
        messagebox.showinfo(
            "关于",
            f"Simple TTS v{__version__}\n\n"
            "轻量级 Windows 桌面文本转语音工具。\n"
            "当前为前端形态演示版本，后端尚未接入。",
            parent=self,
        )

    # ================================================================ 退出

    def destroy(self) -> None:
        self.player_bar.cancel()
        self.player.close()
        super().destroy()
