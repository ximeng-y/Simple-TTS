"""合成结果落盘。

合成的音频一律先写进固定的临时目录（`state.temp_output_dir()`），再由用户按需
点「保存」拷进保存目录。两处的分工：

- 临时目录：自动清理，只留最新的若干条（见 `prune`），先进先出
- 保存目录：用户明确要留下的东西，只增不减，本模块的清理逻辑一概不碰

文件名模式里的可用变量与界面提示一一对应：

    {ts}     时间戳，形如 20260927-153012
    {voice}  音色名（预置音色名 / 音色设计 / 音色复刻）
    {model}  模型 id
    {index}  序号，从 1 开始；同名文件已存在时自动递增

扩展名不由模式决定：模式只负责文件名主体，扩展名一律由这里按当前音频格式
追加。用户若在模式里自己写了 .wav，它也只是一段普通文字（后果是出现
`xxx.wav.wav`）—— 不去猜测哪一段是用户写的扩展名，就不会吃掉 `mimo-v2.5-tts`
里 `.5-tts` 这类带点的名字。

同名文件默认自动改名而不覆盖；save_audio 的 on_conflict 参数可接管这一决策
（见该函数的说明）。copy_audio 拷的是已经落盘的文件，名字已定，只做改名去重。
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable
from datetime import datetime

# Windows 文件名禁用字符，以及控制字符
_ILLEGAL_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
# 模式里可用的占位符
_PLACEHOLDERS = ("ts", "voice", "model", "index")

# prune 认定为合成产物、可以清理的扩展名。只认这两种：临时目录里若混进
# 别的文件（用户手放的东西、编辑器残留），一律不碰。
AUDIO_EXTENSIONS = (".wav", ".mp3")

# 同名文件已存在时，询问回调可返回的三种处置
CONFLICT_OVERWRITE = "overwrite"  # 覆盖旧文件，不再改名
CONFLICT_RENAME = "rename"  # 走默认的 _2、_3 逻辑
CONFLICT_CANCEL = "cancel"  # 放弃本次保存


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
    on_conflict: Callable[[str], str] | None = None,
) -> str | None:
    """把音频写入目录，返回实际落盘的完整路径；用户取消保存时返回 None。

    同名文件默认不覆盖也不询问：模式里带 {index} 时递增序号，不带时在扩展名前
    追加 _2、_3，直到找到空位。若传了 on_conflict，则在发现同名时把已占用的
    路径交给它，由它返回 CONFLICT_OVERWRITE / CONFLICT_RENAME / CONFLICT_CANCEL
    决定怎么处理 —— 只问一次，用户选了「另存为」就不再反复弹窗。
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
    if on_conflict is not None and os.path.exists(path):
        decision = on_conflict(path)
        if decision == CONFLICT_CANCEL:
            return None
        if decision == CONFLICT_OVERWRITE:
            pass  # 直接用这个名字，下面的 os.replace 会覆盖旧文件
        else:
            while os.path.exists(path):
                index += 1
                path = os.path.join(directory, candidate(index))
    else:
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


def copy_audio(
    source: str,
    directory: str,
    *,
    on_conflict: Callable[[str], str] | None = None,
) -> str | None:
    """把已落盘的音频拷进目录，返回副本路径；用户取消保存时返回 None。

    与 save_audio 是两件事：那边是「一段字节该叫什么名字」，这边名字已经定了
    （就是临时文件的名字），只做改名去重，因此不涉及文件名模式。同名处置沿用
    save_audio 那一套常量与回调语义（覆盖 / 另存为副本 / 取消），由调用方决定
    要不要问 —— 拷的是用户自己刚听过的那一份，问不问都能讲得通。
    """
    directory = directory or "."
    os.makedirs(directory, exist_ok=True)

    name = os.path.basename(source)
    stem, suffix = os.path.splitext(name)
    target = os.path.join(directory, name)
    if on_conflict is not None and os.path.exists(target):
        decision = on_conflict(target)
        if decision == CONFLICT_CANCEL:
            return None
        if decision != CONFLICT_OVERWRITE:
            seq = 1
            while os.path.exists(target):
                seq += 1
                target = os.path.join(directory, f"{stem}_{seq}{suffix}")
    else:
        seq = 1
        while os.path.exists(target):
            seq += 1
            target = os.path.join(directory, f"{stem}_{seq}{suffix}")

    # 先拷到临时文件再改名，与 save_audio 同一招：中途失败不留半截音频
    temp_path = target + ".part"
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, target)
    except OSError:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    return target


def prune(directory: str, limit: int, *, keep: tuple[str, ...] = ()) -> list[str]:
    """把目录里的音频删到只剩最新 limit 条，返回被删掉的路径。

    limit 为 0 或不大于 0 表示不限制，直接返回空列表。所谓「最旧」按文件的
    修改时间排，不看文件名 —— 文件名模式是用户可改的，拿它排序未必能得到
    用户心里的先后。

    两处不删：
      - 非音频扩展名（AUDIO_EXTENSIONS 之外）与 .part 中间文件，不做清理
      - keep 里列出的路径，即正在播放或刚合成出来的那一份 —— MCI 占着文件时
        删也删不掉，删了还会让「保存」按钮指向一个不存在的文件

    条数是「目录里一共留几条」，keep 保住的那份也占名额 —— 实际调用时 keep 传的
    就是刚生成、最新的一份，它在排序里本就排在最前，于是清完恰好是 limit 条
    （limit=10 就是留 10 条）。若 keep 指的是一个本会被清掉的旧文件，它会越过
    上限留下，目录里因此可能多出这一条：宁可多留一个正在用的文件，也不要把它
    从「保存」按钮底下删掉。

    删除失败（被占用、只读）静默跳过：临时目录的清理不该打断合成流程，
    下次合成还会再清一遍。
    """
    if limit <= 0:
        return []

    try:
        names = os.listdir(directory)
    except OSError:
        return []

    protected = {os.path.normcase(os.path.abspath(item)) for item in keep}
    entries: list[tuple[float, str]] = []
    for name in names:
        if not name.lower().endswith(AUDIO_EXTENSIONS):
            continue
        path = os.path.join(directory, name)
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            continue
        entries.append((stamp, path))

    # 新的在前：前 limit 条留下，其余清掉
    entries.sort(key=lambda item: item[0], reverse=True)
    removed: list[str] = []
    for _stamp, path in entries[limit:]:
        if os.path.normcase(os.path.abspath(path)) in protected:
            continue
        try:
            os.remove(path)
        except OSError:
            continue
        removed.append(path)
    return removed
