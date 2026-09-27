"""配置落盘。

文件是 userdata/settings.json，一份完整快照：写入时整体覆盖（临时文件 + 原地
替换，与 output.py 写音频同一招），读取时逐项校验、不认的键直接忽略。

两类内容分开处理：

- 普通配置项：字符串、布尔值与非负整数，读回时按类型逐项过滤，类型不符的项
  当作没有，留着内存里的默认值 —— 配置文件被手改坏时最多丢几项设置，不至于
  起不来。
- API Key：不写明文。整份 key 表先用 JSON 序列化，再交给 Windows 的 DPAPI
  （CryptProtectData）用当前登录用户的凭据加密，最后以 base64 存成一行文本。
  于是同一台机器上换个 Windows 账户也解不开，把 userdata/ 整个拷到别的机器
  同样解不开 —— 这正是「密钥不是明文躺在磁盘上」要的效果。

加解密失败一律当作「没有密钥」处理：换过账户、拷过机器之后旧密文本来就打不开，
读出空密钥比抛异常更符合预期。DPAPI 用 ctypes 直接调 crypt32，不引入第三方库
（与 player.py 调 winmm 是同一路数）。
"""

from __future__ import annotations

import base64
import binascii
import ctypes
import json
import os
from ctypes import wintypes

from . import catalog

# 落盘的普通配置项。字段名即 JSON 键名，不另立一套键名免得两边对不上。
STR_KEYS = ("provider_id", "model_id", "save_dir", "filename_pattern", "audio_format")
BOOL_KEYS = ("auto_play", "keep_history", "confirm_overwrite")
# 整型配置项。读回时只认非负整数：负数条数上限没有意义，字符串 "10"
# 也不替它转 —— 与其余各项一样，类型不符就当作没写，留默认值。
INT_KEYS = ("temp_limit",)

# 密钥在文件里的键名。与普通项不同名，是为了让「密文被当成明文读出来」
# 这类错误没法悄悄发生。
SECRETS_KEY = "api_keys_encrypted"

# 音色复刻的样本路径、各模型草稿都不落盘：前者是随手选的临时文件，
# 后者是用户当下正在写的内容，都算不上配置（见 state.py）。

# ---------------------------------------------------------------- Windows DPAPI


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(_DataBlob),  # 待加密数据
    wintypes.LPCWSTR,  # 描述文本，留空
    ctypes.POINTER(_DataBlob),  # 附加熵，留空：只按当前用户加密
    ctypes.c_void_p,  # 保留
    ctypes.c_void_p,  # 提示用的 prompt 结构，留空
    wintypes.DWORD,  # flags
    ctypes.POINTER(_DataBlob),  # 密文输出
]
_crypt32.CryptProtectData.restype = wintypes.BOOL
_crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(_DataBlob),  # 密文
    ctypes.POINTER(wintypes.LPWSTR),  # 描述文本输出，不关心
    ctypes.POINTER(_DataBlob),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(_DataBlob),  # 明文输出
]
_crypt32.CryptUnprotectData.restype = wintypes.BOOL
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p


def _blob(data: bytes) -> _DataBlob:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _take(blob: _DataBlob) -> bytes:
    """取走 DPAPI 分配的输出缓冲并交给 LocalFree 释放 —— 内存归它管，必须还回去。"""
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        _kernel32.LocalFree(blob.pbData)


def protect(plaintext: bytes) -> bytes:
    """按当前登录用户加密一段字节。"""
    out = _DataBlob()
    if not _crypt32.CryptProtectData(
        ctypes.byref(_blob(plaintext)), None, None, None, None, 0, ctypes.byref(out)
    ):
        raise OSError(ctypes.get_last_error(), "CryptProtectData 失败")
    return _take(out)


def unprotect(ciphertext: bytes) -> bytes:
    """解密 protect() 的结果。换了 Windows 账户或换了机器时这里会失败。"""
    out = _DataBlob()
    if not _crypt32.CryptUnprotectData(
        ctypes.byref(_blob(ciphertext)), None, None, None, None, 0, ctypes.byref(out)
    ):
        raise OSError(ctypes.get_last_error(), "CryptUnprotectData 失败")
    return _take(out)


# ---------------------------------------------------------------- 密钥字段


def _pack_keys(api_keys: dict[str, str]) -> str:
    """key 表 -> 一行 base64 密文；没有密钥或加密不可用时返回空串。"""
    secrets = {pid: key for pid, key in api_keys.items() if key}
    if not secrets:
        return ""
    try:
        raw = json.dumps(secrets, ensure_ascii=False).encode("utf-8")
        return base64.b64encode(protect(raw)).decode("ascii")
    except OSError:
        # 加密不可用（被安全软件拦下、凭据存储异常等）。此时宁可不写这一项，
        # 也不退回明文：本次运行内存里的 key 仍可用，只是这次没存下来。
        return ""


def _unpack_keys(text: object) -> dict[str, str]:
    """密文 -> key 表；任何解不开的情况都返回空表。"""
    if not isinstance(text, str) or not text:
        return {}
    try:
        raw = unprotect(base64.b64decode(text, validate=True))
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, binascii.Error, UnicodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


# ---------------------------------------------------------------- 读写


def _to_dict(state) -> dict:
    data: dict[str, object] = {
        key: getattr(state, key) for key in STR_KEYS + BOOL_KEYS + INT_KEYS
    }
    data[SECRETS_KEY] = _pack_keys(state.api_keys)
    return data


def _apply(state, data: dict) -> None:
    """把文件里的值读进 state，逐项校验。

    顺序上先定供应商与模型：切换供应商后旧模型 id 多半不存在，
    这里按 catalog 回落，避免留下一个当前供应商下取不到的模型 id。
    """
    for key in STR_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value:
            setattr(state, key, value)
    for key in BOOL_KEYS:
        value = data.get(key)
        if isinstance(value, bool):
            setattr(state, key, value)
    for key in INT_KEYS:
        value = data.get(key)
        # 先排掉 bool：Python 里 True 也是 int，不挡会让它变成条数上限 1
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            setattr(state, key, value)

    state.api_keys = _unpack_keys(data.get(SECRETS_KEY))

    state.provider_id = catalog.provider_by_id(state.provider_id)["id"]
    state.model_id = catalog.model_by_id(state.provider_id, state.model_id)["id"]
    if state.audio_format not in [fmt for fmt, _label, _note in catalog.FORMATS]:
        state.audio_format = "wav"


def load(path: str, state) -> None:
    """从 path 读回配置。文件不存在、读不动或内容不是对象时，state 保持原样。"""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return
    if isinstance(data, dict):
        _apply(state, data)


def save(path: str, state) -> None:
    """把配置写进 path。写失败抛 OSError，由调用方决定是否提示。"""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    # 与 output.save_audio 同样的路子：先写临时文件再原地替换，
    # 中途失败（磁盘满、被占用）不会留下半截配置
    temp_path = path + ".part"
    try:
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(_to_dict(state), handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, path)
    except OSError:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
