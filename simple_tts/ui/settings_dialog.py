"""设置页。

本版本仅做前端形态演示，点「确定」只把值写回内存中的 AppState，不落盘；
重启后回到默认值。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import catalog
from . import theme

_NOTE = "本版本仅前端形态演示，配置只保存在内存中，不会写入磁盘。"


class SettingsDialog(QDialog):
    def __init__(self, parent, state) -> None:
        super().__init__(parent)
        self._state = state

        self.setWindowTitle("设置")
        self.setSizeGripEnabled(False)

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.GAP)

        notebook = QTabWidget(self)
        notebook.addTab(self._build_api_page(notebook), "  API  ")
        notebook.addTab(self._build_general_page(notebook), "  通用  ")
        layout.addWidget(notebook)

        layout.addWidget(theme.hint(self, _NOTE))

        buttons = QDialogButtonBox(self)
        ok = buttons.addButton("确定", QDialogButtonBox.AcceptRole)
        cancel = buttons.addButton("取消", QDialogButtonBox.RejectRole)
        ok.setMinimumWidth(80)
        cancel.setMinimumWidth(80)
        ok.clicked.connect(self._confirm)
        cancel.clicked.connect(self.reject)
        layout.addWidget(buttons, 0, Qt.AlignRight)

        self._load()
        self._center_on(parent)

    # ================================================================ 页面

    def _build_api_page(self, parent) -> QWidget:
        page = QWidget(parent)
        layout = QGridLayout(page)
        layout.setSpacing(theme.GAP)
        layout.setColumnStretch(1, 1)

        layout.addWidget(theme.title(page, "API Base URL"), 0, 0, Qt.AlignLeft)
        self._base_edit = QLineEdit(page)
        self._base_edit.setMinimumWidth(360)
        layout.addWidget(self._base_edit, 0, 1)
        layout.addWidget(
            theme.hint(page, "OpenAI Chat Completions 风格接口，例如 https://api.xiaomimimo.com/v1"),
            1,
            1,
            Qt.AlignLeft,
        )

        layout.addWidget(theme.title(page, "API Key"), 2, 0, Qt.AlignLeft)
        self._key_edit = QLineEdit(page)
        self._key_edit.setEchoMode(QLineEdit.Password)
        layout.addWidget(self._key_edit, 2, 1)

        self._show_key_check = QCheckBox("显示", page)
        self._show_key_check.toggled.connect(self._toggle_key)
        layout.addWidget(self._show_key_check, 3, 1, Qt.AlignLeft)

        layout.addWidget(
            theme.hint(page, "仅保存在本次运行的内存中"),
            4,
            1,
            Qt.AlignLeft,
        )
        return page

    def _build_general_page(self, parent) -> QWidget:
        page = QWidget(parent)
        layout = QGridLayout(page)
        layout.setSpacing(theme.GAP)
        layout.setColumnStretch(1, 1)
        row = 0

        layout.addWidget(theme.title(page, "默认保存目录"), row, 0, Qt.AlignLeft)
        dir_row = QHBoxLayout()
        dir_row.setSpacing(theme.GAP)
        self._dir_edit = QLineEdit(page)
        dir_row.addWidget(self._dir_edit, 1)
        dir_button = QPushButton("浏览…", page)
        dir_button.clicked.connect(self._pick_dir)
        dir_row.addWidget(dir_button)
        layout.addLayout(dir_row, row, 1)
        row += 1

        layout.addWidget(theme.title(page, "默认音频格式"), row, 0, Qt.AlignLeft)
        formats_row = QHBoxLayout()
        formats_row.setSpacing(theme.PAD)
        format_group = QButtonGroup(self)
        self._format_buttons: dict[str, QRadioButton] = {}
        for fmt_id, label, _note in catalog.FORMATS:
            button = QRadioButton(label, page)
            format_group.addButton(button)
            self._format_buttons[fmt_id] = button
            formats_row.addWidget(button)
        formats_row.addStretch(1)
        layout.addLayout(formats_row, row, 1)
        row += 1

        self._autoplay_check = QCheckBox("合成后自动试听", page)
        layout.addWidget(self._autoplay_check, row, 1, Qt.AlignLeft)
        row += 1

        self._history_check = QCheckBox("保留合成历史记录", page)
        layout.addWidget(self._history_check, row, 1, Qt.AlignLeft)
        row += 1

        self._overwrite_check = QCheckBox("覆盖同名文件前确认", page)
        layout.addWidget(self._overwrite_check, row, 1, Qt.AlignLeft)
        return page

    # ================================================================ 数据

    def _load(self) -> None:
        self._base_edit.setText(self._state.api_base)
        self._key_edit.setText(self._state.api_key)
        self._dir_edit.setText(self._state.output_dir)
        for fmt_id, button in self._format_buttons.items():
            button.setChecked(fmt_id == self._state.audio_format)
        self._autoplay_check.setChecked(self._state.auto_play)
        self._history_check.setChecked(self._state.keep_history)
        self._overwrite_check.setChecked(self._state.confirm_overwrite)

    def _collect_format(self) -> str:
        for fmt_id, button in self._format_buttons.items():
            if button.isChecked():
                return fmt_id
        return ""

    def _confirm(self) -> None:
        state = self._state
        state.api_base = self._base_edit.text().strip() or catalog.DEFAULT_API_BASE
        state.api_key = self._key_edit.text()
        state.output_dir = self._dir_edit.text()
        state.audio_format = self._collect_format() or "wav"
        state.auto_play = self._autoplay_check.isChecked()
        state.keep_history = self._history_check.isChecked()
        state.confirm_overwrite = self._overwrite_check.isChecked()
        self.accept()

    # ================================================================ 内部

    def _toggle_key(self, checked: bool) -> None:
        self._key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def _pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择默认保存目录", self._dir_edit.text() or "")
        if path:
            self._dir_edit.setText(path)

    def _center_on(self, parent) -> None:
        self.adjustSize()
        if parent is None:
            return
        x = parent.x() + (parent.width() - self.width()) // 2
        y = parent.y() + (parent.height() - self.height()) // 3
        self.move(max(x, 0), max(y, 0))
