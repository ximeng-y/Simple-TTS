"""顶部工具条：模型选择 + 当前模型说明。

模型列表来自当前供应商（见 AppState.provider），换供应商后由 App 调用
``reload_models()`` 重建下拉项。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget

from . import theme


class Header(QWidget):
    def __init__(self, parent, state, on_model_change) -> None:
        super().__init__(parent)
        self._state = state
        self._on_model_change = on_model_change

        layout = QHBoxLayout(self)
        layout.setContentsMargins(theme.PAD_L, theme.PAD, theme.PAD_L, theme.PAD)
        layout.setSpacing(theme.GAP)

        layout.addWidget(theme.title(self, "模型"))

        # 下拉项与 state.model_id 分开维护：下拉只按本供应商的模型顺序建，
        # 选中哪一项始终回到 state 里按 id 判断，避免两边下标失配
        self.model_box = QComboBox(self)
        self.model_box.setEditable(False)
        self.model_box.setMinimumWidth(280)
        self.model_box.currentIndexChanged.connect(self._handle_select)
        layout.addWidget(self.model_box)

        self.desc_label = theme.hint(self, "")
        self.desc_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.desc_label, 1)

        self.reload_models()

    # ---------------------------------------------------------------- 对外

    @property
    def model_id(self) -> str:
        return self._state.model_id

    def set_model_id(self, model_id: str) -> None:
        """按 id 选中模型，不触发回调。"""
        self._select(model_id)
        self.refresh_desc()

    def reload_models(self) -> None:
        """按当前供应商重建下拉项，并选中 state 里记着的模型。"""
        models = self._state.provider["models"]
        self.model_box.blockSignals(True)
        self.model_box.clear()
        for model in models:
            self.model_box.addItem(model["label"], model["id"])
        self.model_box.blockSignals(False)

        self._select(self._state.model_id)
        self.refresh_desc()

    def refresh_desc(self) -> None:
        self.desc_label.setText(self._state.model["desc"])

    # ---------------------------------------------------------------- 内部

    def _select(self, model_id: str) -> None:
        index = self.model_box.findData(model_id)
        if index < 0:
            return
        self.model_box.blockSignals(True)
        self.model_box.setCurrentIndex(index)
        self.model_box.blockSignals(False)

    def _handle_select(self, _index: int) -> None:
        self.refresh_desc()
        self._on_model_change(self.model_box.currentData())
