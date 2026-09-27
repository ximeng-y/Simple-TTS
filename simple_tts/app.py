"""主窗口。

装配顺序：Header -> 中栏（左文本 / 右配置）-> 风格辅助 -> 播放条。
各 UI 模块之间互不 import，全部通过本类的回调通信：本类负责把界面上的值
收拢成一次合成请求，再把返回的音频落盘、装载、播放。
"""

from __future__ import annotations

import os
import webbrowser
from dataclasses import dataclass

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import __version__, catalog, output, storage
from .player import AudioPlayer
from .providers import MiMoProvider
from .state import AppState, settings_path, temp_output_dir
from .synth import SynthesisTask
from .ui import theme
from .ui.config_panel import ConfigPanel
from .ui.header import Header
from .ui.player_bar import PlayerBar
from .ui.settings_dialog import SettingsDialog
from .ui.style_panel import StylePanel, StylePanelScrollArea
from .ui.text_panel import TextPanel

_WINDOW_TITLE = "Simple TTS"
# 默认宽度写死，高度按布局实际需求算（见 App._default_size）；
# 高度不写死是因为窗口一开就要能装下中栏内容与整块风格辅助区 ——
# 内容高度随字号/系统缩放浮动，写死的数值只会让某个尺寸下开局就出现滚动条。
_DEFAULT_WIDTH = 1100
# 最小宽度下限（纯观感取值）
_MIN_WIDTH = 1000
_RIGHT_COL_W = theme.RIGHT_COL_W

# 播放位置的轮询间隔（毫秒）。MCI 没有回调，只能定时问；
# 100ms 足够让进度条看起来连续，开销也远小于一次界面重绘。
_TICK_MS = 100


@dataclass(frozen=True)
class _PendingSynth:
    """发起请求时冻下来的落盘参数。

    合成要跑数秒到数十秒，这段窗口里界面上的模型/音色/格式都还能改，
    落盘若读「回调触发时」的值，文件名会与实际音频内容对不上
    （例如中途切到 MP3 后扩展名变成 .mp3、内容却还是 WAV）。
    """

    voice_name: str
    model_id: str
    audio_format: str
    filename_pattern: str
    auto_play: bool


