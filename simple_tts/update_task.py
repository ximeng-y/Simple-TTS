"""后台的更新任务：检查与下载。

与 synth.py 同构：HTTP 调用是阻塞的，放到 daemon 线程里跑，结果经 Qt 信号回到
主线程。用 threading.Thread 而非 QThread 的理由也一样 —— 代理卡住时窗口关闭
不该被等（见 synth.py 的说明）。
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from . import updater


class _CheckSignals(QObject):
    """信号载体，须在主线程构造（理由见 synth.py）。"""

    done = Signal(object, object)  # 清单, 下载来源顺序
    failed = Signal(str)


class CheckTask:
    """一次检查更新的生命周期：start() -> done/failed。"""

    def __init__(self, sources: list) -> None:
        self._sources = sources
        self._signals = _CheckSignals()
        self._alive = True
        self._thread: threading.Thread | None = None

    @property
    def signals(self) -> _CheckSignals:
        return self._signals

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="simple-tts-update-check",
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        """丢弃后续回调。清理见 synth.SynthesisTask.cancel()。"""
        self._alive = False

    def _run(self) -> None:
        try:
            manifest, ordered = updater.check(self._sources)
        except updater.UpdateError as exc:
            self._fail(str(exc))
        except Exception as exc:  # noqa: BLE001
            self._fail(f"检查更新失败：{type(exc).__name__}: {exc}")
        else:
            if self._alive:
                self._signals.done.emit(manifest, ordered)

    def _fail(self, message: str) -> None:
        if self._alive:
            self._signals.failed.emit(message)


class _DownloadSignals(QObject):
    progress = Signal(int, int, str)  # 已下载字节, 总字节, 来源名
    done = Signal(str)  # 已解压就绪的目录
    failed = Signal(str)


class DownloadTask:
    """一次下载的生命周期：start() -> done(staged 目录) / failed。"""

    def __init__(self, manifest: dict, sources: list) -> None:
        self._manifest = manifest
        self._sources = sources
        self._signals = _DownloadSignals()
        # 两个标志各管一边：_cancelled 让下载线程尽快收手，
        # _alive 保证不再往可能已销毁的窗口发信号
        self._cancelled = False
        self._alive = True
        self._thread: threading.Thread | None = None
        # 上次报过的百分比，用于限流（每 64KB 一块，不限流会刷出上千次跨线程信号）
        self._last_percent = -1

    @property
    def signals(self) -> _DownloadSignals:
        return self._signals

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="simple-tts-update-download",
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        self._cancelled = True
        self._alive = False

    # ---------------------------------------------------------------- 内部

    def _is_cancelled(self) -> bool:
        return self._cancelled

    def _on_progress(self, done: int, total: int, source_name: str) -> None:
        percent = int(done * 100 / total) if total > 0 else 0
        if percent == self._last_percent:
            return
        self._last_percent = percent
        if self._alive:
            self._signals.progress.emit(done, total, source_name)

    def _run(self) -> None:
        try:
            zip_path = updater.download(
                self._manifest, self._sources, self._on_progress, self._is_cancelled
            )
            staged = updater.extract(zip_path)
        except updater.UpdateError as exc:
            self._fail(str(exc))
        except Exception as exc:  # noqa: BLE001
            self._fail(f"下载更新失败：{type(exc).__name__}: {exc}")
        else:
            if self._alive:
                self._signals.done.emit(staged)

    def _fail(self, message: str) -> None:
        if self._alive:
            self._signals.failed.emit(message)
