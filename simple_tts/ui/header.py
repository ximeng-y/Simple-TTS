"""顶部工具条：模型选择 + 当前模型说明。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget

from .. import catalog
from . import theme


class Header(QWidget):
    def __init__(self, parent, on_model_change) -> None:
        super().__init__(parent)
        self._on_model_change = on_model_change

        layout = QHBoxLayout(self)
        layout.setContentsMargins(theme.PAD_L, theme.PAD, theme.PAD_L, theme.PAD)
        layout.setSpacing(theme.GAP)

        layout.addWidget(theme.title(self, "模型"))

        # 模型 id 与下拉项文本分开维护，避免展示文案变化时失配
        self._labels = [model["label"] for model in catalog.MODELS]
        self.model_box = QComboBox(self)
        self.model_box.setEditable(False)
        self.model_box.addItems(self._labels)
        self.model_box.setMinimumWidth(280)
        self.model_box.currentIndexChanged.connect(self._handle_select)
        layout.addWidget(self.model_box)

        self.desc_label = theme.hint(self, "")
        self.desc_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.desc_label, 1)

        self.refresh_desc()

    # ---------------------------------------------------------------- 对外

    @property
    def model_id(self) -> str:
        return catalog.MODELS[self.model_box.currentIndex()]["id"]

    def set_model_id(self, model_id: str) -> None:
        """按 id 选中模型，不触发回调。"""
        for index, model in enumerate(catalog.MODELS):
            if model["id"] == model_id:
                self.model_box.blockSignals(True)
                self.model_box.setCurrentIndex(index)
                self.model_box.blockSignals(False)
                self.refresh_desc()
                return

    def refresh_desc(self) -> None:
        self.desc_label.setText(catalog.model_by_id(self.model_id)["desc"])

    # ---------------------------------------------------------------- 内部

    def _handle_select(self, _index: int) -> None:
        self.refresh_desc()
        self._on_model_change(self.model_id)
