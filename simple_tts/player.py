"""音频播放器。

v0.1.0 计划用 ctypes 调用 MCI（mciSendStringW）播放已落盘的本地音频文件：
零第三方依赖即可获得播放、停止、音量、播放位置与结束通知，且无需为格式做特判。

本版本是纯前端形态演示，后端尚未接入，因此这里只保留对外接口签名，
方法体一律为空实现 —— 不 import ctypes、不调用 MCI，避免留下半成品代码。
后续接入时在对应方法里补上 MCI 调用即可，UI 层无需改动。
"""

from __future__ import annotations


class AudioPlayer:
    """播放一段本地音频文件。

    生命周期：load() 装载文件 -> play()/stop()/seek()/set_volume() 操作 -> close() 释放。
    """

    def __init__(self) -> None:
        self._path: str = ""

    # ---------------------------------------------------------------- 接口

    def load(self, path: str) -> None:
        """装载待播放的音频文件。同一时间只持有一个文件。"""
        # TODO(后端接入): 关闭上一个别名后 mciSendStringW(f'open "{path}" alias ...')
        self._path = path

    def play(self) -> None:
        """从头开始播放当前文件。"""
        # TODO(后端接入): mciSendStringW("play <alias>")

    def stop(self) -> None:
        """停止播放并回到起点。"""
        # TODO(后端接入): mciSendStringW("stop <alias>") + "seek <alias> to start"

    def seek(self, seconds: float) -> None:
        """跳转到指定播放位置（秒）。"""
        # TODO(后端接入): mciSendStringW(f"seek <alias> to {int(seconds * 1000)}")

    def set_volume(self, percent: int) -> None:
        """设置音量，取值 0-100。"""
        # TODO(后端接入): mciSendStringW(f"setaudio <alias> volume to {int(percent * 10)}")

    def is_playing(self) -> bool:
        """是否正在播放。用于驱动进度条与「试听/停止」按钮的互斥状态。"""
        return False

    def duration(self) -> float:
        """当前文件总时长（秒）。"""
        return 0.0

    def position(self) -> float:
        """当前播放位置（秒）。"""
        return 0.0

    def close(self) -> None:
        """释放当前文件。"""
        # TODO(后端接入): mciSendStringW("close <alias>")
        self._path = ""
