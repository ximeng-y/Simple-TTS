"""应用状态。

配置在内存中就是这里的一份 AppState；退出时由 App 写进
``userdata/settings.json``（读写见 storage.py），下次启动读回。
但各模型草稿只在内存里，不落盘。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

from . import catalog


def _program_dir() -> str:
    """程序所在目录，即 userdata 的落点。

    冻结成 exe 后 `__file__` 指向 PyInstaller 解出来的临时目录（onefile 模式下
    随进程结束被删除，写进去等于丢），只有 `sys.executable` 才是 exe 自身的
    位置，因此打包后以它为准；源码运行时就取包目录的上一级（项目根）。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def userdata_dir() -> str:
    """程序自用的数据目录。所有需要落盘的东西都收敛在这里。

    跟着程序走而不是跟着系统用户目录走，是为了让整个软件连同产物都在一个
    文件夹内，拷贝/删除互不影响。里面目前有三样：output/ 放合成产物的临时
    文件，save/ 放用户保存下来的音频，settings.json 放配置。目录按需创建
    （见 output.save_audio、storage.save），不在这里做任何磁盘操作。
    """
    return os.path.join(_program_dir(), "userdata")


def settings_path() -> str:
    """配置文件的完整路径。"""
    return os.path.join(userdata_dir(), "settings.json")


def temp_output_dir() -> str:
    """合成产物的临时落脚点，固定不变。

    合成的音频一律先落这里，再由用户按需「保存」到 save_dir。临时目录按
    temp_limit 做先入先出的清理（见 output.prune），因此它既不入配置，
    也不出现在界面上 —— 换个位置对用户没有意义，反而多一个填错的机会。
    """
    return os.path.join(userdata_dir(), "output")


def _default_save_dir() -> str:
    return os.path.join(userdata_dir(), "save")


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
    """全局配置。除 drafts 外均对应「设置」页里的项，且都写进配置文件。

    字段名即配置文件里的键名，落盘范围由 storage.py 的两份键清单决定：
    这里新加字段后要在那边登记，否则读得到、存不下。
    """

    # ---- 供应商与模型
    # 当前启用的供应商。接入第二家后由「设置 → 供应商」页切换；
    # 该值决定顶部模型下拉列出哪些模型，也决定设置页 API KEY 页默认停在哪个标签。
    provider_id: str = catalog.DEFAULT_PROVIDER_ID
    # 当前模型 id。按模型 id 而非下标存储，换供应商后仍能正确回落到该供应商的第一个模型。
    model_id: str = catalog.PROVIDERS[0]["models"][0]["id"]

    # ---- 输出
    # 用户点击「保存」时音频的落点，不受临时文件上限约束。
    # 合成的产物本身先落在固定的 userdata/output（见 temp_output_dir），
    # 那里按 temp_limit 先入先出地清理，与这里互不影响。
    save_dir: str = field(default_factory=_default_save_dir)
    # 临时目录保留的条数上限，0 表示不限制。超出后每次合成成功时删掉最旧的几条。
    temp_limit: int = 10
    # 扩展名不写进模式：模式只拼文件名主体，扩展名一律由落盘时按 audio_format
    # 追加，避免模式里的 .wav 与实际内容不符。可用变量见 output.build_filename。
    filename_pattern: str = "{ts}_{voice}"
    audio_format: str = "wav"
    auto_play: bool = True
    keep_history: bool = False
    confirm_overwrite: bool = True

    # ---- API Key：按供应商 id 各存一份，切换供应商不会互相覆盖。
    # 落盘时整份经 DPAPI 加密，不以明文写入 settings.json（见 storage.py）
    api_keys: dict[str, str] = field(default_factory=dict)

    # ---- 各模型的输入草稿。唯一不落盘的一项：属于正在写的内容而非配置
    drafts: dict[str, ModelDraft] = field(default_factory=dict)

    @property
    def provider(self) -> dict:
        """当前供应商的静态定义。"""
        return catalog.provider_by_id(self.provider_id)

    @property
    def api_base(self) -> str:
        """当前供应商的接口基地址。基地址由供应商硬编码决定，界面不可修改。"""
        return self.provider["base_url"]

    @property
    def api_key(self) -> str:
        return self.api_keys.get(self.provider_id, "")

    @property
    def model(self) -> dict:
        """当前模型的静态定义。"""
        return catalog.model_by_id(self.provider_id, self.model_id)

    def draft(self, model_id: str | None = None) -> ModelDraft:
        """取（必要时新建）指定模型的草稿；不传则取当前模型的。"""
        key = model_id or self.model_id
        if key not in self.drafts:
            self.drafts[key] = ModelDraft()
        return self.drafts[key]
