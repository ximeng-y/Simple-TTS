"""应用状态。

本版本仅做前端形态演示，全部配置只存在于内存中，退出即丢，不写入磁盘。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import catalog


def _default_output_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "Music", "SimpleTTS")


@dataclass
class ModelDraft:
    """单个模型各自保留的输入。

    三个模型的配置区内容不同，切换模型时若共用一份状态会互相污染，
    因此每个模型各存一份草稿，切回去时原样恢复。
    """

    # user 消息。预置音色/复刻场景下是可选的自然语言风格指令；
    # 音色设计场景下是必填的音色描述 —— 同一个字段，界面换文案。
    style_prompt: str = ""
    # assistant 消息，即待合成文本。
    text: str = ""
    # 预置音色场景：当前选中的 Voice ID。
    voice_id: str = "mimo_default"
    # 音色复刻场景：样本文件路径。
    sample_path: str = ""
    # 预置音色场景：唱歌模式（等价于在文本开头加 (唱歌) 标签）。
    sing: bool = False
    # 音色设计场景：optimize_text_preview，开启后可省略 assistant 消息。
    optimize_preview: bool = False


@dataclass
class AppState:
    """全局配置。除 drafts 外均对应「文件 → 设置」页里的项。"""

    model_id: str = catalog.MODELS[0]["id"]

    # ---- 输出
    output_dir: str = field(default_factory=_default_output_dir)
    filename_pattern: str = "{ts}_{voice}.wav"
    audio_format: str = "wav"
    auto_play: bool = True
    keep_history: bool = False
    confirm_overwrite: bool = True

    # ---- API
    api_base: str = catalog.DEFAULT_API_BASE
    api_key: str = ""

    # ---- 各模型的输入草稿
    drafts: dict[str, ModelDraft] = field(default_factory=dict)

    @property
    def model(self) -> dict:
        """当前模型的静态定义。"""
        return catalog.model_by_id(self.model_id)

    def draft(self, model_id: str | None = None) -> ModelDraft:
        """取（必要时新建）指定模型的草稿；不传则取当前模型的。"""
        key = model_id or self.model_id
        if key not in self.drafts:
            self.drafts[key] = ModelDraft()
        return self.drafts[key]
