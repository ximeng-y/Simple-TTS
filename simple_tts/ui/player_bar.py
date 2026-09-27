"""底部播放条：合成按钮 + 进度 + 试听控制 + 保存。

四个状态互斥，由 set_state() 统一驱动：

    synth    合成中：全部控件禁用，进度条走不确定动画（时长未知，给不出百分比）
    idle     空闲：没有可播放的文件，只有「合成」可用，进度条隐藏
    ready    已装载：可试听、可保存、可拖动进度、可调音量，进度条隐藏
    playing  播放中：同 ready，但进度条显示播放位置

进度条只在合成中与播放中出现：合成失败或播放结束就隐藏，不留一条读不出的静态进度。

「保存」与试听同级：合成产物只落在临时目录里会被上限清掉，保存是把它拷进
保存目录的唯一入口。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QProgressBar,
    QPushButton,
    QSlider,
    QWidget,
)

from . import theme

_PLACEHOLDER_TIME = "00:00 / 00:00"

# 进度条内部以 0-1000 表示播放比例，避免用浮点拖动滑块
_PROGRESS_MAX = 1000


def _format_time(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class PlayerBar(QWidget):
    def __init__(
        self, parent, on_synthesize, on_play, on_stop, on_save, on_seek, on_volume
    ) -> None:
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
        self.progress.setRange(0, _PROGRESS_MAX)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
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

        self.save_button = QPushButton("保存", self)
        self.save_button.setMinimumWidth(80)
        self.save_button.clicked.connect(lambda: on_save())
        layout.addWidget(self.save_button)

        self.seek_scale = QSlider(Qt.Horizontal, self)
        self.seek_scale.setRange(0, _PROGRESS_MAX)
        self.seek_scale.setFixedWidth(160)
        layout.addWidget(self.seek_scale)
        # 用 sliderMoved 而非 valueChanged：后者在拖动与程序回写位置时都会触发，
        # 回写会立刻反过来 seek 一次，形成抖动。sliderMoved 只在用户拖动时发出。
        self.seek_scale.sliderMoved.connect(on_seek)

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

        self.set_state("idle")

    # ================================================================ 对外

    @property
    def state(self) -> str:
        """当前状态。只读——状态一律经 set_state 变更，避免各处自行赋值。"""
        return self._state

    def set_state(self, state: str) -> None:
        """切换播放条状态：synth / idle / ready / playing。"""
        self._state = state

        synthesizing = state == "synth"
        playable = state in ("ready", "playing")

        self.synth_button.setEnabled(not synthesizing)
        self.play_button.setEnabled(playable)
        self.stop_button.setEnabled(playable)
        self.save_button.setEnabled(playable)
        self.seek_scale.setEnabled(playable)
        # 音量由客户端播放器决定，有文件即可调；合成中连文件都还没有
        self.volume_scale.setEnabled(not synthesizing)

        if state == "synth":
            # 时长未知，走不确定动画而不是给出一个编造的百分比
            self.progress.setRange(0, 0)
            self.progress.setVisible(True)
            self.time_label.setText(_PLACEHOLDER_TIME)
            self.seek_scale.setValue(0)
        elif state == "idle":
            self.progress.setRange(0, _PROGRESS_MAX)
            self.progress.setValue(0)
            self.progress.setVisible(False)
            self.time_label.setText(_PLACEHOLDER_TIME)
            self.seek_scale.setValue(0)
        else:
            self.progress.setRange(0, _PROGRESS_MAX)
            self.progress.setVisible(state == "playing")

    def set_position(self, position: float, duration: float) -> None:
        """刷新播放进度与时间标签。不播放、不拖动时原地不动。"""
        self.time_label.setText(f"{_format_time(position)} / {_format_time(duration)}")
        if duration <= 0:
            return
        ratio = max(0.0, min(position / duration, 1.0))
        value = int(ratio * _PROGRESS_MAX)
        # 用户正按住滑块时不要抢着回写，否则滑块会被拽回播放位置
        if not self.seek_scale.isSliderDown():
            self.seek_scale.setValue(value)
        self.progress.setValue(value)

    def playback_ratio(self) -> float:
        """拖动条当前位置对应的比例，供 App 换算成 seek 的秒数。"""
        return self.seek_scale.value() / _PROGRESS_MAX
