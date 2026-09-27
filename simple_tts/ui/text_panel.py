"""中栏文本区：风格指令 / 音色描述 + 合成文本。

对应文档里的两条消息：
  - user 消息（自然语言控制）-> 上面的「风格指令 / 音色描述」框
  - assistant 消息（待合成文本）-> 下面的「合成文本」框
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import catalog
from . import theme

# 开头的风格标签，形如 (风格1 风格2)正文，括号支持 () （） []
_OPENING_RE = re.compile(r"^[ \t]*[（(\[]\s*([^）)\]]*?)\s*[）)\]]")

# 中文播报速度的粗略估计，仅用于界面上显示一个数量级
_SECONDS_PER_CHAR = 0.18


class TextPanel(QWidget):
    def __init__(self, parent, on_text_change) -> None:
        super().__init__(parent)
        self._on_text_change = on_text_change
        self._model = catalog.PROVIDERS[0]["models"][0]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.PAD_L, theme.PAD, theme.PAD, theme.PAD)
        layout.setSpacing(theme.GAP)

        self._build_style_prompt(layout)
        self._build_text_area(layout)
        self.refresh_labels()
        self._refresh_counter()

    # ================================================================ 构建

    def _build_style_prompt(self, parent_layout: QVBoxLayout) -> None:
        head = QHBoxLayout()
        head.setSpacing(theme.GAP)
        self._style_label = theme.title(self, "风格指令")
        head.addWidget(self._style_label)
        head.addStretch(1)

        template_button = QPushButton("插入导演模式框架", self)
        template_button.clicked.connect(self.insert_director_template)
        head.addWidget(template_button)
        parent_layout.addLayout(head)

        self._style_hint = theme.hint(self, "", wrap=True)
        parent_layout.addWidget(self._style_hint)

        self.style_text = QPlainTextEdit(self)
        self.style_text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.style_text.setFixedHeight(theme.TEXT_BOX_H)
        self.style_text.textChanged.connect(self._on_text_change)
        parent_layout.addWidget(self.style_text)

    def _build_text_area(self, parent_layout: QVBoxLayout) -> None:
        head = QHBoxLayout()
        head.setSpacing(theme.GAP)
        head.addWidget(theme.title(self, "合成文本"))
        head.addWidget(theme.hint(self, "在下方填写要让AI读出的音频内容"))
        head.addStretch(1)

        self._counter = theme.hint(self, "")
        head.addWidget(self._counter)
        parent_layout.addLayout(head)

        self.text = QPlainTextEdit(self)
        self.text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        # 中栏被压缩时只压这个框（上方描述框已固定高度），压到与描述框齐平为止
        self.text.setMinimumHeight(theme.TEXT_BOX_H)
        self.text.textChanged.connect(self._handle_text_edit)
        parent_layout.addWidget(self.text, 1)

    # ================================================================ 模型联动

    def set_model(self, model: dict) -> None:
        """切换模型：同一个框在「风格指令（可选）」与「音色描述（必填）」之间换文案。"""
        self._model = model
        self.refresh_labels()

    def refresh_labels(self) -> None:
        if self._model["requires_style_prompt"]:
            self._style_label.setText("音色描述（必填）")
            self._style_hint.setText(
                "这段文字即音色设计描述，同时作为 user 消息传入。写 1-4 句核心特征即可，"
                "不要写混响、回声、EQ 等后期处理描述。"
            )
        else:
            self._style_label.setText("风格指令（可选）")
            self._style_hint.setText(
                "用自然语言描述想要的语气与风格，作为 user 消息传入，内容不会出现在合成的语音中；"
                "也可用来写对话历史。"
            )

    # ================================================================ 风格指令框

    def get_style_prompt(self) -> str:
        return self.style_text.toPlainText()

    def set_style_prompt(self, value: str) -> None:
        self._set_plain_text(self.style_text, value)

    def insert_director_template(self) -> None:
        """插入导演模式的骨架：从角色 / 场景 / 指导三个维度刻画声线。"""
        if self.get_style_prompt().strip():
            self.style_text.appendPlainText("\n" + catalog.DIRECTOR_TEMPLATE)
        else:
            self._set_plain_text(self.style_text, catalog.DIRECTOR_TEMPLATE)

    # ================================================================ 合成文本框

    def get_text(self) -> str:
        return self.text.toPlainText()

    def set_text(self, value: str) -> None:
        self._set_plain_text(self.text, value)
        self._refresh_counter()

    def insert_inline(self, tag: str) -> None:
        """在光标处插入行内音频标签。"""
        self.text.textCursor().insertText(f"[{tag}]")
        self.text.setFocus()
        self._refresh_counter()

    # ---- 开头风格标签

    def apply_opening(self, style: str) -> bool:
        """把风格并入文本开头的括号标签，返回操作后是否处于唱歌模式。

        规则（来自文档）：
          - 普通风格可以多个共存于同一对括号内，分隔符不限，此处统一用空格
          - 唱歌必须独占文本最开头：它出现时清掉其它风格，反之亦然
          - 再次点击已存在的风格即移除；括号内清空则整个去掉
        """
        text = self.get_text()
        match = _OPENING_RE.match(text)
        if match:
            existing = match.group(1).split()
            rest = text[match.end():]
        else:
            existing = []
            rest = text

        if style == catalog.SING_STYLE:
            styles = [] if existing == [catalog.SING_STYLE] else [style]
        elif catalog.SING_STYLE in existing:
            # 从唱歌切回普通风格：唱歌不能与其它风格共存
            styles = [style]
        elif style in existing:
            styles = [item for item in existing if item != style]
        else:
            styles = existing + [style]

        prefix = f"({' '.join(styles)})" if styles else ""
        self.set_text(prefix + rest)
        return catalog.SING_STYLE in styles

    def set_sing(self, enabled: bool) -> None:
        """供「唱歌模式」复选框调用。"""
        if enabled != self.is_singing():
            self.apply_opening(catalog.SING_STYLE)

    def is_singing(self) -> bool:
        match = _OPENING_RE.match(self.get_text())
        return bool(match) and match.group(1).strip() == catalog.SING_STYLE

    # ================================================================ 内部

    def _set_plain_text(self, edit: QPlainTextEdit, value: str) -> None:
        """程序化赋值：屏蔽 textChanged，只在编辑框内容变化时才发出通知。

        这样才与原 Tk 版「set_text 不触发 on_text_change」的语义一致，
        否则 App._sync_sing_ui 会被反复回调。
        """
        if edit.toPlainText() == value:
            return
        edit.blockSignals(True)
        edit.setPlainText(value)
        edit.blockSignals(False)

    def _handle_text_edit(self, _event=None) -> None:
        self._refresh_counter()
        self._on_text_change()

    def _refresh_counter(self) -> None:
        count = len(self.get_text())
        self._counter.setText(f"{count} 字 / 约 {count * _SECONDS_PER_CHAR:.1f} 秒")
