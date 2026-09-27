# Simple TTS

## 项目简介

Simple TTS 是一个轻量级的 Windows 桌面文本转语音工具，当前版本（v0.1.0）接入小米 MiMo 语音合成 API（`https://api.xiaomimimo.com/v1`，OpenAI Chat Completions 风格接口），支持其三个模型：

- `mimo-v2.5-tts`：预置音色合成，支持唱歌模式与低延迟流式输出
- `mimo-v2.5-tts-voicedesign`：通过文本描述定制音色
- `mimo-v2.5-tts-voiceclone`：基于音频样本复刻音色

设计目标：界面简单、性能占用低、实用；架构上通过 Provider 抽象（`synthesize(text, **params) -> audio_bytes`，返回一段完整音频文件的字节）与 GUI 严格分层，便于后续接入其他 TTS 服务。

工作流：提交文本 → 服务端一次性返回完整音频 → 保存到本地文件 → 用户点击试听时在软件内播放该文件。不使用流式接收与流式播放。

## 技术栈

- **语言**：Python 3.12（不兼容 Windows 7；3.9+ 要求 Win8.1+，3.13+ 要求 Win10+，故 3.12 是覆盖面与特性之间的平衡点）
- **GUI**：PySide6（Qt Widgets），使用 Qt 布局（QVBoxLayout / QHBoxLayout / QGridLayout）与控件，外观由 Qt 原生风格跟随系统；Qt6 自带 per-monitor DPI 处理，无需自行调用 DPI awareness API
- **HTTP 调用**：标准库 `urllib`，调用 Chat Completions 非流式接口（`stream` 不传或为 `false`），不引入 openai SDK。响应中 `choices[0].message.audio.data` 为 base64 编码的完整音频，`base64.b64decode` 后即为可落盘的音频字节
- **音频格式**：请求参数 `audio.format` 取 `wav` 或 `mp3`（不支持 pcm16 裸流，不用于流式场景）。取 `wav` 时服务端返回成型 WAV 文件，无需自行补写 WAV 头；取 `mp3` 时返回成型 MP3 文件
- **音频播放**：播放已落盘的本地音频文件。优先使用 `ctypes` 调用 MCI（`mciSendStringW`），零第三方依赖即可获得播放、停止、音量、播放位置与结束通知，且无需为格式做特判。若确认只需"播放/停止"而不需要音量与进度，可退化为标准库 `winsound.PlaySound(path, SND_FILENAME | SND_ASYNC)`
- **第三方依赖**：运行期依赖 `PySide6-Essentials`（LGPLv3，装在项目内 `.venv/`，不入版本库），开发期另使用 PyInstaller 打包；分发时用 PyInstaller `--onedir` 模式（不要将 Qt 二进制压进单文件，用户需能替换 Qt 二进制是 LGPLv3 的要求），产出目录内附 Qt/PySide6 的许可文件
