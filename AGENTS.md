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
| `updater.py` | 自动更新：下载源、版本比较、清单解析、并发检查、下载校验、解压、生成并启动替换脚本。只依赖标准库，不 import Qt |
| `update_task.py` | 检查更新与下载的后台线程，结果经 Qt 信号回主线程（仿 `synth.py`） |
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
- **第三方依赖**：运行期依赖 `PySide6-Essentials`（LGPLv3，装在项目内 `.venv/`，不入版本库），开发期另使用 PyInstaller 打包；分发时用 PyInstaller `--onedir` 模式（不要将 Qt 二进制压进单文件，用户需能替换 Qt 二进制是 LGPLv3 的要求），产出目录内附 Qt/PySide6 的许可文件（见 `licenses/`）
- **许可**：程序自身以 GPL-3.0-or-later 发布，正文在仓库根目录的 `LICENSE`（GitHub 靠根目录这个文件名识别许可，不要挪动或改名）。`licenses/` 只放第三方组件（Qt/PySide6 的 LGPLv3、Python 的 PSF），两者不可混放。打包时根目录的 `LICENSE` 会被拷成发布包内的 `licenses/LICENSE.txt`，让用户在一个目录里找齐全部许可（GPLv3 §4 要求随二进制分发许可正文）
- **自动更新**：客户端读 `https://github.com/ximeng-y/Simple-TTS/releases/latest/download/latest.json`（GitHub 会 302 到最新**正式**版 release 的同名附件；预发布版不会被 `latest` 选中），不用 `api.github.com` —— 加速代理只转发 `github.com` 的下载链接，且未登录的 API 每小时只给 60 次。清单里带版本号、zip 的文件名/大小/SHA256 与更新说明，下载后按它校验。下载源 = 直连 GitHub（`urllib` 自动读 Windows 系统代理）+ `update_mirrors` 里的加速代理前缀（用法是「前缀 + 完整 GitHub URL」）+ Gitee（接口已留，`catalog.GITEE_REPO` 为空即不启用），检查时**并发**取清单取最快的一个、下载时按快慢顺序逐个退。SHA256 能挡下载被截断或改坏；若清单本身经代理取得，代理可以连清单带 zip 一起换掉 —— 个人工具接受这一边界。更新包解压在 `userdata/update/`，替换由外部 bat 完成（运行中的 exe 与 Qt DLL 被占用，自己换不了自己）：脚本等主进程退出后，对 `_internal/` 做镜像，顶层与其余子目录只覆盖/新增、绝不删除（安装目录里可能有用户自己的文件），`userdata/` 完全不动；替换失败会留一个标记文件，下次启动提示。源码运行时（`启动.bat`）只提示不替换

### 落盘位置

需要写入磁盘的东西一律收敛在程序目录下的 `userdata/`（`state.userdata_dir()`），不碰系统用户目录：

```
userdata/
  output/         合成产物的临时落脚点，固定位置、界面上不可改
  save/           「保存」拷进这里的音频，默认保存目录（settings 里可改）
  update/         更新包的下载与解压中转目录，每次启动整个清掉
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
- 更新用的加速代理寿命不定，失效后在「设置 → 更新」里删掉或换掉即可；删光就是只走直连。Gitee 下载源的接入框架已留（`updater.GiteeSource`）但未启用，`catalog.GITEE_REPO` 为空，启用前需按「发版流程」实测
- 自动检查更新每天至多一次（按 `update_last_check` 判断），失败一律静默；手动检查（「帮助 → 检查更新」）失败会显示原因。点过「忽略此版本」的版本号记进 `update_skip_version`，自动检查不再提示它，手动检查照常提示
- 程序目录不可写（装在 Program Files 又没提权）时更新无法完成：替换脚本会写一个失败标记，下次启动提示用户到发布页手动下载
- 源码运行时（`启动.bat`）不自我替换，对话框只提示「用 git pull 更新」

## 发版流程

打包发版**手动进行**，不使用 GitHub Actions。每个 release 只挂两个附件，客户端与打包脚本都按这个约定来：

- `SimpleTTS-{version}-win64.zip`：zip 顶层是一个目录 `SimpleTTS/`，其下是 `SimpleTTS.exe`、`_internal/`、`licenses/`（含程序自身的 GPL 正文 `LICENSE.txt` 与第三方许可）
- `latest.json`（UTF-8）：

```json
{
  "version": "0.2.0",
  "tag": "v0.2.0",
  "asset": "SimpleTTS-0.2.0-win64.zip",
  "size": 45678901,
  "sha256": "64 位小写十六进制",
  "notes": "更新说明，纯文本，可多行"
}
```

步骤：

1. 改 `simple_tts/__init__.py` 的 `__version__`，提交。
2. 写本次更新说明到一个文本文件，例如 `.XMTEMP\notes.txt`。
3. 在项目根目录跑 `.venv\Scripts\python.exe tools\build_release.py --notes-file .XMTEMP\notes.txt`。脚本会重跑 PyInstaller、拷入 `licenses/`、打 zip（自动跳过 `userdata/`）、算 SHA256 并写出 `dist\latest.json`。
4. 双击 `dist\SimpleTTS\SimpleTTS.exe` 冒烟一遍；跑完把它生成的 `dist\SimpleTTS\userdata\` 删掉（脚本打 zip 时本就会跳过它）。
5. `git tag v{version}` 然后 `git push origin v{version}`。
6. `gh release create v{version} dist\SimpleTTS-{version}-win64.zip dist\latest.json --title "v{version}" --notes-file .XMTEMP\notes.txt`。**不要勾选 pre-release** —— `releases/latest` 只指向最新正式版，勾了客户端就查不到这次更新。
7. （可选，启用 Gitee 后）在 Gitee 同名仓库建同 tag 的 release，上传同样两个文件；首次启用时把 `catalog.GITEE_REPO` 设为 `owner/repo`，并实测 `GiteeSource` 的两步取清单（发 `releases/latest` 的 API、在 assets 里找 `latest.json`）与附件匿名下载。
8. 验证：浏览器打开 `https://github.com/ximeng-y/Simple-TTS/releases/latest/download/latest.json`，能看到刚发的版本号即成功。

