# Simple TTS

## 项目简介

Simple TTS 是一个轻量级的 Windows 桌面文本转语音工具，当前版本（v0.1.0）接入小米 MiMo 语音合成 API（`https://api.xiaomimimo.com/v1`，OpenAI Chat Completions 风格接口），支持其三个模型：

- `mimo-v2.5-tts`：预置音色合成，支持唱歌模式
- `mimo-v2.5-tts-voicedesign`：通过文本描述定制音色
- `mimo-v2.5-tts-voiceclone`：基于音频样本复刻音色

设计目标：界面简单、性能占用低、实用；架构上通过 Provider 抽象（`synthesize(text, **params) -> audio_bytes`，返回一段完整音频文件的字节）与 GUI 严格分层，便于后续接入其他 TTS 服务。

供应商在代码里体现为 `catalog.PROVIDERS`：一项 = 一套基地址 + 一组可用模型。`AppState` 只记 `provider_id` 与 `model_id`（均按 id 而非下标存储），顶部模型下拉与设置页的供应商单选、API KEY 标签页全部由该列表生成，接入第二家时只追加数据项，界面层无需改动。

工作流：提交文本 → 服务端一次性返回完整音频 → 保存到本地文件 → 用户点击试听时在软件内播放该文件。不使用流式接收与流式播放。

### 模块划分

| 模块 | 职责 |
| --- | --- |
| `catalog.py` | 纯数据：供应商/模型/预置音色/格式/风格标签，界面与后端共用 |
| `state.py` | 内存中的配置与各模型草稿，退出即丢，不落盘 |
| `providers/base.py` | `TTSProvider` 抽象与 `SynthesisError` |
| `providers/mimo.py` | MiMo 实现，只依赖标准库，不 import Qt |
| `synth.py` | 后台合成线程，结果经 Qt 信号回主线程 |
| `output.py` | 文件名拼装与音频落盘 |
| `player.py` | MCI 播放本地音频文件 |
| `ui/` | 界面模块，互不 import，全部经 `app.py` 的回调通信 |

数据流：`App.on_synthesize` 收拢界面上的值 → `SynthesisTask` 在后台线程调 `provider.synthesize` → 回到主线程由 `output.save_audio` 落盘 → `player.load/play` 播放，并用定时器轮询 MCI 状态驱动进度条。

## 技术栈

- **语言**：Python 3.12（不兼容 Windows 7；3.9+ 要求 Win8.1+，3.13+ 要求 Win10+，故 3.12 是覆盖面与特性之间的平衡点）
- **GUI**：PySide6（Qt Widgets），使用 Qt 布局（QVBoxLayout / QHBoxLayout / QGridLayout）与控件，外观由 Qt 原生风格跟随系统；Qt6 自带 per-monitor DPI 处理，无需自行调用 DPI awareness API
- **HTTP 调用**：标准库 `urllib`，调用 Chat Completions 非流式接口（`stream` 固定为 `false`），不引入 openai SDK。响应中 `choices[0].message.audio.data` 为 base64 编码的完整音频，`base64.b64decode` 后即为可落盘的音频字节
- **音频格式**：请求参数 `audio.format` 取 `wav` 或 `mp3`（不支持 pcm16 裸流，不用于流式场景）。取 `wav` 时服务端返回成型 WAV 文件，无需自行补写 WAV 头；取 `mp3` 时返回成型 MP3 文件
- **音频播放**：播放已落盘的本地音频文件，用 `ctypes` 调用 MCI（`mciSendStringW`），`open ... type mpegvideo` 加载后 wav 与 mp3 共用一套命令，零第三方依赖即可获得播放、停止、音量、播放位置与时长。MCI 没有结束回调，播放中由 `App` 用一个 100ms 定时器轮询 `status mode` 发现播放结束并停止轮询
- **线程模型**：合成是阻塞 HTTP 调用，放在 `threading.Thread`（daemon）里执行，结果经 Qt 信号回主线程；线程为 daemon，请求未返回时关窗也能正常退出，`closeEvent` 只摘掉回调
- **第三方依赖**：运行期依赖 `PySide6-Essentials`（LGPLv3，装在项目内 `.venv/`，不入版本库），开发期另使用 PyInstaller 打包；分发时用 PyInstaller `--onedir` 模式（不要将 Qt 二进制压进单文件，用户需能替换 Qt 二进制是 LGPLv3 的要求），产出目录内附 Qt/PySide6 的许可文件

## 已知边界

- 配置只存在于内存，重启回到默认值；「保留合成历史记录」勾选项尚无对应功能
- 同名文件不覆盖也不询问，自动追加 `_2`、`_3`；文件名模式含 `{index}` 时改为递增序号
- 请求无法中断，合成中途关窗会直接放弃这次请求