class App(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.state = AppState()
        # 上次运行留下的配置，读在装机之前：下面的界面构建与载入都是按它来摆的
        storage.load(settings_path(), self.state)
        self.player = AudioPlayer()
        self.provider = MiMoProvider()

        self._task: SynthesisTask | None = None
        # 当前请求的落盘参数快照，随 _task 一同存在，合成回来时用它落盘
        self._pending: _PendingSynth | None = None
        # 最近一次成功落盘的文件路径；None 表示还没有可试听的文件
        self._current_file: str | None = None
        # 当前文件已被「保存」到的路径；None 表示这份还没保存过。
        # 与 _current_file 同生共死：换了一份文件，这条记录就作废
        self._saved_target: str | None = None

        self.setWindowTitle(_WINDOW_TITLE)

        self._build_menu()
        self._build_layout()
        self.resize(*self._default_size())
        self._bind_shortcuts()
        self._load_model_into_ui()

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(_TICK_MS)
        self._tick_timer.timeout.connect(self._on_tick)

    # ================================================================ 构建

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        # 顶层「设置」菜单：三项都是设置页里的页面，点哪项直接停在那一页
        settings_menu = menubar.addMenu("设置")
        for label, page in (("通用…", "general"), ("供应商…", "provider"), ("API KEY…", "api")):
            action = QAction(label, self)
            action.triggered.connect(lambda _checked=False, name=page: self.on_settings(name))
            settings_menu.addAction(action)
        # Ctrl+, 是「打开设置」的惯例快捷键；这里没有单一设置项，给到默认页
        settings_menu.actions()[0].setShortcut(QKeySequence("Ctrl+,"))

        help_menu = menubar.addMenu("帮助")
        docs_action = QAction("API 使用文档", self)
        docs_action.triggered.connect(self.on_open_docs)
        help_menu.addAction(docs_action)

        about_action = QAction("关于", self)
        about_action.triggered.connect(self.on_about)
        help_menu.addAction(about_action)

    def _build_layout(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = Header(central, self.state, on_model_change=self.on_model_change)
        layout.addWidget(self.header)

        # 中栏：左文本弹性伸缩，右配置固定宽度
        middle = QSplitter(Qt.Horizontal, central)
        middle.setChildrenCollapsible(False)

        self.text_panel = TextPanel(middle, on_text_change=self.on_text_change)
        self.config_panel = ConfigPanel(middle, self.state, on_sing_toggle=self.on_sing_from_config)

        middle.addWidget(self.text_panel)
        middle.addWidget(self.config_panel)
        middle.setStretchFactor(0, 3)
        middle.setStretchFactor(1, 0)
        middle.setSizes([_DEFAULT_WIDTH - _RIGHT_COL_W, _RIGHT_COL_W])
        # 中栏是上半部分的弹性区：默认状态下它拿走全部多余高度（进入「合成文本」框），
        # 窗口变矮时再被压回去，最多压到两个文本框齐平（TextPanel 里的最小高度）。
        layout.addWidget(middle, 1)

        # 风格辅助面板：widgetResizable(False) 下滚动区不代管面板尺寸，
        # 这里显式把面板钉在全高，滚动区的最低高度给到半高 ——
        # 于是「已压缩即可滚动、压到一半为止」两件事各由一句代码负责。
        self.style_panel = StylePanel(
            central,
            on_opening_style=self.on_opening_style,
            on_inline_tag=self.on_inline_tag,
        )
        full = self.style_panel.sizeHint().height()
        self.style_panel.setFixedHeight(full)

        self.style_wrap = StylePanelScrollArea(central)
        self.style_wrap.setFrameShape(QFrame.NoFrame)
        self.style_wrap.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.style_wrap.setWidget(self.style_panel)
        self.style_wrap.setMinimumHeight(full // 2)
        layout.addWidget(self.style_wrap)

        self.player_bar = PlayerBar(
            central,
            on_synthesize=self.on_synthesize,
            on_play=self.on_play,
            on_stop=self.on_stop,
            on_save=self.on_save_copy,
            on_seek=self.on_seek,
            on_volume=self.on_volume,
        )
        layout.addWidget(self.player_bar)

        self.setCentralWidget(central)

        # 窗口最小高度由布局实际需求决定：中栏压缩下限 + 风格面板半高 + 其余固定块。
        # 写死数值会在字号/系统缩放大时低于真实需求，中栏先被裁切而不是面板滚动。
        need = layout.minimumSize().height() + self.menuBar().sizeHint().height()
        self.setMinimumSize(_MIN_WIDTH, need)

    def _default_size(self) -> tuple[int, int]:
        """默认窗口尺寸：宽度固定，高度取「内容全高 与 可用屏幕高」的较小者。

        高度按布局实际需求算而不是写死：中栏本身只需按钮/输入框不被裁掉那么多
        （约 386px），要末行不被裁掉的风格辅助区再往下压一截。写死一个偏小的值
        （如原先的 880）在 150% 系统缩放下就装不下全部内容，一开局就出现滚动条。
        """
        central = self.centralWidget()
        need = central.layout().sizeHint().height() + self.menuBar().sizeHint().height()
        screen = self.screen().availableGeometry().height() if self.screen() else need
        return _DEFAULT_WIDTH, max(min(need, screen), self.minimumHeight())

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.on_synthesize)
        QShortcut(QKeySequence("F5"), self, activated=self.on_synthesize)

    # ================================================================ 模型联动

    def on_model_change(self, model_id: str) -> None:
        """顶部切换模型：先存旧草稿，再载入新模型的配置与文本。"""
        self._save_draft()
        self.state.model_id = model_id
        self._load_model_into_ui()

    def on_provider_change(self, provider_id: str) -> None:
        """设置页切换了启用的供应商：换掉顶部模型列表并重载界面。

        不同供应商支持的模型完全不同，旧模型 id 多半在新供应商下不存在，
        state.model 会自动回落到新供应商的第一个模型。
        """
        self._save_draft()
        self.state.provider_id = provider_id
        self.state.model_id = self.state.model["id"]
        self.header.reload_models()
        self._load_model_into_ui()

    def _load_model_into_ui(self) -> None:
        model = self.state.model
        draft = self.state.draft()

        self.config_panel.apply_model()
        self.text_panel.set_model(model)
        self.text_panel.set_style_prompt(draft.style_prompt)
        self.text_panel.set_text(draft.text)
        self._sync_sing_ui()

    def _save_draft(self) -> None:
        """把界面上的输入写回当前模型的草稿（仅内存，不进配置文件）。"""
        draft = self.state.draft()
        draft.style_prompt = self.text_panel.get_style_prompt()
        draft.text = self.text_panel.get_text()
        self.config_panel.commit()

    # ================================================================ 文本与标签

    def on_text_change(self) -> None:
        """文本框内容变化：同步唱歌状态。草稿在切模型/合成时统一保存。"""
        self._sync_sing_ui()

    def on_opening_style(self, style: str) -> None:
        self.text_panel.apply_opening(style)
        self._sync_sing_ui()

    def on_inline_tag(self, tag: str) -> None:
        self.text_panel.insert_inline(tag)

    def on_sing_from_config(self, checked: bool) -> None:
        """右侧「唱歌模式」复选框被点击。"""
        self.text_panel.set_sing(checked)
        self._sync_sing_ui()

    def _sync_sing_ui(self) -> None:
        """两处唱歌入口与文本框内容保持一致。

        (唱歌) 是写在文本里的标签，用户也可能手输或删除，因此以文本内容为准回写控件。
        """
        singing = self.text_panel.is_singing()
        self.config_panel.set_sing(singing)

    # ================================================================ 合成

    def on_synthesize(self) -> None:
        """触发合成：校验 -> 后台请求 -> 落盘 -> 装载 -> 按设置自动试听。"""
        if self._task is not None:
            # 上一次还没回来。按钮此时已禁用，走到这里只可能是快捷键
            return

        self._save_draft()
        draft = self.state.draft()
        model = self.state.model
        text = draft.text

        # 音色设计开启润色时可以不填文本；其余情况空文本没有意义
        if not text.strip() and not (draft.optimize_preview and model["supports_optimize"]):
            self._warn("请先填写要合成的文本。")
            return

        params = {
            "api_key": self.state.api_key,
            "model": model["id"],
            "tone_source": model["tone_source"],
            "audio_format": self.state.audio_format,
            "style_prompt": draft.style_prompt,
            "voice_id": self.config_panel.voice_id,
            "sample_path": draft.sample_path,
            "optimize_text_preview": draft.optimize_preview and model["supports_optimize"],
        }

        # 落盘参数与请求参数在同一时刻取值：合成期间界面仍可切换模型与格式，
        # 不能等回调回来再读，否则文件名/扩展名会与实际音频不符
        self._pending = _PendingSynth(
            voice_name=self.config_panel.voice_name or model["short"],
            model_id=model["id"],
            audio_format=self.state.audio_format,
            filename_pattern=self.state.filename_pattern,
            auto_play=self.state.auto_play,
        )

        self.player.stop()
        # 上一次试听可能还在轮询，一并停掉：合成期间没有播放位置可报，
        # 若让定时器继续跑，它会把刚设好的 synth 覆盖掉（见 _on_tick 的守卫）
        self._tick_timer.stop()
        self.player_bar.set_state("synth")

        task = SynthesisTask(self.provider, text, params)
        task.signals.done.connect(self._on_synthesized)
        task.signals.failed.connect(self._on_synthesize_failed)
        self._task = task
        task.start()

    def _on_synthesized(self, audio: bytes) -> None:
        """后台线程已拿到音频：按发起时的快照落盘并装载，界面回到可用状态。"""
        self._task = None
        pending = self._pending
        self._pending = None
        if pending is None:
            # 理论上走不到；真到了也只是没有参数可用，宁可不动界面
            return

        try:
            path = output.save_audio(
                audio,
                temp_output_dir(),
                pending.filename_pattern,
                voice_name=pending.voice_name,
                model_id=pending.model_id,
                audio_format=pending.audio_format,
                on_conflict=self._resolve_overwrite if self.state.confirm_overwrite else None,
            )
        except OSError as exc:
            self.player_bar.set_state("idle")
            self._warn(f"音频保存失败：{exc}")
            return

        if path is None:
            # 用户在覆盖询问里选了取消：这次结果不落盘，回到发起前的可用状态。
            # 上一个文件仍装载在播放器里，所以是 ready 而不是 idle。
            self.player_bar.set_state("ready" if self._current_file else "idle")
            self.player_bar.set_position(0.0, self.player.duration())
            return

        # 换了文件，上一份的「已保存」记录随之作废
        self._current_file = path
        self._saved_target = None
        if not self.player.load(path):
            self.player_bar.set_state("idle")
            self._warn(f"已生成 {path}，但无法播放该音频文件。")
            return

        self.player.set_volume(self.player_bar.volume_scale.value())
        self.player_bar.set_state("ready")
        self.player_bar.set_position(0.0, self.player.duration())

        # 先把新文件护住再清理：本次是刚生成的，不该被自己的上限判出局
        self._prune_temp()

        if pending.auto_play:
            self.on_play()
        else:
            self._warn(
                f"音频已生成，暂存于临时目录：\n{path}\n\n"
                f"需要留存请点「保存」，将拷贝到 {self.state.save_dir}。",
                title="合成完成",
                icon=QMessageBox.Information,
            )

    def _on_synthesize_failed(self, message: str) -> None:
        self._task = None
        self._pending = None
        self.player_bar.set_state("idle")
        self._warn(message, title="合成失败")

    # ================================================================ 保存

    def on_save_copy(self) -> None:
        """把当前音频拷进保存目录。同一份已保存过则只提示，不重复拷。"""
        if not self._current_file:
            return
        if self._saved_target is not None:
            self._warn(
                f"该音频已保存到：\n{self._saved_target}",
                title="已保存过",
                icon=QMessageBox.Information,
            )
            return
        if not os.path.exists(self._current_file):
            self._warn("当前音频文件已不在临时目录，无法保存。")
            return

        try:
            target = output.copy_audio(
                self._current_file,
                self.state.save_dir,
                on_conflict=self._resolve_overwrite if self.state.confirm_overwrite else None,
            )
        except OSError as exc:
            self._warn(f"保存失败：{exc}")
            return

        if target is None:
            # 用户在覆盖询问里选了取消
            return

        self._saved_target = target
        self._warn(
            f"已保存到：\n{target}",
            title="保存成功",
            icon=QMessageBox.Information,
        )

    # ================================================================ 播放

    def on_play(self) -> None:
        """从头播放当前文件，并启动位置轮询。"""
        if not self._current_file:
            return
        self.player.play()
        self.player_bar.set_state("playing")
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    def on_stop(self) -> None:
        self._tick_timer.stop()
        self.player.stop()
        self.player_bar.set_state("ready")
        self.player_bar.set_position(0.0, self.player.duration())

    def on_seek(self, _value: int) -> None:
        if not self._current_file:
            return
        self.player.seek(self.player_bar.playback_ratio() * self.player.duration())

    def on_volume(self, value: int) -> None:
        self.player.set_volume(int(value))

    def _on_tick(self) -> None:
        """播放位置轮询。MCI 不提供结束回调，靠这里发现播放已结束。

        只在「播放中」才回写结束态：定时器停止前已经排进事件循环的那次 tick
        仍会送达，而那时状态可能已经是 synth（合成前会 player.stop()），
        回写 ready 会把合成态顶掉、控件提前放开。
        """
        duration = self.player.duration()
        if not self.player.is_playing():
            self._tick_timer.stop()
            if self.player_bar.state != "playing":
                return
            self.player_bar.set_state("ready")
            self.player_bar.set_position(duration, duration)
            return
        self.player_bar.set_position(self.player.position(), duration)

    # ================================================================ 菜单动作

    def on_settings(self, page: str = "general") -> None:
        dialog = SettingsDialog(self, self.state, page=page)
        if dialog.exec() == QDialog.Accepted:
            if dialog.provider_changed:
                self.on_provider_change(self.state.provider_id)
            self.config_panel.apply_settings()
            # 设置页改完就落盘，不等关窗：用户点「确定」的这一刻配置已经定下来了
            self._save_settings()

    def on_open_docs(self) -> None:
        webbrowser.open(catalog.DOC_URL)

    def on_about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            f"Simple TTS v{__version__}\n\n"
            "轻量级 Windows 桌面文本转语音工具。\n"
            f"当前接入 {self.state.provider['name']}，支持预置音色、音色设计与音色复刻。",
        )

    # ================================================================ 内部

    def _prune_temp(self) -> None:
        """按设置里的条数上限清理临时目录，保留当前文件。"""
        output.prune(
            temp_output_dir(),
            self.state.temp_limit,
            keep=(self._current_file,) if self._current_file else (),
        )

    def _save_settings(self) -> None:
        """把 state 里的配置写进 userdata/settings.json。

        写不进去（目录只读、被判毒拦下等）不该拦着用户用软件，只提示一次；
        提示是模态的，用户点掉之后就回到正常流程。
        """
        try:
            storage.save(settings_path(), self.state)
        except OSError as exc:
            self._warn(f"配置无法保存，本次改动重启后会丢失：\n{exc}")

    def _resolve_overwrite(self, path: str) -> str:
        """落盘发现同名时询问用户，返回 output 里约定的三种处置之一。

        默认按钮给「另存为副本」：误按回车不该把已有文件覆盖掉。
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("文件已存在")
        box.setText(f"文件已存在：\n{path}")
        overwrite = box.addButton("覆盖", QMessageBox.DestructiveRole)
        rename = box.addButton("另存为副本", QMessageBox.AcceptRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(rename)
        box.exec()

        clicked = box.clickedButton()
        if clicked is overwrite:
            return output.CONFLICT_OVERWRITE
        if clicked is rename:
            return output.CONFLICT_RENAME
        return output.CONFLICT_CANCEL

    def _warn(self, message: str, title: str = "提示", icon: QMessageBox.Icon = QMessageBox.Warning) -> None:
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(message)
        box.exec()

    # ================================================================ 退出

    def closeEvent(self, event) -> None:
        # 右侧配置区的目录/格式/文件名模式只在 commit 时收回 state，
        # 关窗前先收一次，否则这两处改动会写在配置之外
        self._save_draft()
        self._save_settings()

        if self._task is not None:
            # 请求阻塞在 socket 上无法中断，只能让它随进程一起结束（线程是 daemon），
            # 这里先把回调摘掉，避免结果回来时窗口已经在销毁中
            self._task.cancel()
            self._task = None
            self._pending = None
        self._tick_timer.stop()
        self.player.close()
        super().closeEvent(event)
