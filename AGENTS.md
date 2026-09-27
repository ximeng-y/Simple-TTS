# Simple TTS

## 项目简介

Simple TTS 是一个轻量级的 Windows 桌面文本转语音工具，当前版本（v0.1.0）接入小米 MiMo 语音合成 API（`https://api.xiaomimimo.com/v1`，OpenAI Chat Completions 风格接口），支持其三个模型：

- `mimo-v2.5-tts`：预置音色合成，支持唱歌模式
- `mimo-v2.5-tts-voicedesign`：通过文本描述定制音色
- `mimo-v2.5-tts-voiceclone`：基于音频样本复刻音色

设计目标：界面简单、性能占用低、实用；架构上通过 Provider 抽象（`synthesize(text, **params) -> audio_bytes`，返回一段完整音频文件的字节）与 GUI 严格分层，便于后续接入其他 TTS 服务。

供应商在代码里体现为 `catalog.PROVIDERS`：一项 = 一套基地址 + 一组可用模型。`AppState` 只记 `provider_id` 与 `model_id`（均按 id 而非下标存储），顶部模型下拉与设置页的供应商单选、API KEY 标签页全部由该列表生成，接入第二家时只追加数据项，界面层无需改动。

工作流：提交文本 → 服务端一次性返回完整音频 → 写进临时目录 → 用户点击试听时在软件内播放该文件；需要留存时再点「保存」拷进保存目录。不使用流式接收与流式播放。

### 模块划分

| 模块 | 职责 |
| --- | --- |
| `catalog.py` | 纯数据：供应商/模型/预置音色/格式/风格标签，界面与后端共用 |
| `state.py` | 内存中的配置与各模型草稿，并提供 `userdata` 目录与配置文件路径的定位 |
| `storage.py` | 配置读写：`userdata/settings.json`，含 API Key 的 DPAPI 加解密 |
| `providers/base.py` | `TTSProvider` 抽象与 `SynthesisError` |
| `providers/mimo.py` | MiMo 实现，只依赖标准库，不 import Qt |
| `synth.py` | 后台合成线程，结果经 Qt 信号回主线程 |
| `output.py` | 文件名拼装、音频落盘、临时目录清理与「保存」拷贝 |
| `player.py` | MCI 播放本地音频文件 |
| `ui/` | 界面模块，互不 import，全部经 `app.py` 的回调通信 |

数据流：`App.on_synthesize` 收拢界面上的值 → `SynthesisTask` 在后台线程调 `provider.synthesize` → 回到主线程由 `output.save_audio` 写进临时目录 → 按上限清理临时目录 → `player.load/play` 播放，并用定时器轮询 MCI 状态驱动进度条。用户点「保存」时另由 `output.copy_audio` 把当前文件拷进保存目录。

## 技术栈

- **语言**：Python 3.12（不兼容 Windows 7；3.9+ 要求 Win8.1+，3.13+ 要求 Win10+，故 3.12 是覆盖面与特性之间的平衡点）
- **GUI**：PySide6（Qt Widgets），使用 Qt 布局（QVBoxLayout / QHBoxLayout / QGridLayout）与控件，外观由 Qt 原生风格跟随系统；Qt6 自带 per-monitor DPI 处理，无需自行调用 DPI awareness API
- **HTTP 调用**：标准库 `urllib`，调用 Chat Completions 非流式接口（`stream` 固定为 `false`），不引入 openai SDK。响应中 `choices[0].message.audio.data` 为 base64 编码的完整音频，`base64.b64decode` 后即为可落盘的音频字节
- **音频格式**：请求参数 `audio.format` 取 `wav` 或 `mp3`（不支持 pcm16 裸流，不用于流式场景）。取 `wav` 时服务端返回成型 WAV 文件，无需自行补写 WAV 头；取 `mp3` 时返回成型 MP3 文件
- **音频播放**：播放已落盘的本地音频文件，用 `ctypes` 调用 MCI（`mciSendStringW`），`open ... type mpegvideo` 加载后 wav 与 mp3 共用一套命令，零第三方依赖即可获得播放、停止、音量、播放位置与时长。MCI 没有结束回调，播放中由 `App` 用一个 100ms 定时器轮询 `status mode` 发现播放结束并停止轮询
- **配置持久化**：配置存 `userdata/settings.json`（标准库 `json`，临时文件 + `os.replace` 覆写），启动读入、点设置页「确定」与关窗时写出。API Key 不存明文：整份 key 表经 `ctypes` 调 Windows DPAPI（`CryptProtectData`）按当前登录用户加密后以 base64 存入，换 Windows 账户或换机器都读不出来 —— 也无需为此引入第三方库。各模型草稿（用户正在写的正文/描述）不落盘，属会话内容而非配置
- **线程模型**：合成是阻塞 HTTP 调用，放在 `threading.Thread`（daemon）里执行，结果经 Qt 信号回主线程；线程为 daemon，请求未返回时关窗也能正常退出，`closeEvent` 只摘掉回调
- **第三方依赖**：运行期依赖 `PySide6-Essentials`（LGPLv3，装在项目内 `.venv/`，不入版本库），开发期另使用 PyInstaller 打包；分发时用 PyInstaller `--onedir` 模式（不要将 Qt 二进制压进单文件，用户需能替换 Qt 二进制是 LGPLv3 的要求），产出目录内附 Qt/PySide6 的许可文件

