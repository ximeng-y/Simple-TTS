"""右侧配置区：音色 + 输出。

「音色」区的三块内容互斥，随顶部所选模型切换（预置音色 / 音色设计 / 音色复刻）。
三块做成 QStackedWidget 的三页，切换时只换当前页，不产生 Notebook 那样的标签页视觉噪音。
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import catalog
from . import theme

# 三种音色来源在 QStackedWidget 里的页序，与 catalog 的 tone_source 对应
_PAGE_ORDER = ("preset", "design", "clone")


class ConfigPanel(QScrollArea):
    """参数区，内容超出窗口高度时可纵向滚动。

    与 App 的约定：
      - on_sing_toggle(checked) 唱歌模式勾选变化时回调，由 App 去改文本框内容
      - commit() 把控件值写回 state；apply_model() 把 state 读进控件
    """

    def __init__(self, parent, state, on_sing_toggle) -> None:
        super().__init__(parent)
        self._state = state
        self._on_sing_toggle = on_sing_toggle

        # 内容宽度跟随可视区，否则内部换行标签按 sizeHint 宽度算高度、文字会被截断
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(theme.PAD_L, theme.PAD, theme.PAD, theme.PAD)
        layout.setSpacing(theme.PAD)

        # 音色与输出左右并排，避免在滚动框内上下堆叠
        layout.addWidget(self._build_voice_section(), 1)
        layout.addWidget(self._build_output_section(), 1)
        self.setWidget(root)

    # ================================================================ 构建

    def _build_voice_section(self) -> QGroupBox:
        section = QGroupBox(" 音色 ", self)
        layout = QVBoxLayout(section)

        self._stack = QStackedWidget(section)
        layout.addWidget(self._stack)

        # 三个块共用一个栈，靠 setCurrentIndex 显示/隐藏
        self._blocks: dict[str, QWidget] = {}
        for key in _PAGE_ORDER:
            block = QWidget(section)
            self._blocks[key] = block
            self._stack.addWidget(block)

        self._build_preset_block(self._blocks["preset"])
        self._build_design_block(self._blocks["design"])
        self._build_clone_block(self._blocks["clone"])
        return section

    def _build_preset_block(self, block: QWidget) -> None:
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.GAP)

        layout.addWidget(theme.title(block, "预置音色"))

        self._voice_box = QComboBox(block)
        self._voice_box.setEditable(False)
        self._voice_box.currentIndexChanged.connect(self._refresh_voice_hint)
        layout.addWidget(self._voice_box)

        self._voice_hint = theme.hint(block, "", wrap=True)
        layout.addWidget(self._voice_hint)

        self._sing_check = QCheckBox("唱歌模式", block)
        self._sing_check.toggled.connect(self._handle_sing)
        layout.addWidget(self._sing_check)

        layout.addWidget(
            theme.hint(
                block,
                "勾选后会在合成文本开头添加 (唱歌) 标签；歌词建议使用中文。",
                wrap=True,
            )
        )
        layout.addStretch(1)

    def _build_design_block(self, block: QWidget) -> None:
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.GAP)

        layout.addWidget(theme.title(block, "音色由描述生成"))
        layout.addWidget(
            theme.hint(
                block,
                "在左侧「音色描述」中写一段文字描述想要的音色，无需提供音频样本。",
                wrap=True,
            )
        )

        layout.addWidget(theme.title(block, "可参考的维度"))
        for hint in catalog.VOICE_DESC_HINTS:
            layout.addWidget(theme.hint(block, f"· {hint}", wrap=True))

        self._optimize_check = QCheckBox("文本智能润色", block)
        layout.addWidget(self._optimize_check)
        layout.addWidget(
            theme.hint(
                block,
                "对应请求参数 audio.optimize_text_preview；开启时可省略合成文本，"
                "由服务端根据需要播报的内容智能润色。",
                wrap=True,
            )
        )
        layout.addStretch(1)

    def _build_clone_block(self, block: QWidget) -> None:
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.GAP)

        layout.addWidget(theme.title(block, "音频样本"))

        picker = QHBoxLayout()
        picker.setSpacing(theme.GAP)
        self._sample_edit = QLineEdit(block)
        self._sample_edit.setReadOnly(True)
        picker.addWidget(self._sample_edit, 1)

        pick_button = QPushButton("选择样本…", block)
        pick_button.clicked.connect(self._pick_sample)
        picker.addWidget(pick_button)
        layout.addLayout(picker)

        self._sample_hint = theme.hint(block, "", wrap=True)
        layout.addWidget(self._sample_hint)

        layout.addWidget(
            theme.hint(
                block,
                "样本会被编码成 data:audio/{MIME};base64,… 传给 audio.voice，"
                "Base64 后不得超过 10MB，仅支持 mp3 与 wav。",
                wrap=True,
            )
        )
        layout.addStretch(1)

    def _build_output_section(self) -> QGroupBox:
        section = QGroupBox(" 输出 ", self)
        layout = QVBoxLayout(section)
        layout.setSpacing(theme.GAP)

        layout.addWidget(theme.title(section, "音频格式"))

        # 单选按钮需显式分组，否则与同一窗口内的其它 QRadioButton 互斥
        self._format_group = QButtonGroup(self)
        self._format_buttons: dict[str, QRadioButton] = {}
        for fmt_id, label, note in catalog.FORMATS:
            button = QRadioButton(label, section)
            self._format_group.addButton(button)
            self._format_buttons[fmt_id] = button
            layout.addWidget(button)
            layout.addWidget(theme.hint(section, note, wrap=True))

        separator = QFrame(section)
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        layout.addWidget(theme.title(section, "保存目录"))
        dir_row = QHBoxLayout()
        dir_row.setSpacing(theme.GAP)
        self._dir_edit = QLineEdit(section)
        dir_row.addWidget(self._dir_edit, 1)
        dir_button = QPushButton("浏览…", section)
        dir_button.clicked.connect(self._pick_dir)
        dir_row.addWidget(dir_button)
        layout.addLayout(dir_row)

        layout.addWidget(theme.title(section, "文件名模式"))
        self._pattern_edit = QLineEdit(section)
        layout.addWidget(self._pattern_edit)

        layout.addWidget(
            theme.hint(
                section,
                "可用变量：{ts} 时间戳、{voice} 音色、{model} 模型、{index} 序号；"
                "扩展名按音频格式自动追加，不用写在这里",
                wrap=True,
            )
        )

        self._autoplay_check = QCheckBox("合成后自动试听", section)
        layout.addWidget(self._autoplay_check)
        return section

    # ================================================================ 对外

    def apply_model(self) -> None:
        """把 state 中当前模型的配置读进控件，并切换到对应的音色块。"""
        model = self._state.model
        draft = self._state.draft()

        self._stack.setCurrentWidget(self._blocks[model["tone_source"]])

        if model["tone_source"] == "preset":
            self._voice_box.blockSignals(True)
            self._voice_box.clear()
            for voice in catalog.PRESET_VOICES:
                self._voice_box.addItem(catalog.voice_label(voice), voice["voice_id"])
            index = next(
                (
                    i
                    for i, voice in enumerate(catalog.PRESET_VOICES)
                    if voice["voice_id"] == draft.voice_id
                ),
                0,
            )
            self._voice_box.setCurrentIndex(index)
            self._voice_box.blockSignals(False)
            self._refresh_voice_hint()
            self._set_sing_checked(draft.sing)

        if model["tone_source"] == "design":
            self._optimize_check.setChecked(draft.optimize_preview)

        if model["tone_source"] == "clone":
            self._sample_edit.setText(draft.sample_path)
            self._refresh_sample_hint()

        for fmt_id, button in self._format_buttons.items():
            button.setChecked(fmt_id == self._state.audio_format)
        self._dir_edit.setText(self._state.output_dir)
        self._pattern_edit.setText(self._state.filename_pattern)
        self._autoplay_check.setChecked(self._state.auto_play)

    def apply_settings(self) -> None:
        """设置页确认后，把与设置页重叠的项同步到控件。"""
        for fmt_id, button in self._format_buttons.items():
            button.setChecked(fmt_id == self._state.audio_format)
        self._dir_edit.setText(self._state.output_dir)
        self._autoplay_check.setChecked(self._state.auto_play)

    def commit(self) -> None:
        """把控件值写回 state（仅内存）。切模型前与点合成前调用。"""
        draft = self._state.draft()
        model = self._state.model

        if model["tone_source"] == "preset":
            draft.voice_id = self._voice_box.currentData() or catalog.PRESET_VOICES[0]["voice_id"]
            draft.sing = self._sing_check.isChecked()
        if model["tone_source"] == "design":
            draft.optimize_preview = self._optimize_check.isChecked()

        if model["tone_source"] == "clone":
            draft.sample_path = self._sample_edit.text()

        self._state.audio_format = self._current_format() or "wav"
        self._state.output_dir = self._dir_edit.text()
        self._state.filename_pattern = self._pattern_edit.text()
        self._state.auto_play = self._autoplay_check.isChecked()

    def set_sing(self, checked: bool) -> None:
        """由 App 反向同步（例如用户在文本框里手动删掉了 (唱歌) 标签）。"""
        self._set_sing_checked(checked)

    @property
    def voice_name(self) -> str:
        """当前音色的展示名，用于拼默认文件名。

        三个模型的音色来源不同，取不到合适名字时回落到模型简称：
        预置音色用下拉里的名字，复刻用样本文件名，音色设计没有具体音色。
        """
        tone_source = self._state.model["tone_source"]
        if tone_source == "preset":
            return self._current_voice().get("name", "")
        if tone_source == "clone":
            path = self._sample_edit.text()
            return os.path.splitext(os.path.basename(path))[0] if path else ""
        return ""

    @property
    def voice_id(self) -> str:
        """当前选中的预置音色 Voice ID；其它模型下为空。"""
        if self._state.model["tone_source"] != "preset":
            return ""
        return self._current_voice().get("voice_id", "")

    # ================================================================ 内部

    def _current_voice(self) -> dict:
        voice_id = self._voice_box.currentData()
        for voice in catalog.PRESET_VOICES:
            if voice["voice_id"] == voice_id:
                return voice
        return {}

    def _current_format(self) -> str:
        for fmt_id, button in self._format_buttons.items():
            if button.isChecked():
                return fmt_id
        return ""

    def _set_sing_checked(self, checked: bool) -> None:
        """程序化改勾选状态。

        QCheckBox.setChecked() 会发出 toggled 信号，若不屏蔽就会回到 _handle_sing，
        再经 App 转一圈绕回本方法，形成回环。
        """
        if self._sing_check.isChecked() == checked:
            return
        self._sing_check.blockSignals(True)
        self._sing_check.setChecked(checked)
        self._sing_check.blockSignals(False)

    def _refresh_voice_hint(self, _index: int = 0) -> None:
        voice_id = self._voice_box.currentData()
        self._voice_hint.setText(f"Voice ID：{voice_id}" if voice_id else "")

    def _refresh_sample_hint(self) -> None:
        path = self._sample_edit.text()
        if not path:
            self._sample_hint.setStyleSheet("color: #666666;")
            self._sample_hint.setText("尚未选择样本文件")
            return
        size = os.path.getsize(path) if os.path.exists(path) else 0
        if size > catalog.MAX_SAMPLE_BYTES:
            self._sample_hint.setStyleSheet("color: #b00020;")
            self._sample_hint.setText(f"样本 {size / 1024 / 1024:.1f}MB，超过 10MB 上限")
        else:
            self._sample_hint.setStyleSheet("color: #666666;")
            mime = catalog.sample_mime_for(path)
            self._sample_hint.setText(f"{size / 1024:.0f}KB · MIME {mime}")

    def _pick_sample(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "选择音色样本",
            "",
            "音频样本 (*.mp3 *.wav);;MP3 (*.mp3);;WAV (*.wav)",
        )
        if not path:
            return
        self._sample_edit.setText(path)
        self._refresh_sample_hint()

    def _pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "选择保存目录", self._dir_edit.text() or ""
        )
        if path:
            self._dir_edit.setText(path)

    def _handle_sing(self, checked: bool) -> None:
        self._on_sing_toggle(checked)
