"""TTS 服务商的抽象基类。

本版本（v0.1.0 前端形态）不提供任何实现，UI 层也不 import 本模块 ——
保持「GUI 与后端严格分层」这条约束在代码里可见。

后续接入 MiMo 时新增 mimo.py：

    class MiMoProvider(TTSProvider):
        def synthesize(self, text, *, model, voice=None, style_prompt="",
                       audio_format="wav", optimize_text_preview=False, **kw) -> bytes:
            # 用标准库 urllib 调 Chat Completions 非流式接口
            # 响应中 choices[0].message.audio.data 为 base64 编码的完整音频
            # base64.b64decode(...) 后即为可落盘的音频字节
"""

from __future__ import annotations

import abc


class TTSProvider(abc.ABC):
    """文本转语音服务商的统一接口。"""

    @abc.abstractmethod
    def synthesize(self, text: str, **params) -> bytes:
        """把 text 合成为一段音频，返回该音频文件的完整字节。

        params 由各实现自行约定（模型、音色、风格指令、输出格式等）。
        取 wav 时服务端返回成型 WAV 文件，直接落盘即可，无需自行补写文件头。
        """
        raise NotImplementedError
