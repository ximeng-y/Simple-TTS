"""后台合成任务。

``synthesize()`` 是阻塞的 HTTP 调用（长文本可能耗时数十秒），直接在主线程里跑
会让界面整个冻住，因此放到后台线程执行，结果通过 Qt 信号回到主线程。

用 ``threading.Thread`` 而非 ``QThread``：线程是 daemon，窗口关闭时若请求还没
返回，进程照常退出，不需要在 closeEvent 里等一个可能长达 120 秒的请求。
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from .providers import SynthesisError, TTSProvider


class _Signals(QObject):
    """信号载体。

    必须在本对象所属线程（主线程）里构造，这样从后台线程 emit 时 Qt 才会
    自动走队列连接，把回调排在主线程的事件循环上执行。
    """

    done = Signal(object)  # 音频字节
    failed = Signal(str)  # 直接可展示的中文错误说明


class SynthesisTask:
    """一次合成任务的生命周期：start() -> done/failed，或 cancel() 后静默丢弃。"""

    def __init__(self, provider: TTSProvider, text: str, params: dict) -> None:
        self._provider = provider
        self._text = text
        self._params = params
        self._signals = _Signals()
        self._alive = True
        self._thread: threading.Thread | None = None

    # ---------------------------------------------------------------- 对外

    @property
    def signals(self) -> _Signals:
        return self._signals

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="simple-tts-synthesize",
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        """丢弃后续回调。

        请求本身无法中断（阻塞在 socket 上），线程会随 daemon 属性在进程退出时结束；
        这里只需保证不会再回调到可能已被销毁的窗口。
        """
        self._alive = False

    # ---------------------------------------------------------------- 内部

    def _run(self) -> None:
        try:
            audio = self._provider.synthesize(self._text, **self._params)
        except SynthesisError as exc:
            self._fail(str(exc))
        except Exception as exc:  # noqa: BLE001
            # 兜底：后台线程里漏出的异常不会有人接，界面会永远停在「合成中」，
            # 因此无论什么异常都必须回传一句可读的说明。
            self._fail(f"合成失败：{type(exc).__name__}: {exc}")
        else:
            if self._alive:
                self._signals.done.emit(audio)

    def _fail(self, message: str) -> None:
        if self._alive:
            self._signals.failed.emit(message)
