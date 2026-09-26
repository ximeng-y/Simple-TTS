"""顶部工具条：模型选择 + 当前模型说明。"""

from __future__ import annotations

from tkinter import ttk

from .. import catalog
from . import theme


class Header(ttk.Frame):
    def __init__(self, parent, on_model_change) -> None:
        super().__init__(parent, padding=(theme.PAD_L, theme.PAD, theme.PAD_L, theme.PAD))
        self._on_model_change = on_model_change

        self.columnconfigure(2, weight=1)

        ttk.Label(self, text="模型", style="Title.TLabel").grid(row=0, column=0, sticky="w")

        # 模型 id 与下拉项文本分开维护，避免展示文案变化时失配
        self._labels = [model["label"] for model in catalog.MODELS]
        self.model_box = ttk.Combobox(
            self, values=self._labels, state="readonly", width=38
        )
        self.model_box.current(0)
        self.model_box.grid(row=0, column=1, sticky="w", padx=(theme.GAP, theme.PAD_L))
        self.model_box.bind("<<ComboboxSelected>>", self._handle_select)

        self.desc_label = ttk.Label(self, style="Hint.TLabel", anchor="e")
        self.desc_label.grid(row=0, column=2, sticky="ew")

        self.refresh_desc()

    # ---------------------------------------------------------------- 对外

    @property
    def model_id(self) -> str:
        return catalog.MODELS[self.model_box.current()]["id"]

    def set_model_id(self, model_id: str) -> None:
        """按 id 选中模型，不触发回调。"""
        for index, model in enumerate(catalog.MODELS):
            if model["id"] == model_id:
                self.model_box.current(index)
                self.refresh_desc()
                return

    def refresh_desc(self) -> None:
        self.desc_label.configure(text=catalog.model_by_id(self.model_id)["desc"])

    # ---------------------------------------------------------------- 内部

    def _handle_select(self, _event) -> None:
        self.refresh_desc()
        self._on_model_change(self.model_id)
