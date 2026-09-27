"""风格辅助面板：可直接点选的风格标签与音频标签。

对应文档里的两种标签控制方式：
  - 开头风格标签 (风格1 风格2)正文 -> 写入合成文本最前面
  - 行内音频标签 [标签]            -> 插入到合成文本的光标处

本面板不持有文本框，只通过构造时传入的回调通知 App，由 App 转交给 TextPanel 执行，
避免 UI 模块之间互相依赖。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import catalog
from . import theme

# 每组最多 9 个按钮排成一行，超出的换行
_COLUMNS = 9
# 原 Tk 版的宽度以字符计，换算成像素的最小宽度
_BUTTON_PX = 78
_LABEL_PX = 78


class StylePanelScrollArea(QScrollArea):
    """风格辅助面板的滚动容器。

    构造后需由外部 setWidget 装入面板并 setMinimumHeight(全高 // 2) 作为压缩下限。
    """

    def resizeEvent(self, event) -> None:
        """面板宽度跟随可视区。

        面板用 widgetResizable(False) 装载（这样它不会被 viewport 带着一起缩矮），
        宽度也就没了人代管，不手动同步会在右侧留出一条空白。
        """
        super().resizeEvent(event)
        panel = self.widget()
        if panel is not None:
            panel.resize(max(self.viewport().width(), panel.minimumWidth()), panel.height())


class StylePanel(QGroupBox):
    def __init__(self, parent, on_opening_style, on_inline_tag) -> None:
        super().__init__(" 风格辅助 ", parent)
        self._on_opening_style = on_opening_style
        self._on_inline_tag = on_inline_tag

        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.PAD_L, theme.PAD, theme.PAD_L, theme.PAD)

        notebook = QTabWidget(self)
        opening_page = self._build_opening_page(notebook)
        inline_page = self._build_inline_page(notebook)
        notebook.addTab(opening_page, "  开头风格  ")
        notebook.addTab(inline_page, "  行内标签  ")
        layout.addWidget(notebook)

        # QTabWidget 的 sizeHint / minimumSizeHint 只按「当前页」计算，两个页面的高度需求
        # 不同（开头风格 7 行按钮，行内标签 4 行），切到较矮的页时面板会跟着缩矮，再切回来
        # 时较长的页就被裁掉末行。把两页的最小高度统一取最大值，切换标签页不再改变面板高度。
        pages = (opening_page, inline_page)
        need = max(page.layout().minimumSize().height() for page in pages)
        for page in pages:
            page.setMinimumHeight(need)

    # ================================================================ 开头风格

    def _build_opening_page(self, parent) -> QWidget:
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setSpacing(theme.GAP)

        layout.addWidget(
            theme.hint(
                page,
                "点击后写入合成文本最开头，形如 (风格1 风格2)正文；再次点击同一项即移除。",
                wrap=True,
            )
        )

        grid = QGridLayout()
        grid.setSpacing(2)
        for row, (group_name, styles) in enumerate(catalog.OPENING_STYLES):
            self._fill_row(page, grid, row, group_name, styles, self._on_opening_style)
        layout.addLayout(grid)
        layout.addStretch(1)
        return page

    # ================================================================ 行内标签

    def _build_inline_page(self, parent) -> QWidget:
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setSpacing(theme.GAP)

        layout.addWidget(
            theme.hint(
                page,
                "点击后插入到合成文本的光标位置，形如 [哽咽]；可对语气、情绪做细粒度控制。",
                wrap=True,
            )
        )

        grid = QGridLayout()
        grid.setSpacing(2)
        for row, (group_name, tags) in enumerate(catalog.INLINE_TAGS):
            self._fill_row(page, grid, row, group_name, tags, self._on_inline_tag)
        layout.addLayout(grid)
        layout.addStretch(1)
        return page

    # ================================================================ 对外

    # ================================================================ 内部

    def _fill_row(
        self, page: QWidget, grid: QGridLayout, row: int, group_name: str, items: list[str], command
    ) -> None:
        """一组标签占一行：最左是组名，右侧平铺按钮。"""
        label = theme.hint(page, group_name)
        label.setMinimumWidth(_LABEL_PX)
        grid.addWidget(label, row, 0, Qt.AlignLeft)

        for index, item in enumerate(items):
            button = QPushButton(item, page)
            button.setMinimumWidth(_BUTTON_PX)
            button.clicked.connect(lambda _checked=False, value=item: command(value))
            grid.addWidget(
                button,
                row + index // _COLUMNS,
                1 + index % _COLUMNS,
            )
