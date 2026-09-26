"""中栏文本区：风格指令 / 音色描述 + 合成文本。

对应文档里的两条消息：
  - user 消息（自然语言控制）-> 上面的「风格指令 / 音色描述」框
  - assistant 消息（待合成文本）-> 下面的「合成文本」框

注：多行文本编辑在 Tk 里只有经典 tk.Text 这一个原语，ttk 没有对应控件，
    此处与菜单栏一样属于必要例外。
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk

from .. import catalog
from . import theme

# 开头的风格标签，形如 (风格1 风格2)正文，括号支持 () （） []
_OPENING_RE = re.compile(r"^[ \t]*[（(\[]\s*([^）)\]]*?)\s*[）)\]]")

# 中文播报速度的粗略估计，仅用于界面上显示一个数量级
_SECONDS_PER_CHAR = 0.18


class TextPanel(ttk.Frame):
    def __init__(self, parent, on_text_change) -> None:
        super().__init__(parent, padding=(theme.PAD_L, theme.PAD, theme.PAD, theme.PAD))
        self._on_text_change = on_text_change
        self._model = catalog.MODELS[0]

        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)  # 合成文本框吃掉多余高度

        self._build_style_prompt()
        self._build_text_area()
        self.refresh_labels()
        self._refresh_counter()

    # ================================================================ 构建

    def _build_style_prompt(self) -> None:
        head = ttk.Frame(self)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)

        self._style_label = ttk.Label(head, text="风格指令", style="Title.TLabel")
        self._style_label.grid(row=0, column=0, sticky="w")

        ttk.Button(head, text="插入导演模式框架", command=self.insert_director_template).grid(
            row=0, column=1, sticky="e"
        )

        self._style_hint = ttk.Label(self, style="Hint.TLabel", anchor="w", justify="left")
        self._style_hint.grid(row=1, column=0, sticky="ew", pady=(2, theme.GAP))

        self.style_text = tk.Text(
            self, height=5, wrap="word", undo=True, relief="solid", borderwidth=1
        )
        self.style_text.grid(row=2, column=0, sticky="ew")
        self.style_text.bind("<KeyRelease>", lambda _e: self._on_text_change())

    def _build_text_area(self) -> None:
        head = ttk.Frame(self)
        head.grid(row=3, column=0, sticky="ew", pady=(theme.PAD, 2))
        head.columnconfigure(0, weight=1)

        ttk.Label(head, text="合成文本", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self._counter = ttk.Label(head, text="", style="Hint.TLabel")
        self._counter.grid(row=0, column=1, sticky="e")

        holder = ttk.Frame(self)
        holder.grid(row=4, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)

        self.text = tk.Text(
            holder, height=10, wrap="word", undo=True, relief="solid", borderwidth=1
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)
        self.text.bind("<KeyRelease>", self._handle_text_edit)

    # ================================================================ 模型联动

    def set_model(self, model: dict) -> None:
        """切换模型：同一个框在「风格指令（可选）」与「音色描述（必填）」之间换文案。"""
        self._model = model
        self.refresh_labels()

    def refresh_labels(self) -> None:
        if self._model["requires_style_prompt"]:
            self._style_label.configure(text="音色描述（必填）")
            self._style_hint.configure(
                text="这段文字即音色设计描述，同时作为 user 消息传入。写 1-4 句核心特征即可，"
                "不要写混响、回声、EQ 等后期处理描述。"
            )
        else:
            self._style_label.configure(text="风格指令（可选）")
            self._style_hint.configure(
                text="用自然语言描述想要的语气与风格，作为 user 消息传入，内容不会出现在合成的语音中；"
                "也可用来写对话历史。"
            )

    # ================================================================ 风格指令框

    def get_style_prompt(self) -> str:
        return self.style_text.get("1.0", "end-1c")

    def set_style_prompt(self, value: str) -> None:
        self.style_text.delete("1.0", "end")
        self.style_text.insert("1.0", value)

    def insert_director_template(self) -> None:
        """插入导演模式的骨架：从角色 / 场景 / 指导三个维度刻画声线。"""
        if self.get_style_prompt().strip():
            self.style_text.insert("end", "\n\n" + catalog.DIRECTOR_TEMPLATE)
        else:
            self.style_text.insert("1.0", catalog.DIRECTOR_TEMPLATE)

    # ================================================================ 合成文本框

    def get_text(self) -> str:
        return self.text.get("1.0", "end-1c")

    def set_text(self, value: str) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self._refresh_counter()

    def insert_inline(self, tag: str) -> None:
        """在光标处插入行内音频标签。"""
        self.text.insert("insert", f"[{tag}]")
        self.text.focus_set()
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

    def _handle_text_edit(self, _event) -> None:
        self._refresh_counter()
        self._on_text_change()

    def _refresh_counter(self) -> None:
        count = len(self.get_text())
        self._counter.configure(text=f"{count} 字 / 约 {count * _SECONDS_PER_CHAR:.1f} 秒")
