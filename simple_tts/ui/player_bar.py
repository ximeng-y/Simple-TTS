"""底部播放条：合成按钮 + 进度 + 试听控制。

本版本后端尚未接入：
  - 「合成」只走一遍假进度（约 1.5 秒）后复位，不落盘、不弹提示、不播放
  - 播放条上的试听 / 停止 / 进度 / 音量控件保留完整形态，但操作后无任何效果
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QWidget,
)

from . import theme

# 假合成的总时长（毫秒）与进度刷新间隔
_FAKE_TOTAL_MS = 1500
_TICK_MS = 50

_PLACEHOLDER_TIME = "00:00 / 00:00"


class PlayerBar(QWidget):
    def __init__(self, parent, on_synthesize, on_play, on_stop, on_seek, on_volume) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(theme.PAD_L, theme.PAD, theme.PAD_L, theme.PAD)
        layout.setSpacing(theme.GAP)

        # ---- 合成
        self.synth_button = QPushButton("合成", self)
        self.synth_button.setMinimumWidth(90)
        self.synth_button.clicked.connect(lambda: on_synthesize())
        layout.addWidget(self.synth_button)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress, 1)

        # ---- 试听控制
        self.play_button = QPushButton("▶ 试听", self)
        self.play_button.setMinimumWidth(80)
        self.play_button.clicked.connect(lambda: on_play())
        layout.addWidget(self.play_button)

        self.stop_button = QPushButton("■ 停止", self)
        self.stop_button.setMinimumWidth(80)
        self.stop_button.clicked.connect(lambda: on_stop())
        layout.addWidget(self.stop_button)

        self.seek_scale = QSlider(Qt.Horizontal, self)
        self.seek_scale.setRange(0, 100)
        self.seek_scale.setFixedWidth(160)
        self.seek_scale.setEnabled(False)
        layout.addWidget(self.seek_scale)
        # 初始化完成后再接信号：QSlider.setValue() 同样会发 valueChanged，
        # 提前接会在控件尚未装配进主窗口时就回调到 App。
        self.seek_scale.valueChanged.connect(on_seek)

        self.time_label = theme.hint(self, _PLACEHOLDER_TIME)
        self.time_label.setMinimumWidth(100)
        self.time_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.time_label)

        layout.addWidget(theme.hint(self, "音量"))

        self.volume_scale = QSlider(Qt.Horizontal, self)
        self.volume_scale.setRange(0, 100)
        self.volume_scale.setFixedWidth(90)
        self.volume_scale.setValue(80)
        self.volume_scale.valueChanged.connect(on_volume)
        layout.addWidget(self.volume_scale)

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

        self._on_done = None
        self._elapsed_ms = 0

    # ================================================================ 对外

    def set_busy(self, busy: bool) -> None:
        """合成期间禁用交互控件，进度条只在忙碌时可见。"""
        if busy:
            self.synth_button.setEnabled(False)
            self.play_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.progress.setVisible(True)
            self.progress.setValue(0)
            self.time_label.setText(_PLACEHOLDER_TIME)
        else:
            self.synth_button.setEnabled(True)
            self.play_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            self.progress.setValue(0)
            self.progress.setVisible(False)

    def start_fake_progress(self, on_done) -> None:
        """走一遍假进度后回调 on_done。不做任何真实合成。"""
        self._elapsed_ms = 0
        self._on_done = on_done
        self._timer.start()
        self._tick()

    # ================================================================ 内部

    def _tick(self) -> None:
        self._elapsed_ms += _TICK_MS
        ratio = min(self._elapsed_ms / _FAKE_TOTAL_MS, 1.0)
        self.progress.setValue(int(ratio * 100))
        if ratio >= 1.0:
            self._timer.stop()
            if self._on_done is not None:
                self._on_done()

    def cancel(self) -> None:
        self._timer.stop()
