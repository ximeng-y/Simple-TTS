"""检查更新对话框。

非模态：下载可能持续几十秒，期间用户还能继续用软件合成音频，因此用 show()
而不是 exec()。四态各占一页，由 QStackedWidget 切换。

本模块只经回调与 App 通信（on_download / on_cancel / on_skip /
on_restart_now / on_restart_later / on_open_page），不 import 其它 ui 模块。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from . import theme

# 进度条走千分比：整数百分比在下载几十兆的更新包时变化太粗，进度条会一跳一跳
_PROGRESS_SCALE = 1000


def _mb(size: int) -> str:
    return f"{size / 1024 / 1024:.1f} MB"


class UpdateDialog(QDialog):
    """所有交互都转成回调交给 App，本类不碰 state、不碰线程。"""

    def __init__(
        self,
        parent,
        on_download,
        on_cancel,
        on_skip,
        on_restart_now,
        on_restart_later,
        on_open_page,
    ) -> None:
        super().__init__(parent)
        self._on_cancel = on_cancel
        self._on_skip = on_skip

        self.setWindowTitle("检查更新")
        self.setModal(False)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.GAP)
        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack)

        self._found_page = self._build_found_page(on_download, on_skip, on_open_page)
        self._progress_page = self._build_progress_page(on_cancel)
        self._ready_page = self._build_ready_page(on_restart_now, on_restart_later)
        self._error_page = self._build_error_page(on_open_page)
        self._latest_page = self._build_latest_page()
        for page in (
            self._found_page,
            self._progress_page,
            self._ready_page,
            self._error_page,
            self._latest_page,
        ):
            self._stack.addWidget(page)

    # ================================================================ 对外

    def show_found(self, version: str, notes: str, can_self_update: bool) -> None:
        """发现新版本。can_self_update 为 False 时只提示，不给更新按钮。"""
        self._found_title.setText(f"发现新版本 v{version}（当前 v{__version__}）")
        self._found_notes.setPlainText(notes.strip() or "（本次发布没有填写更新说明）")

        self._found_hint.setVisible(not can_self_update)
        self._download_button.setVisible(can_self_update)
        self._open_button_found.setVisible(not can_self_update)
        self._stack.setCurrentWidget(self._found_page)
        self._show()

    def show_progress(self, done: int, total: int, source_name: str) -> None:
        self._progress_label.setText(f"正在从 {source_name} 下载…")
        self._progress_bar.setRange(0, _PROGRESS_SCALE)
        ratio = int(done * _PROGRESS_SCALE / total) if total > 0 else 0
        self._progress_bar.setValue(min(ratio, _PROGRESS_SCALE))
        self._progress_size.setText(f"{_mb(done)} / {_mb(total)}")
        self._stack.setCurrentWidget(self._progress_page)
        self._show()

    def show_ready(self) -> None:
        self._stack.setCurrentWidget(self._ready_page)
        self._show()

    def show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._stack.setCurrentWidget(self._error_page)
        self._show()

    def show_latest(self) -> None:
        self._latest_label.setText(f"当前已是最新版本 v{__version__}。")
        self._stack.setCurrentWidget(self._latest_page)
        self._show()

    # ================================================================ 页面

    def _build_found_page(self, on_download, on_skip, on_open_page) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(theme.GAP)

        self._found_title = theme.title(page, "")
        layout.addWidget(self._found_title)

        self._found_hint = theme.hint(
            page, "当前为源码运行，请用 git pull 更新；或到发布页手动下载。", wrap=True
        )
        layout.addWidget(self._found_hint)

        self._found_notes = QPlainTextEdit(page)
        self._found_notes.setReadOnly(True)
        # 约 8 行，更新说明再长也就滚动条的事
        self._found_notes.setFixedHeight(self.fontMetrics().lineSpacing() * 8 + theme.PAD * 2)
        layout.addWidget(self._found_notes)

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self._open_button_found = QPushButton("打开发布页", page)
        self._open_button_found.clicked.connect(lambda: on_open_page())
        row.addWidget(self._open_button_found)
        row.addStretch(1)

        skip = QPushButton("忽略此版本", page)
        skip.clicked.connect(lambda: (on_skip(), self.hide()))
        row.addWidget(skip)

        later = QPushButton("稍后", page)
        later.clicked.connect(self.hide)
        row.addWidget(later)

        self._download_button = QPushButton("立即更新", page)
        self._download_button.setDefault(True)
        self._download_button.clicked.connect(lambda: on_download())
        row.addWidget(self._download_button)
        layout.addLayout(row)
        return page

    def _build_progress_page(self, on_cancel) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(theme.GAP)

        self._progress_label = QLabel(page)
        layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar(page)
        self._progress_bar.setTextVisible(False)
        layout.addWidget(self._progress_bar)

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self._progress_size = theme.hint(page, "")
        row.addWidget(self._progress_size)
        row.addStretch(1)
        cancel = QPushButton("取消", page)
        cancel.clicked.connect(lambda: on_cancel())
        row.addWidget(cancel)
        layout.addLayout(row)

        layout.addWidget(theme.hint(page, "下载可继续，期间软件照常使用；下载完会再提示。", wrap=True))
        return page

    def _build_ready_page(self, on_restart_now, on_restart_later) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(theme.GAP)

        layout.addWidget(theme.title(page, "更新已下载并校验完成"))
        layout.addWidget(theme.hint(page, "重启软件即可完成更新。", wrap=True))

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        row.addWidget(
            theme.hint(page, "选择「稍后」的话，关闭软件时会自动完成更新。", wrap=True), 1
        )
        later = QPushButton("稍后", page)
        later.clicked.connect(lambda: (on_restart_later(), self.hide()))
        row.addWidget(later)
        now = QPushButton("立即重启", page)
        now.setDefault(True)
        now.clicked.connect(lambda: on_restart_now())
        row.addWidget(now)
        layout.addLayout(row)
        return page

    def _build_error_page(self, on_open_page) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(theme.GAP)

        layout.addWidget(theme.title(page, "更新未完成"))
        self._error_label = theme.hint(page, "", wrap=True)
        layout.addWidget(self._error_label)
        layout.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        open_button = QPushButton("打开发布页", page)
        open_button.clicked.connect(lambda: on_open_page())
        row.addWidget(open_button)
        row.addStretch(1)
        close = QPushButton("关闭", page)
        close.setDefault(True)
        close.clicked.connect(self.hide)
        row.addWidget(close)
        layout.addLayout(row)
        return page

    def _build_latest_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(theme.GAP)

        self._latest_label = theme.title(page, "")
        layout.addWidget(self._latest_label)
        layout.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("关闭", page)
        close.setDefault(True)
        close.clicked.connect(self.hide)
        row.addWidget(close)
        layout.addLayout(row)
        return page

    # ================================================================ 内部

    def _show(self) -> None:
        """显示并置前。update_dialog 是复用的同一个实例，重新出现时要拉回视线。"""
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        """点 × 等价于「稍后」；正在下载时等价于「取消」。"""
        if self._stack.currentWidget() is self._progress_page:
            self._on_cancel()
        elif self._stack.currentWidget() is self._found_page:
            self._on_skip()
        super().closeEvent(event)
