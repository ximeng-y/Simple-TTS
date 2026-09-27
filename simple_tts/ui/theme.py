"""界面外观：字体探测、间距常量与两个标签工厂。

中文界面若落到不含中文字形的字体上会显示成方框，因此显式挑一个系统中文字体，
通过 QApplication.setFont 统一应用。

Qt6 在 Windows 上默认使用 windows11 原生风格（跟随系统浅色/深色），
不需要像 Tk 那样手动挑主题。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

# 间距常量，避免各控件各写各的魔法数字
PAD = 8
PAD_L = 12
GAP = 6
# 右侧配置区（音色 / 输出 并排），越宽左侧文本区越窄
RIGHT_COL_W = 440

# 依次尝试，取第一个系统里存在的
_PREFERRED_FONTS = ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Tahoma")

# 提示文字与标题文字的字号（基准字号为 9）
_TITLE_POINT_SIZE = 10

_HINT_STYLE = "color: #666666;"


def pick_font_family() -> str:
    """返回系统中可用的首选中文字体族名。"""
    available = set(QFontDatabase.families())
    for family in _PREFERRED_FONTS:
        if family in available:
            return family
    return QFont().defaultFamily()


def apply(app) -> None:
    """选定字体并设置全局样式。需在创建控件之前调用。"""
    app.setFont(QFont(pick_font_family(), 9))


def hint(parent: QWidget, text: str = "", wrap: bool = False) -> QLabel:
    """灰色小字说明，对应原 ttk 的 Hint.TLabel。

    换行提示在窄列里可能把单行文本撑得很宽（QLabel 换行前不折行）。
    水平策略置为 Ignored 后只按可用宽度折行，不参与撑大布局。

    但宽高比 Ignored 更麻烦：QLabel 折行后的真实高度要由 heightForWidth 现算，
    而 QSizePolicy 的两个参数构造会把 heightForWidth 重置为 False，布局便只按
    未折行的一行高度（sizeHint）分配，文字被下一行盖住。因此显式打开。
    """
    label = QLabel(text, parent)
    label.setStyleSheet(_HINT_STYLE)
    label.setWordWrap(wrap)
    label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
    if wrap:
        policy = QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        label.setSizePolicy(policy)
    return label


def title(parent: QWidget, text: str = "", wrap: bool = False) -> QLabel:
    """加粗小节标题，对应原 ttk 的 Title.TLabel。"""
    label = QLabel(text, parent)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    label.setWordWrap(wrap)
    label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
    return label
