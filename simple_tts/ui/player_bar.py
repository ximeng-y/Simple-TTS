"""底部播放条：合成按钮 + 进度 + 试听控制。

本版本后端尚未接入：
  - 「合成」只走一遍假进度（约 1.5 秒）后复位，不落盘、不弹提示、不播放
  - 播放条上的试听 / 停止 / 进度 / 音量控件保留完整形态，但操作后无任何效果
"""

from __future__ import annotations

from tkinter import ttk

from . import theme

# 假合成的总时长（毫秒）与进度刷新间隔
_FAKE_TOTAL_MS = 1500
_TICK_MS = 50

_PLACEHOLDER_TIME = "00:00 / 00:00"


class PlayerBar(ttk.Frame):
    def __init__(self, parent, on_synthesize, on_play, on_stop, on_seek, on_volume) -> None:
        super().__init__(parent, padding=(theme.PAD_L, theme.PAD, theme.PAD_L, theme.PAD))
        self._on_synthesize = on_synthesize

        self.columnconfigure(1, weight=1)

        # ---- 合成
        self.synth_button = ttk.Button(self, text="合成", command=on_synthesize, width=10)
        self.synth_button.grid(row=0, column=0, sticky="w")

        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=1, sticky="ew", padx=theme.PAD)

        # ---- 试听控制
        controls = ttk.Frame(self)
        controls.grid(row=0, column=2, sticky="e")

        self.play_button = ttk.Button(controls, text="▶ 试听", command=on_play, width=9)
        self.play_button.grid(row=0, column=0)

        self.stop_button = ttk.Button(controls, text="■ 停止", command=on_stop, width=9)
        self.stop_button.grid(row=0, column=1, padx=(theme.GAP, theme.PAD))

        self.seek_scale = ttk.Scale(
            controls, from_=0, to=100, orient="horizontal", length=160
        )
        self.seek_scale.set(0)
        self.seek_scale.state(["disabled"])
        self.seek_scale.grid(row=0, column=2)
        # 初始化完成后再挂回调：ttk.Scale 的 set() 也会触发 command，
        # 提前挂会在控件尚未装配进主窗口时就回调到 App。
        self.seek_scale.configure(command=on_seek)

        self.time_label = ttk.Label(controls, text=_PLACEHOLDER_TIME, style="Hint.TLabel", width=15)
        self.time_label.grid(row=0, column=3, padx=theme.GAP)

        ttk.Label(controls, text="音量", style="Hint.TLabel").grid(row=0, column=4)
        self.volume_scale = ttk.Scale(
            controls, from_=0, to=100, orient="horizontal", length=90
        )
        self.volume_scale.set(80)
        self.volume_scale.grid(row=0, column=5, padx=(theme.GAP, 0))
        self.volume_scale.configure(command=on_volume)

        self._tick_job: str | None = None
        self._elapsed_ms = 0

    # ================================================================ 对外

    def set_busy(self, busy: bool) -> None:
        """合成期间禁用交互控件，进度条只在忙碌时可见。"""
        if busy:
            self.synth_button.state(["disabled"])
            self.play_button.state(["disabled"])
            self.stop_button.state(["disabled"])
            self.progress.grid()
            self.progress["value"] = 0
            self.time_label.configure(text=_PLACEHOLDER_TIME)
        else:
            self.synth_button.state(["!disabled"])
            self.play_button.state(["!disabled"])
            self.stop_button.state(["!disabled"])
            self.progress["value"] = 0
            self.progress.grid_remove()

    def start_fake_progress(self, on_done) -> None:
        """走一遍假进度后回调 on_done。不做任何真实合成。"""
        self._elapsed_ms = 0
        self._on_done = on_done
        self._tick()

    # ================================================================ 内部

    def _tick(self) -> None:
        self._elapsed_ms += _TICK_MS
        ratio = min(self._elapsed_ms / _FAKE_TOTAL_MS, 1.0)
        self.progress["value"] = ratio * 100
        if ratio >= 1.0:
            self._tick_job = None
            self._on_done()
            return
        self._tick_job = self.after(_TICK_MS, self._tick)

    def cancel(self) -> None:
        if self._tick_job is not None:
            self.after_cancel(self._tick_job)
            self._tick_job = None
