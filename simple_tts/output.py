"""合成结果落盘。

文件名模式里的可用变量与界面提示一一对应：

    {ts}     时间戳，形如 20260927-153012
    {voice}  音色名（预置音色名 / 音色设计 / 音色复刻）
    {model}  模型 id
    {index}  序号，从 1 开始；同名文件已存在时自动递增

扩展名不由模式决定，一律跟随当前音频格式 —— 模式里写死的 .wav 在切到 mp3 时
会与实际文件内容不符，因此这里以格式为准覆写扩展名。
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


def _with_extension(name: str, audio_format: str) -> str:
    """把扩展名统一成当前音频格式。"""
    stem, _ext = os.path.splitext(name)
    return f"{stem}.{audio_format.lstrip('.') or 'wav'}"


def build_filename(
    pattern: str,
    *,
    voice_name: str,
    model_id: str,
    audio_format: str,
    index: int = 1,
) -> str:
    """按模式拼出一个安全的基础文件名（不含去重后缀）。"""
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
    return _with_extension(sanitize(result), audio_format)


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
    index = 1
    filename = build_filename(
        pattern,
        voice_name=voice_name,
        model_id=model_id,
        audio_format=audio_format,
        index=index,
    )
    path = os.path.join(directory, filename)

    # uses_index 时序号本身就能腾出位置，只需递增 {index}；
    # 否则保持基础名不变，在扩展名前追加去重后缀。
    while os.path.exists(path):
        index += 1
        if uses_index:
            path = os.path.join(
                directory,
                build_filename(
                    pattern,
                    voice_name=voice_name,
                    model_id=model_id,
                    audio_format=audio_format,
                    index=index,
                ),
            )
        else:
            stem, ext = os.path.splitext(filename)
            path = os.path.join(directory, f"{stem}_{index}{ext}")

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