### 落盘位置

需要写入磁盘的东西一律收敛在程序目录下的 `userdata/`（`state.userdata_dir()`），不碰系统用户目录：

```
userdata/
  output/         合成产物的临时落脚点，固定位置、界面上不可改
  save/           「保存」拷进这里的音频，默认保存目录（settings 里可改）
  settings.json   配置。没改过设置就不存在；api_keys_encrypted 是 DPAPI 密文
```

两类目录分工明确：合成的音频一律先落 `output/`，按设置里的「临时文件上限」（`temp_limit`，默认 10 条，0 表示不限制）先进先出地清理，只留最新的若干条；用户点「保存」才拷进 `save/`，那里只增不减，不受上限约束。之所以把临时目录固定下来、不给用户改：它只是中转站，位置可配只会多一个填错的机会。

目录跟着程序走，整个软件连同产物在一个文件夹内，拷贝或删除互不影响；`userdata/` 已进 `.gitignore`。定位程序目录时区分两种形态：源码运行取包目录的上一级，打包成 exe 后取 `sys.executable` 所在目录 —— 冻结后 `__file__` 指向 PyInstaller 解出的临时目录（onefile 模式下随进程结束被删除），不能用来放数据。

## 已知边界

- 配置存在 `userdata/settings.json`，重启后自动读回；其中 API Key 按当前 Windows 账户加密，换账户或把 `userdata/` 拷到别的机器需重新填写。「保留合成历史记录」勾选项尚无对应功能
- 旧的 `output_dir` 配置项已由 `save_dir` 取代，不做迁移：旧配置里的值会被忽略，保存目录回落到 `userdata/save`，用户重填一次即可
- 配置文件的容错口径是「宁可少读，不可起不来」：文件缺失、JSON 损坏、字段类型不符（含负数或非整数形式的 `temp_limit`）、供应商/模型 id 已不存在，一律回落默认值或忽略该项，不弹窗不报错。写盘失败（目录只读等）弹一次提示，软件继续可用，只是本次改动重启后丢失
- 同名文件默认不覆盖也不询问，自动追加 `_2`、`_3`；文件名模式含 `{index}` 时改为递增序号。勾选设置里的「覆盖同名文件前确认」后改为逐次弹窗询问（覆盖 / 另存为副本 / 取消，只问一次）；「保存」拷进保存目录时同名走同一套口径
- 临时目录的清理只认 `.wav` / `.mp3`，跳过 `.part` 中间文件与当前正在试听的那一份；删不掉（文件被 MCI 占用、只读）静默跳过，下次合成再清一遍。改小上限不立刻清理，从下一次合成起生效
- 「保存」按同一份文件去重：当前音频已保存过则只提示路径，不重复拷贝；重新合成后该记录自然作废，可再保存
- 请求无法中断，合成中途关窗会直接放弃这次请求

