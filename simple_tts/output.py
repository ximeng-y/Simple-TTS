"""合成结果落盘。

文件名模式里的可用变量与界面提示一一对应：

    {ts}     时间戳，形如 20260927-153012
    {voice}  音色名（预置音色名 / 音色设计 / 音色复刻）
    {model}  模型 id
    {index}  序号，从 1 开始；同名文件已存在时自动递增

扩展名不由模式决定：模式只负责文件名主体，扩展名一律由这里按当前音频格式
追加。用户若在模式里自己写了 .wav，它也只是一段普通文字（后果是出现
`xxx.wav.wav`）—— 不去猜测哪一段是用户写的扩展名，就不会吃掉 `mimo-v2.5-tts`
里 `.5-tts` 这类带点的名字。
"""

from __future__ import annotations

import os
import re
from datetime import datetime

# Windows 文件名禁用字符，以及控制字符
_ILLEGAL_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
# 模式里可用的占位符
_PLACEHOLDERS = ("ts", "voice", "model", "index")


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def sanitize(name: str) -> str:
    """去掉文件名里的非法字符与首尾空白/点。

    音色名来自下拉框（安全）与样本文件名（用户自取，可能含非法字符），
    统一在这里处理，避免各调用点各写一套。
    """
    cleaned = _ILLEGAL_RE.sub("_", name).strip().strip(".")
    return cleaned or "unnamed"


def _suffix(audio_format: str) -> str:
    """当前音频格式对应的扩展名（不含点）。"""
    return audio_format.lstrip(".") or "wav"


def _render_stem(
    pattern: str,
    *,
    voice_name: str,
    model_id: str,
    index: int = 1,
) -> str:
    """按模式拼出文件名主体（不含扩展名）。"""
    values = {
        "ts": timestamp_slug(),
        "voice": sanitize(voice_name or "voice"),
        "model": sanitize(model_id or "model"),
        "index": str(index),
    }
    result = pattern or "{ts}_{voice}"
    for key in _PLACEHOLDERS:
        result = result.replace("{" + key + "}", values[key])
    # 未知占位符原样留着会变成字面量，统一按原名处理更不意外
    result = re.sub(r"\{[^{}]*\}", "", result)
    return sanitize(result)


def build_filename(
    pattern: str,
    *,
    voice_name: str,
    model_id: str,
    audio_format: str,
    index: int = 1,
) -> str:
    """按模式拼出一个安全的基础文件名（不含去重后缀）。"""
    stem = _render_stem(pattern, voice_name=voice_name, model_id=model_id, index=index)
    return f"{stem}.{_suffix(audio_format)}"


def save_audio(
    audio: bytes,
    directory: str,
    pattern: str,
    *,
    voice_name: str,
    model_id: str,
    audio_format: str,
) -> str:
    """把音频写入目录，返回实际落盘的完整路径。

    同名文件不弹窗询问，也不覆盖：模式里带 {index} 时递增序号，
    不带时在扩展名前追加 _2、_3，直到找到空位。
    """
    directory = directory or "."
    os.makedirs(directory, exist_ok=True)

    uses_index = "{index}" in (pattern or "")
    suffix = _suffix(audio_format)
    index = 1
    # 不含序号的渲染结果只算一次，避免时间戳在循环里跨秒变化
    base_stem = _render_stem(pattern, voice_name=voice_name, model_id=model_id)

    def candidate(seq: int) -> str:
        """第 seq 次尝试的文件名。扩展名始终由这里拼，不解析名字里已有的点。"""
        if not uses_index and seq > 1:
            # 模式里没有 {index}：保持主体不变，在扩展名前追加去重后缀
            return f"{base_stem}_{seq}.{suffix}"
        stem = base_stem if not uses_index else _render_stem(
            pattern, voice_name=voice_name, model_id=model_id, index=seq
        )
        return f"{stem}.{suffix}"

    path = os.path.join(directory, candidate(index))
    while os.path.exists(path):
        index += 1
        path = os.path.join(directory, candidate(index))

    # 先写临时文件再改名：中途失败不会留下一个内容不完整的音频文件
    temp_path = path + ".part"
    try:
        with open(temp_path, "wb") as handle:
            handle.write(audio)
        os.replace(temp_path, path)
    except OSError:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    return path
