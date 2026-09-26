"""右侧配置区：音色 + 输出。

「音色」区的三块内容互斥，随顶部所选模型切换（预置音色 / 音色设计 / 音色复刻）。
为了不引入 Notebook 那样的视觉噪音，三块都放在同一个 grid 单元里，用 grid_remove 切换。
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, ttk

from .. import catalog
from . import theme
from .scroll import ScrollableFrame


class ConfigPanel(ScrollableFrame):
    """参数区，内容超出窗口高度时可纵向滚动。

    与 App 的约定：
      - on_sing_toggle(checked) 唱歌模式勾选变化时回调，由 App 去改文本框内容
      - commit() 把控件值写回 state；apply_model() 把 state 读进控件
    """

    def __init__(self, parent, state, on_sing_toggle) -> None:
        super().__init__(parent, padding=(theme.PAD_L, theme.PAD, theme.PAD, theme.PAD))
        self._state = state
        self._on_sing_toggle = on_sing_toggle

        # 后续控件一律挂到可滚动内容的 body 上
        root = self.body
        root.columnconfigure(0, weight=1)

        self._build_voice_section(root)
        self._build_output_section(root)

        # 音色区随可用高度伸展
        root.rowconfigure(0, weight=1)

    # ================================================================ 构建

    def _build_voice_section(self, root: ttk.Frame) -> None:
        section = ttk.LabelFrame(root, text=" 音色 ", padding=theme.PAD)
        section.grid(row=0, column=0, sticky="nsew")
        section.columnconfigure(0, weight=1)
        section.rowconfigure(0, weight=1)

        # 三个块共用一个单元，靠 grid_remove 显示/隐藏
        self._blocks: dict[str, ttk.Frame] = {}
        for key in ("preset", "design", "clone"):
            block = ttk.Frame(section)
            block.grid(row=0, column=0, sticky="nsew")
            block.columnconfigure(0, weight=1)
            self._blocks[key] = block

        self._build_preset_block(self._blocks["preset"])
        self._build_design_block(self._blocks["design"])
        self._build_clone_block(self._blocks["clone"])

    def _build_preset_block(self, block: ttk.Frame) -> None:
        ttk.Label(block, text="预置音色", style="Title.TLabel").grid(row=0, column=0, sticky="w")

        self._voice_box = ttk.Combobox(block, state="readonly", values=[])
        self._voice_box.grid(row=1, column=0, sticky="ew", pady=(theme.GAP, 2))
        self._voice_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_voice_hint())

        self._voice_hint = ttk.Label(block, style="Hint.TLabel", wraplength=theme.RIGHT_COL_W - 40)
        self._voice_hint.grid(row=2, column=0, sticky="w", pady=(0, theme.GAP))

        self._sing_var = tk.BooleanVar(value=False)
        self._sing_check = ttk.Checkbutton(
            block,
            text="唱歌模式",
            variable=self._sing_var,
            command=self._handle_sing,
        )
        self._sing_check.grid(row=3, column=0, sticky="w")

        ttk.Label(
            block,
            text="勾选后会在合成文本开头添加 (唱歌) 标签；歌词建议使用中文。",
            style="Hint.TLabel",
            wraplength=theme.RIGHT_COL_W - 40,
            justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(2, 0))

    def _build_design_block(self, block: ttk.Frame) -> None:
        ttk.Label(block, text="音色由描述生成", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            block,
            text="在左侧「音色描述」中写一段文字描述想要的音色，无需提供音频样本。",
            style="Hint.TLabel",
            wraplength=theme.RIGHT_COL_W - 40,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(theme.GAP, theme.PAD))

        ttk.Label(block, text="可参考的维度", style="Title.TLabel").grid(row=2, column=0, sticky="w")
        for index, hint in enumerate(catalog.VOICE_DESC_HINTS):
            ttk.Label(
                block,
                text=f"· {hint}",
                style="Hint.TLabel",
                wraplength=theme.RIGHT_COL_W - 40,
                justify="left",
            ).grid(row=3 + index, column=0, sticky="w")

        row = 3 + len(catalog.VOICE_DESC_HINTS) + 1
        self._optimize_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            block,
            text="文本智能润色",
            variable=self._optimize_var,
        ).grid(row=row, column=0, sticky="w", pady=(theme.PAD, 0))
        ttk.Label(
            block,
            text="对应请求参数 audio.optimize_text_preview；开启时可省略合成文本，"
            "由服务端根据需要播报的内容智能润色。",
            style="Hint.TLabel",
            wraplength=theme.RIGHT_COL_W - 40,
            justify="left",
        ).grid(row=row + 1, column=0, sticky="w", pady=(2, 0))

    def _build_clone_block(self, block: ttk.Frame) -> None:
        ttk.Label(block, text="音频样本", style="Title.TLabel").grid(row=0, column=0, sticky="w")

        picker = ttk.Frame(block)
        picker.grid(row=1, column=0, sticky="ew", pady=(theme.GAP, 2))
        picker.columnconfigure(0, weight=1)

        self._sample_var = tk.StringVar()
        ttk.Entry(picker, textvariable=self._sample_var, state="readonly").grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(picker, text="选择样本…", command=self._pick_sample, width=11).grid(
            row=0, column=1, padx=(theme.GAP, 0)
        )

        self._sample_hint = ttk.Label(block, style="Hint.TLabel", wraplength=theme.RIGHT_COL_W - 40)
        self._sample_hint.grid(row=2, column=0, sticky="w")

        ttk.Label(
            block,
            text="样本会被编码成 data:audio/{MIME};base64,… 传给 audio.voice，"
            "Base64 后不得超过 10MB，仅支持 mp3 与 wav。",
            style="Hint.TLabel",
            wraplength=theme.RIGHT_COL_W - 40,
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(theme.GAP, 0))

    def _build_output_section(self, root: ttk.Frame) -> None:
        section = ttk.LabelFrame(root, text=" 输出 ", padding=theme.PAD)
        section.grid(row=1, column=0, sticky="ew", pady=(theme.PAD, 0))
        section.columnconfigure(0, weight=1)
        row = 0

        ttk.Label(section, text="音频格式", style="Title.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        self._format_var = tk.StringVar()
        for fmt_id, label, note in catalog.FORMATS:
            ttk.Radiobutton(
                section,
                text=label,
                value=fmt_id,
                variable=self._format_var,
            ).grid(row=row, column=0, sticky="w")
            row += 1
            ttk.Label(
                section,
                text=note,
                style="Hint.TLabel",
                wraplength=theme.RIGHT_COL_W - 60,
                justify="left",
            ).grid(row=row, column=0, sticky="w", padx=(20, 0), pady=(0, 2))
            row += 1

        ttk.Separator(section, orient="horizontal").grid(
            row=row, column=0, sticky="ew", pady=theme.GAP
        )
        row += 1

        ttk.Label(section, text="保存目录", style="Title.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        dir_row = ttk.Frame(section)
        dir_row.grid(row=row, column=0, sticky="ew")
        dir_row.columnconfigure(0, weight=1)
        self._dir_var = tk.StringVar()
        ttk.Entry(dir_row, textvariable=self._dir_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(dir_row, text="浏览…", command=self._pick_dir, width=8).grid(
            row=0, column=1, padx=(theme.GAP, 0)
        )
        row += 1

        ttk.Label(section, text="文件名模式", style="Title.TLabel").grid(
            row=row, column=0, sticky="w", pady=(theme.GAP, 0)
        )
        row += 1
        self._pattern_var = tk.StringVar()
        ttk.Entry(section, textvariable=self._pattern_var).grid(row=row, column=0, sticky="ew")
        row += 1
        ttk.Label(
            section,
            text="可用变量：{ts} 时间戳、{voice} 音色、{model} 模型、{index} 序号",
            style="Hint.TLabel",
            wraplength=theme.RIGHT_COL_W - 40,
            justify="left",
        ).grid(row=row, column=0, sticky="w")
        row += 1

        self._autoplay_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(section, text="合成后自动试听", variable=self._autoplay_var).grid(
            row=row, column=0, sticky="w", pady=(theme.GAP, 0)
        )

    # ================================================================ 对外

    def apply_model(self) -> None:
        """把 state 中当前模型的配置读进控件，并切换到对应的音色块。"""
        model = self._state.model
        draft = self._state.draft()

        for key, block in self._blocks.items():
            if key == model["tone_source"]:
                block.grid()
            else:
                block.grid_remove()

        if model["tone_source"] == "preset":
            self._voice_box.configure(values=[catalog.voice_label(v) for v in catalog.PRESET_VOICES])
            index = next(
                (
                    i
                    for i, voice in enumerate(catalog.PRESET_VOICES)
                    if voice["voice_id"] == draft.voice_id
                ),
                0,
            )
            self._voice_box.current(index)
            self._refresh_voice_hint()
            self._sing_var.set(draft.sing)

        if model["tone_source"] == "design":
            self._optimize_var.set(draft.optimize_preview)

        if model["tone_source"] == "clone":
            self._sample_var.set(draft.sample_path)
            self._refresh_sample_hint()

        self._format_var.set(self._state.audio_format)
        self._dir_var.set(self._state.output_dir)
        self._pattern_var.set(self._state.filename_pattern)
        self._autoplay_var.set(self._state.auto_play)

    def apply_settings(self) -> None:
        """设置页确认后，把与设置页重叠的项同步到控件。"""
        self._format_var.set(self._state.audio_format)
        self._dir_var.set(self._state.output_dir)
        self._autoplay_var.set(self._state.auto_play)

    def commit(self) -> None:
        """把控件值写回 state（仅内存）。切模型前与点合成前调用。"""
        draft = self._state.draft()
        model = self._state.model

        if model["tone_source"] == "preset":
            draft.voice_id = catalog.PRESET_VOICES[self._voice_box.current()]["voice_id"]
            draft.sing = self._sing_var.get()
        if model["tone_source"] == "design":
            draft.optimize_preview = self._optimize_var.get()

        if model["tone_source"] == "clone":
            draft.sample_path = self._sample_var.get()

        self._state.audio_format = self._format_var.get() or "wav"
        self._state.output_dir = self._dir_var.get()
        self._state.filename_pattern = self._pattern_var.get()
        self._state.auto_play = self._autoplay_var.get()

    def set_sing(self, checked: bool) -> None:
        """由 App 反向同步（例如用户在文本框里手动删掉了 (唱歌) 标签）。"""
        self._sing_var.set(checked)

    @property
    def selected_voice_name(self) -> str:
        """当前选中音色的展示名，用于拼默认文件名。"""
        return catalog.PRESET_VOICES[self._voice_box.current()]["name"]

    # ================================================================ 内部

    def _refresh_voice_hint(self) -> None:
        voice = catalog.PRESET_VOICES[self._voice_box.current()]
        self._voice_hint.configure(text=f"Voice ID：{voice['voice_id']}")

    def _refresh_sample_hint(self) -> None:
        path = self._sample_var.get()
        if not path:
            self._sample_hint.configure(text="尚未选择样本文件", foreground="#666666")
            return
        size = os.path.getsize(path) if os.path.exists(path) else 0
        if size > catalog.MAX_SAMPLE_BYTES:
            self._sample_hint.configure(
                text=f"样本 {size / 1024 / 1024:.1f}MB，超过 10MB 上限",
                foreground="#b00020",
            )
        else:
            mime = catalog.sample_mime_for(path)
            self._sample_hint.configure(
                text=f"{size / 1024:.0f}KB · MIME {mime}",
                foreground="#666666",
            )

    def _pick_sample(self) -> None:
        path = filedialog.askopenfilename(
            title="选择音色样本",
            filetypes=[("音频样本", "*.mp3 *.wav"), ("MP3", "*.mp3"), ("WAV", "*.wav")],
        )
        if not path:
            return
        self._sample_var.set(path)
        self._refresh_sample_hint()

    def _pick_dir(self) -> None:
        path = filedialog.askdirectory(title="选择保存目录", initialdir=self._dir_var.get() or None)
        if path:
            self._dir_var.set(path)

    def _handle_sing(self) -> None:
        self._on_sing_toggle(self._sing_var.get())
