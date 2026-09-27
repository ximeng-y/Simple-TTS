"""音频播放器。

用 ctypes 调 Windows 的 MCI（mciSendStringW）播放已落盘的本地音频文件：零第三方
依赖即可拿到播放、停止、音量、播放位置与时长，且不需要为 wav/mp3 分别处理。
MCI 的 mpegvideo 设备底层是 DirectShow，两种格式都能吃。

所有方法都只在主线程调用（界面线程），因此不做加锁；每次调用失败都返回安全默认值，
由调用方自身判断是否继续 —— 例如窗口关闭时 close() 之后再有 status 查询是正常的。
"""

from __future__ import annotations

import ctypes
import os
import threading

_winmm = ctypes.WinDLL("winmm")

_mci = _winmm.mciSendStringW
_mci.argtypes = [
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    ctypes.c_uint,
    ctypes.c_void_p,
]
_mci.restype = ctypes.c_uint

_BUF = 256
_MODE_PLAYING = "playing"


def _send(command: str) -> tuple[int, str]:
    """执行一条 MCI 命令，返回 (错误码, 输出文本)。错误码为 0 表示成功。"""
    buffer = ctypes.create_unicode_buffer(_BUF)
    code = _mci(command, buffer, _BUF, None)
    return code, buffer.value


class AudioPlayer:
    """播放一段本地音频文件。

    生命周期：load() 装载文件 -> play()/stop()/seek()/set_volume() 操作 -> close() 释放。
    """

    def __init__(self) -> None:
        self._path = ""
        self._alias = ""
        # 别名在同一个进程里必须唯一：MCI 关闭别名是异步生效的，复用同名别名
        # 会在「换个文件重播」时偶发 open 失败
        self._seq = 0
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- 接口

    def load(self, path: str) -> bool:
        """装载待播放的音频文件，返回是否装载成功。同一时间只持有一个文件。"""
        with self._lock:
            self._close_locked()
            if not path or not os.path.exists(path):
                return False

            self._seq += 1
            alias = f"simpletts{self._seq}"
            code, _ = _send(f'open "{path}" type mpegvideo alias {alias}')
            if code != 0:
                # mpegvideo 打不开时退回让 MCI 自行按扩展名挑设备（wav 走 waveaudio）
                code, _ = _send(f'open "{path}" alias {alias}')
            if code != 0:
                return False

            self._path = path
            self._alias = alias
            return True

    def play(self) -> None:
        """从头开始播放当前文件。"""
        with self._lock:
            if self._alias:
                _send(f"seek {self._alias} to start")
                _send(f"play {self._alias}")

    def stop(self) -> None:
        """停止播放并回到起点。"""
        with self._lock:
            if self._alias:
                _send(f"stop {self._alias}")
                _send(f"seek {self._alias} to start")

    def seek(self, seconds: float) -> None:
        """跳转到指定播放位置（秒）。播放中跳转会继续播放。"""
        with self._lock:
            if not self._alias:
                return
            was_playing = self._mode_locked() == _MODE_PLAYING
            _send(f"seek {self._alias} to {max(int(seconds * 1000), 0)}")
            if was_playing:
                _send(f"play {self._alias}")

    def set_volume(self, percent: int) -> None:
        """设置音量，取值 0-100。"""
        with self._lock:
            if self._alias:
                _send(f"setaudio {self._alias} volume to {max(0, min(int(percent), 100)) * 10}")

    def is_playing(self) -> bool:
        """是否正在播放。用于驱动进度条与「试听/停止」按钮的互斥状态。"""
        with self._lock:
            return self._mode_locked() == _MODE_PLAYING

    def duration(self) -> float:
        """当前文件总时长（秒）。"""
        return self._status_seconds("length")

    def position(self) -> float:
        """当前播放位置（秒）。"""
        return self._status_seconds("position")

    def close(self) -> None:
        """释放当前文件。"""
        with self._lock:
            self._close_locked()

    # ---------------------------------------------------------------- 内部

    def _close_locked(self) -> None:
        if self._alias:
            _send(f"close {self._alias}")
        self._alias = ""
        self._path = ""

    def _status_seconds(self, what: str) -> float:
        """查询 MCI 的毫秒级状态并换算成秒；查不到返回 0。"""
        with self._lock:
            if not self._alias:
                return 0.0
            code, value = _send(f"status {self._alias} {what}")
        if code != 0 or not value.strip().isdigit():
            return 0.0
        return int(value) / 1000.0

    def _mode_locked(self) -> str:
        """返回 MCI 的当前播放状态：playing / paused / stopped / not ready。"""
        if not self._alias:
            return ""
        code, value = _send(f"status {self._alias} mode")
        return value.strip() if code == 0 else ""
