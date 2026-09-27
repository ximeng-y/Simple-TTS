"""设置页。

顶层页序与菜单「设置」中各项一一对应：通用 / 供应商 / API KEY。
「供应商」页决定当前启用哪一家，「API KEY」页则按供应商分标签各存一份 Key。

配置只存在于内存中的 AppState，点「确定」写回后即生效，但不落盘；重启回到默认值。
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

_NOTE = "配置只保存在本次运行的内存中，不会写入磁盘，重启后回到默认值。"

# 顶层页的 key 与标签，页序即菜单「设置」里的展示顺序
_PAGES = (("general", "  通用  "), ("provider", "  供应商  "), ("api", "  API KEY  "))


class SettingsDialog(QDialog):
    """参数：page 为打开时停在的顶层页 key，取不到时落在第一页。"""

    def __init__(self, parent, state, page: str = "general") -> None:
        super().__init__(parent)
        self._state = state
        # 打开时的启用供应商，用于确认后判断是否需要让 App 重载界面
        self._initial_provider = state.provider_id
        # 界面上当前选中的供应商，决定 API KEY 页停在哪个标签
        self._picked_provider = state.provider_id

        self.setWindowTitle("设置")
        self.setSizeGripEnabled(False)

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.GAP)

        self._notebook = QTabWidget(self)
        for key, label in _PAGES:
            self._notebook.addTab(self._build_page(key, self._notebook), label)
        layout.addWidget(self._notebook)

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
        self._goto(page)
        self._center_on(parent)

    # ================================================================ 对外

    @property
    def provider_changed(self) -> bool:
        """确认后与打开前的启用供应商是否不同。"""
        return self._state.provider_id != self._initial_provider

    # ================================================================ 页面

    def _build_page(self, key: str, parent) -> QWidget:
        if key == "general":
            return self._build_general_page(parent)
        if key == "provider":
            return self._build_provider_page(parent)
        return self._build_api_page(parent)

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

    def _build_provider_page(self, parent) -> QWidget:
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setSpacing(theme.GAP)

        layout.addWidget(theme.title(page, "启用的供应商"))
        layout.addWidget(
            theme.hint(
                page,
                "供应商决定顶部「模型」下拉里列出哪些模型，以及 API KEY 页里有哪些标签。",
                wrap=True,
            )
        )

        # 供应商列表当前硬编码只有 MIMO 一家；接入第二家后这里自动多出一项
        self._provider_group = QButtonGroup(self)
        self._provider_buttons: dict[str, QRadioButton] = {}
        for provider in catalog.PROVIDERS:
            button = QRadioButton(f"{provider['name']}　—　{provider['desc']}", page)
            self._provider_group.addButton(button)
            self._provider_buttons[provider["id"]] = button
            layout.addWidget(button)
            layout.addWidget(theme.hint(page, f"接口基地址：{provider['base_url']}"))

        layout.addStretch(1)
        return page

    def _build_api_page(self, parent) -> QWidget:
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setSpacing(theme.GAP)

        head = QHBoxLayout()
        head.setSpacing(theme.GAP)
        head.addWidget(theme.title(page, "当前启用供应商"))
        self._provider_label = theme.title(page, "")
        head.addWidget(self._provider_label)
        head.addStretch(1)
        layout.addLayout(head)

        # 每家供应商一个标签页，Key 各存各的，切换标签不会互相覆盖
        self._key_notebook = QTabWidget(page)
        self._base_edits: dict[str, QLineEdit] = {}
        self._key_edits: dict[str, QLineEdit] = {}
        self._show_key_checks: dict[str, QCheckBox] = {}
        for provider in catalog.PROVIDERS:
            self._key_notebook.addTab(self._build_api_tab(provider), f"  {provider['name']}  ")
        layout.addWidget(self._key_notebook)
        return page

    def _build_api_tab(self, provider: dict) -> QWidget:
        tab = QWidget(self._key_notebook)
        layout = QGridLayout(tab)
        layout.setSpacing(theme.GAP)
        layout.setColumnStretch(1, 1)

        layout.addWidget(theme.title(tab, "API Base URL"), 0, 0, Qt.AlignLeft)
        base_edit = QLineEdit(tab)
        base_edit.setMinimumWidth(360)
        # 基地址由供应商硬编码决定，只读展示
        base_edit.setReadOnly(True)
        self._base_edits[provider["id"]] = base_edit
        layout.addWidget(base_edit, 0, 1)
        layout.addWidget(
            theme.hint(tab, "由供应商决定，不可修改"),
            1,
            1,
            Qt.AlignLeft,
        )

        layout.addWidget(theme.title(tab, "API Key"), 2, 0, Qt.AlignLeft)
        key_edit = QLineEdit(tab)
        key_edit.setEchoMode(QLineEdit.Password)
        self._key_edits[provider["id"]] = key_edit
        layout.addWidget(key_edit, 2, 1)

        show_check = QCheckBox("显示", tab)
        show_check.toggled.connect(
            lambda checked, edit=key_edit: edit.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        self._show_key_checks[provider["id"]] = show_check
        layout.addWidget(show_check, 3, 1, Qt.AlignLeft)

        layout.addWidget(theme.hint(tab, "仅保存在本次运行的内存中"), 4, 1, Qt.AlignLeft)
        layout.setRowStretch(5, 1)
        return tab

    # ================================================================ 数据

    def _load(self) -> None:
        for provider_id, button in self._provider_buttons.items():
            button.setChecked(provider_id == self._picked_provider)
        for provider in catalog.PROVIDERS:
            provider_id = provider["id"]
            self._base_edits[provider_id].setText(provider["base_url"])
            self._key_edits[provider_id].setText(self._state.api_keys.get(provider_id, ""))

        self._dir_edit.setText(self._state.output_dir)
        for fmt_id, button in self._format_buttons.items():
            button.setChecked(fmt_id == self._state.audio_format)
        self._autoplay_check.setChecked(self._state.auto_play)
        self._history_check.setChecked(self._state.keep_history)
        self._overwrite_check.setChecked(self._state.confirm_overwrite)

        self._sync_api_page()

    def _collect_format(self) -> str:
        for fmt_id, button in self._format_buttons.items():
            if button.isChecked():
                return fmt_id
        return ""

    def _collect_provider(self) -> str:
        for provider_id, button in self._provider_buttons.items():
            if button.isChecked():
                return provider_id
        return catalog.DEFAULT_PROVIDER_ID

    def _confirm(self) -> None:
        state = self._state
        # 供应商先落回 state，后续按供应商取值的项（基地址等）才拿到正确对象
        self._picked_provider = self._collect_provider()
        state.provider_id = self._picked_provider
        state.model_id = state.model["id"]
        for provider in catalog.PROVIDERS:
            provider_id = provider["id"]
            state.api_keys[provider_id] = self._key_edits[provider_id].text()

        state.output_dir = self._dir_edit.text()
        state.audio_format = self._collect_format() or "wav"
        state.auto_play = self._autoplay_check.isChecked()
        state.keep_history = self._history_check.isChecked()
        state.confirm_overwrite = self._overwrite_check.isChecked()
        self.accept()

    # ================================================================ 内部

    def _goto(self, page: str) -> None:
        """切到指定顶层页；API KEY 页同时把子标签停到当前启用的供应商。"""
        for index, (key, _label) in enumerate(_PAGES):
            if key == page:
                self._notebook.setCurrentIndex(index)
                break
        self._sync_api_page()

    def _sync_api_page(self) -> None:
        provider = catalog.provider_by_id(self._picked_provider)
        self._provider_label.setText(provider["name"])
        for index, item in enumerate(catalog.PROVIDERS):
            if item["id"] == provider["id"]:
                self._key_notebook.setCurrentIndex(index)
                return

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
