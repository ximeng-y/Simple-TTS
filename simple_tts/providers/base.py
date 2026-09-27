"""TTS 服务商的抽象基类。

实现类只依赖标准库与 catalog（纯数据），不 import 任何 Qt 模块 ——
「GUI 与后端严格分层」这条约束在这里是可见的：界面层只拿到 bytes。
"""

from __future__ import annotations

import abc


class SynthesisError(RuntimeError):
    """合成失败。

    消息是直接给用户看的中文，界面层原样弹在对话框里即可，
    不需要（也不应该）再去解析服务端返回的原始报文。
    """


class TTSProvider(abc.ABC):
    """文本转语音服务商的统一接口。"""

    @abc.abstractmethod
    def synthesize(self, text: str, **params) -> bytes:
        """把 text 合成为一段音频，返回该音频文件的完整字节。

        params 由各实现自行约定（模型、音色、风格指令、输出格式等）。
        取 wav 时服务端返回成型 WAV 文件，取 mp3 时返回成型 MP3 文件，直接落盘即可。
        失败时抛 SynthesisError。
        """
        raise NotImplementedError
