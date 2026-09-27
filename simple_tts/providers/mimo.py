"""小米 MiMo 语音合成服务接入。

三个模型共用同一个 Chat Completions 风格的 endpoint，差别只在请求体：

- ``mimo-v2.5-tts``             ``audio.voice`` 传预置音色 id
- ``mimo-v2.5-tts-voicedesign`` 不传 ``audio.voice``，音色由 user 消息的文字描述决定
- ``mimo-v2.5-tts-voiceclone``  ``audio.voice`` 传 ``data:{mime};base64,<样本>``

只依赖标准库 base64/json/urllib，不引入 openai SDK，也不 import Qt。
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

from .. import catalog
from .base import SynthesisError, TTSProvider

# 音色复刻样本在 base64 之后的体积上限（文档要求）
_MAX_SAMPLE_B64 = catalog.MAX_SAMPLE_BYTES


def _decode_error_body(raw: bytes) -> str:
    """从错误响应体里尽力取出一句可读的说明。

    服务端风格是 OpenAI 兼容的 ``{"error": {"message": ...}}``，但错误路径下
    未必真是这个形状（网关可能直接返回 HTML），因此逐级兜底，取不到就回原始片段。
    """
    text = raw.decode("utf-8", errors="replace").strip()
    try:
        payload = json.loads(text)
    except ValueError:
        return text[:500]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str):
            return error
        for key in ("message", "detail", "msg"):
            if payload.get(key):
                return str(payload[key])
    return text[:500]


def _encode_sample(path: str) -> str:
    """把本地音频样本读成 ``data:audio/...;base64,...`` 形式的字符串。"""
    if not path:
        raise SynthesisError("音色复刻需要选择音频样本文件。")
    if not os.path.exists(path):
        raise SynthesisError(f"音频样本不存在：{path}")

    size = os.path.getsize(path)
    if size > _MAX_SAMPLE_B64:
        raise SynthesisError(f"音频样本 {size / 1024 / 1024:.1f}MB，超过 10MB 上限。")

    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return f"data:{catalog.sample_mime_for(path)};base64,{encoded}"


class MiMoProvider(TTSProvider):
    """mimo.mi.com 的语音合成接口。"""

    def __init__(self, base_url: str = "", chat_path: str = "") -> None:
        provider = catalog.PROVIDERS[0]
        self._base_url = (base_url or provider["base_url"]).rstrip("/")
        self._chat_path = chat_path or provider["chat_path"]

    # ---------------------------------------------------------------- 接口

    def synthesize(
        self,
        text: str,
        *,
        api_key: str,
        model: str,
        tone_source: str,
        audio_format: str = "wav",
        style_prompt: str = "",
        voice_id: str = "",
        sample_path: str = "",
        optimize_text_preview: bool = False,
    ) -> bytes:
        """合成一段音频，返回音频文件的完整字节。

        text 即 assistant 消息（待合成文本），其中的风格标签与行内标签由界面
        预先写进文本，这里原样透传，不做解析。
        """
        if not api_key.strip():
            raise SynthesisError("尚未填写 API Key，请在「设置 → API KEY」中填写。")

        audio: dict = {"format": audio_format}
        if tone_source == "preset":
            if not voice_id:
                raise SynthesisError("请选择一个预置音色。")
            audio["voice"] = voice_id
        elif tone_source == "clone":
            audio["voice"] = _encode_sample(sample_path)
        elif tone_source == "design":
            if not style_prompt.strip():
                raise SynthesisError("音色设计需要填写音色描述。")
        else:
            raise SynthesisError(f"未知的音色来源：{tone_source}")

        if optimize_text_preview:
            audio["optimize_text_preview"] = True

        payload = {
            "model": model,
            "messages": self._build_messages(text, style_prompt, tone_source),
            "audio": audio,
            # 一次性拿到完整音频后自行落盘、自行播放，不走流式接收
            "stream": False,
        }
        return self._post(payload, api_key)

    # ---------------------------------------------------------------- 内部

    @staticmethod
    def _build_messages(text: str, style_prompt: str, tone_source: str) -> list[dict]:
        """组装 user（风格指令 / 音色描述）与 assistant（待合成文本）两条消息。

        空消息会改变模型对上下文的判断，因此非复刻场景下空内容一律不发；
        复刻场景按文档示例保留空的 user 消息。
        """
        messages: list[dict] = []
        style_prompt = style_prompt.strip()
        if style_prompt or tone_source == "clone":
            messages.append({"role": "user", "content": style_prompt})
        if text.strip():
            messages.append({"role": "assistant", "content": text})
        return messages

    def _post(self, payload: dict, api_key: str) -> bytes:
        url = self._base_url + self._chat_path
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=catalog.REQUEST_TIMEOUT) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = _decode_error_body(exc.read())
            raise SynthesisError(f"服务端返回 {exc.code}：{detail}") from exc
        except urllib.error.URLError as exc:
            raise SynthesisError(f"无法连接服务端：{exc.reason}") from exc
        except TimeoutError as exc:
            raise SynthesisError("请求超时，请缩短文本后重试。") from exc

        return self._extract_audio(body)

    @staticmethod
    def _extract_audio(body: bytes) -> bytes:
        """从响应体里取出 base64 音频并解码。

        路径为 ``choices[0].message.audio.data``（非流式）。
        """
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise SynthesisError(
                f"无法解析服务端响应：{body[:200].decode('utf-8', errors='replace')}"
            ) from exc

        try:
            encoded = payload["choices"][0]["message"]["audio"]["data"]
        except (KeyError, IndexError, TypeError) as exc:
            # 结构对不上时多半是服务端把错误塞进了 choices，尽力取一句说明
            raise SynthesisError(f"响应中没有音频数据：{_decode_error_body(body)}") from exc

        if not encoded:
            raise SynthesisError("服务端返回了空的音频数据。")
        try:
            return base64.b64decode(encoded)
        except (ValueError, TypeError) as exc:
            raise SynthesisError("音频数据不是合法的 base64 编码。") from exc
