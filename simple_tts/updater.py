"""自动更新：检查、下载、校验、解压、替换。

本模块只用标准库，不 import Qt —— 除界面外的所有更新逻辑都在这里，界面层
（update_task.py / ui/update_dialog.py）只负责把它跑起来并把结果画出来。

数据流：取清单 latest.json -> 下载 zip -> 校验 SHA256 -> 解压到 userdata/update/staging
-> 写一个替换脚本并启动它 -> 本进程退出，脚本覆盖程序目录后按需重启。

几个设计上的取舍：

- **读 ``releases/latest/download/latest.json`` 而不调 ``api.github.com``**：加速代理
  转发的是 github.com 的下载链接，不转发 API；而且未登录的 API 每小时只给 60 次。
  清单挂在 release 附件里，与 zip 走同一条路，代理能通清单就能通。
- **SHA256 的信任边界**：它能挡住下载被截断、被中间设备改坏，但清单本身若经代理
  取得，代理可以连清单带 zip 一起换掉。个人工具接受这一条（要堵住得给清单做签名，
  标准库的 ``pow`` 足够做 RSA 验签，暂不实现）。
- **替换交给外部 bat**：运行中的 exe 与其加载的 Qt DLL 都被系统占用，自己换不了
  自己，只能另起一个进程、等本进程退出后再动手。
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from . import __version__, catalog
from .state import program_dir, update_dir

# 部分代理会拒掉 Python-urllib 的默认 UA
_USER_AGENT = f"SimpleTTS/{__version__}"
_MANIFEST_TIMEOUT = 8  # 秒，单个来源取清单的超时
_DOWNLOAD_TIMEOUT = 30  # 秒，下载时单次 socket 读的超时
_CHUNK = 64 * 1024
# 清单很小，读这么多还读不完说明对面返回的不是清单（例如代理塞了一个网页）
_MANIFEST_MAX_BYTES = 1024 * 1024

EXE_NAME = "SimpleTTS.exe"
MANIFEST_NAME = "latest.json"
# 替换脚本失败时写下的标记文件，下次启动由 cleanup() 读取并提示
_RESULT_FILE = "result.txt"

# 解压出的更新包中，用户可替换的 Qt 二进制所在的目录（LGPLv3 的要求）
_INTERNAL_DIR = "_internal"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class UpdateError(Exception):
    """更新过程中的失败。消息是可直接展示给用户的中文。"""


# ---------------------------------------------------------------- 版本


def parse_version(text: str) -> tuple[int, ...] | None:
    """``'0.2.0'`` / ``'v0.2.0'`` -> ``(0, 2, 0)``；含非数字段（如 ``0.2.0-beta``）返回 None。"""
    if not isinstance(text, str):
        return None
    trimmed = text.strip().lstrip("vV")
    if not trimmed:
        return None
    parts = trimmed.split(".")
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def is_newer(remote: str, local: str = __version__) -> bool:
    """remote 能解析且严格大于 local 时为 True；任一解析失败返回 False。

    返回 False 意味着「不提示更新」—— 拿不准的时候宁可不打扰用户。
    """
    remote_tuple = parse_version(remote)
    local_tuple = parse_version(local)
    if remote_tuple is None or local_tuple is None:
        return False
    return remote_tuple > local_tuple


# ---------------------------------------------------------------- 代理前缀


def normalize_mirrors(items) -> list[str]:
    """规整代理前缀列表：去空白、只留 http(s)、补齐结尾斜杠、按出现顺序去重。"""
    result: list[str] = []
    for item in items:
        prefix = item.strip() if isinstance(item, str) else ""
        if not prefix.lower().startswith(("http://", "https://")):
            continue
        if not prefix.endswith("/"):
            prefix += "/"
        if prefix not in result:
            result.append(prefix)
    return result


# ---------------------------------------------------------------- HTTP 小工具


def _open(url: str, timeout: float):
    """带 UA 的 urlopen。

    默认的 ProxyHandler 会读 Windows 注册表里的系统代理设置，因此开着代理软件的
    用户即使直连 GitHub 也能通，不需要在这里额外配置。重定向（releases/latest
    就是靠 302 指到具体 tag）由 urllib 自动跟随。
    """
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)


def _get_bytes(url: str, timeout: float, limit: int = _MANIFEST_MAX_BYTES) -> bytes:
    """取一段小内容（清单）。读满 limit 还不见结尾就判失败。"""
    try:
        with _open(url, timeout) as response:
            raw = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        raise UpdateError(f"连接失败：{reason}") from exc
    if len(raw) > limit:
        raise UpdateError("返回内容过大")
    return raw


# ---------------------------------------------------------------- 清单


def parse_manifest(raw: bytes) -> dict:
    """解析并校验 latest.json，返回只含约定 6 个键的新 dict。

    asset 里的路径分隔符与 ``..`` 一律拒掉：它会被拼进下载地址，也会被用作
    落盘文件名，放行等于让清单指定写到哪去。
    """
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise UpdateError("更新信息格式不正确") from exc
    if not isinstance(data, dict):
        raise UpdateError("更新信息格式不正确")

    version = data.get("version")
    tag = data.get("tag")
    asset = data.get("asset")
    size = data.get("size")
    sha256 = data.get("sha256")
    notes = data.get("notes", "")

    if not isinstance(version, str) or parse_version(version) is None:
        raise UpdateError("更新信息格式不正确")
    if not isinstance(tag, str) or not tag:
        raise UpdateError("更新信息格式不正确")
    if not isinstance(asset, str) or not asset:
        raise UpdateError("更新信息格式不正确")
    if "/" in asset or "\\" in asset or ".." in asset:
        raise UpdateError("更新信息格式不正确")
    # bool 也是 int，先排掉
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise UpdateError("更新信息格式不正确")
    if not isinstance(sha256, str) or not _SHA256_RE.match(sha256.lower()):
        raise UpdateError("更新信息格式不正确")

    return {
        "version": version,
        "tag": tag,
        "asset": asset,
        "size": size,
        "sha256": sha256.lower(),
        "notes": notes if isinstance(notes, str) else "",
    }


# ---------------------------------------------------------------- 下载源


class Source:
    """一个下载来源。name 用于界面显示（如「直连 GitHub」「gh-proxy.com」「Gitee」）。"""

    name = ""

    def fetch_manifest(self) -> dict:
        """取 latest.json。失败抛 UpdateError。"""
        raise NotImplementedError

    def asset_url(self, manifest: dict) -> str:
        """取更新包 zip 的地址。"""
        raise NotImplementedError


class GitHubSource(Source):
    """GitHub 本体，或一个加速代理。

    代理的用法是「前缀 + 完整 GitHub URL」，因此 prefix 为空即直连。
    """

    def __init__(self, prefix: str = "") -> None:
        self._prefix = prefix
        # 前缀可能是任意用户输入，取不出主机名就退回原串，至少界面上有东西显示
        host = urllib.parse.urlsplit(prefix).hostname if prefix else ""
        self.name = host or "直连 GitHub"

    def fetch_manifest(self) -> dict:
        url = (
            self._prefix
            + f"https://github.com/{catalog.UPDATE_REPO}/releases/latest/download/{MANIFEST_NAME}"
        )
        return parse_manifest(_get_bytes(url, _MANIFEST_TIMEOUT))

    def asset_url(self, manifest: dict) -> str:
        return (
            self._prefix
            + f"https://github.com/{catalog.UPDATE_REPO}/releases/download/"
            f"{manifest['tag']}/{manifest['asset']}"
        )


class GiteeSource(Source):
    """Gitee 镜像。

    未实测 —— 本次未启用（``catalog.GITEE_REPO`` 为空串）。启用前按 AGENTS.md
    「发版流程」实测一遍再放出去。

    Gitee 没有 ``releases/latest/download`` 这种固定地址，取清单得两步：
    先查 releases/latest 的 API，在 assets 里找到名为 latest.json 的那一项，
    再取它的 browser_download_url。
    """

    def __init__(self, repo: str) -> None:
        self._repo = repo
        self.name = "Gitee"

    def fetch_manifest(self) -> dict:
        api = f"https://gitee.com/api/v5/repos/{self._repo}/releases/latest"
        try:
            data = json.loads(_get_bytes(api, _MANIFEST_TIMEOUT).decode("utf-8"))
            assets = data["assets"]
            url = next(
                item["browser_download_url"]
                for item in assets
                if isinstance(item, dict) and item.get("name") == MANIFEST_NAME
            )
        except (KeyError, TypeError, ValueError, StopIteration, UnicodeError) as exc:
            raise UpdateError("Gitee 返回的数据无法识别") from exc
        if not isinstance(url, str) or not url:
            raise UpdateError("Gitee 返回的数据无法识别")
        return parse_manifest(_get_bytes(url, _MANIFEST_TIMEOUT))

    def asset_url(self, manifest: dict) -> str:
        return (
            f"https://gitee.com/{self._repo}/releases/download/"
            f"{manifest['tag']}/{manifest['asset']}"
        )


def build_sources(mirrors: list[str]) -> list[Source]:
    """直连在最前，其后是各加速代理，最后是 Gitee（``GITEE_REPO`` 非空时）。"""
    sources: list[Source] = [GitHubSource()]
    sources.extend(GitHubSource(prefix) for prefix in mirrors)
    if catalog.GITEE_REPO:
        sources.append(GiteeSource(catalog.GITEE_REPO))
    return sources


# ---------------------------------------------------------------- 检查


def check(sources: list[Source]) -> tuple[dict, list[Source]]:
    """并发向所有来源取清单，返回 (最先成功的清单, 下载时的来源顺序)。

    来源顺序 = 按「成功返回清单的先后」排列的来源，再接上其余来源（原顺序）。
    这样下载优先用最快的那个，它中途掉了还能逐个往下退。

    用 daemon 线程 + ``queue.Queue`` 而不是 ``ThreadPoolExecutor``：后者的工作线程
    不是 daemon，解释器退出时会被 join，一个卡住的代理能把关窗拖上八秒。
    第一个成功就立即返回，不等其余来源 —— 它们慢，正说明不该优先用。

    总等待上限比单个来源的超时多 2 秒，给线程启动与排队留余量。
    """
    if not sources:
        raise UpdateError("没有可用的下载来源")

    results: queue.Queue = queue.Queue()
    for index, source in enumerate(sources):
        threading.Thread(
            target=_fetch_into,
            args=(index, source, results),
            name=f"simple-tts-manifest-{index}",
            daemon=True,
        ).start()

    started = time.monotonic()
    deadline = _MANIFEST_TIMEOUT + 2
    errors: dict[int, str] = {}
    for _ in range(len(sources)):
        remaining = deadline - (time.monotonic() - started)
        if remaining <= 0:
            break
        try:
            index, outcome = results.get(timeout=remaining)
        except queue.Empty:
            break
        if isinstance(outcome, UpdateError):
            errors[index] = str(outcome)
            continue
        # 已成功的排前面（通常就是它自己），其余按原顺序接在后面
        ordered = [sources[index]] + [s for i, s in enumerate(sources) if i != index]
        return outcome, ordered

    lines = [f"{i + 1}. {source.name}：{errors.get(i, '超时')}" for i, source in enumerate(sources)]
    raise UpdateError("所有下载来源都失败了：\n" + "\n".join(lines))


def _fetch_into(index: int, source: Source, out: queue.Queue) -> None:
    """线程体：取清单，成功放清单、失败放 UpdateError，都带上下标。"""
    try:
        manifest = source.fetch_manifest()
    except UpdateError as exc:
        out.put((index, exc))
    except Exception as exc:  # noqa: BLE001
        out.put((index, UpdateError(f"{type(exc).__name__}: {exc}")))
    else:
        out.put((index, manifest))


# ---------------------------------------------------------------- 下载


def download(manifest: dict, sources: list[Source], on_progress, is_cancelled) -> str:
    """按 sources 顺序逐个尝试，把 zip 下到 ``update_dir()/asset`` 并返回其路径。

    - 先写 ``asset + '.part'``，边读边算 sha256，每读一块回调
      ``on_progress(done_bytes, total_bytes, source.name)``；
    - **整段读完**才校验：字节数对上 ``manifest['size']``、sha256 对上清单，
      任一不符就删掉 .part 换下一个来源。中途不许提前判定通过；
    - 全都不成才抛 UpdateError，消息里列出每个来源失败的原因；
    - ``total_bytes`` 取清单里的 size 而非 Content-Length —— 代理未必给后者。
    """
    os.makedirs(update_dir(), exist_ok=True)
    target = os.path.join(update_dir(), manifest["asset"])
    part = target + ".part"
    total = manifest["size"]
    errors: list[str] = []

    for source in sources:
        url = source.asset_url(manifest)
        digest = hashlib.sha256()
        done = 0
        try:
            if os.path.exists(part):
                os.remove(part)
            with _open(url, _DOWNLOAD_TIMEOUT) as response:
                with open(part, "wb") as handle:
                    while True:
                        if is_cancelled():
                            raise UpdateError("已取消")
                        chunk = response.read(_CHUNK)
                        if not chunk:
                            break
                        handle.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        on_progress(done, total, source.name)
        except UpdateError:
            _remove(part)
            raise
        except (urllib.error.URLError, OSError, ValueError) as exc:
            _remove(part)
            reason = getattr(exc, "reason", exc)
            errors.append(f"{source.name}：{reason}")
            continue

        # 读完了才判：中途的 done 只用于画进度，不能拿来当「下完了」的依据
        if done != total or digest.hexdigest() != manifest["sha256"]:
            _remove(part)
            errors.append(f"{source.name}：校验失败")
            continue

        os.replace(part, target)
        return target

    detail = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(errors)) or "无可用来源"
    raise UpdateError(f"下载失败：\n{detail}")


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------- 解压


def extract(zip_path: str) -> str:
    """解压到 ``update_dir()/staging``，返回含 ``SimpleTTS.exe`` 的那一层目录。

    ``zipfile.extractall`` 自己会去掉绝对路径与 ``..``，不必另做 zip-slip 防护
    （但仍要检查解出来的结构对不对）。约定 zip 顶层是 ``SimpleTTS/`` 目录，
    为容错也接受 exe 直接躺在解压根下。
    """
    staging = os.path.join(update_dir(), "staging")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(staging)
    except zipfile.BadZipFile as exc:
        raise UpdateError("更新包已损坏") from exc
    except OSError as exc:
        raise UpdateError(f"更新包解压失败：{exc}") from exc

    for candidate in (os.path.join(staging, "SimpleTTS"), staging):
        if os.path.isfile(os.path.join(candidate, EXE_NAME)):
            if os.path.isdir(os.path.join(candidate, _INTERNAL_DIR)):
                return candidate
            raise UpdateError("更新包内容不完整")
    raise UpdateError("更新包内容不完整")


# ---------------------------------------------------------------- 替换


def can_self_update() -> bool:
    """只有打包后的 exe 才能自我替换；源码运行时（启动.bat）返回 False。"""
    return getattr(sys, "frozen", False)


# 替换脚本。必须纯 ASCII —— cmd 按 OEM 代码页解析文件内容，混进多字节字符会
# 吞字断行（与 启动.bat 同一个道理），因此注释一律写英文 rem。
# 所有路径都经命令行参数传进来：参数是 Unicode，不受文件编码影响，程序目录
# 含中文也不会出问题。
#
# 探测主进程用的 tasklist / find 都写绝对路径：PATH 里若混进了 Git for Windows
# 的 usr\bin，那里的 find.exe 会把 PID 当文件名、报错退出 1 —— 恰好等于「进程已
# 退出」，脚本会在主进程还活着时就动手覆盖文件。
_APPLY_BAT = r"""@echo off
setlocal
set "PID=%~1"
set "SRC=%~2"
set "DST=%~3"
set "EXE=%~4"
set "RESTART=%~5"
set "RESULT=%~6"
set "TASKLIST=%SystemRoot%\System32\tasklist.exe"
set "FIND=%SystemRoot%\System32\find.exe"

rem Wait until the main process exits, up to about 60 seconds.
rem ping is used instead of timeout because timeout needs an attached console.
set /a N=0
:wait
"%TASKLIST%" /FI "PID eq %PID%" /NH 2>nul | "%FIND%" "%PID%" >nul
if errorlevel 1 goto copy
set /a N+=1
if %N% geq 60 goto fail
ping -n 2 127.0.0.1 >nul
goto wait

:copy
rem /IS on every pass: robocopy skips files whose size and 2-second-granularity
rem timestamp both match, and a version bump can easily produce a file that
rem differs only in content the size does not reveal. Better to rewrite.
rem _internal is ours alone: mirror it so stale files of the old version go away.
robocopy "%SRC%\_internal" "%DST%\_internal" /MIR /IS /R:5 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto fail
rem Top level and other subdirectories: overwrite and add only, never delete.
rem The install folder may hold user files (someone may have unpacked the zip
rem straight onto the desktop), so deleting is out of the question.
robocopy "%SRC%" "%DST%" /XD "%SRC%\_internal" /IS /R:5 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto fail
for /d %%D in ("%SRC%\*") do (
    if /i not "%%~nxD"=="_internal" (
        robocopy "%%D" "%DST%\%%~nxD" /E /IS /R:5 /W:1 /NFL /NDL /NJH /NJS /NP >nul
        if errorlevel 8 goto fail
    )
)
rd /s /q "%SRC%" 2>nul
if "%RESTART%"=="1" start "" /D "%DST%" "%DST%\%EXE%"
goto end

:fail
> "%RESULT%" echo fail
if "%RESTART%"=="1" start "" /D "%DST%" "%DST%\%EXE%"

:end
(goto) 2>nul & del "%~f0"
"""


def launch_apply(staged_dir: str, restart: bool) -> None:
    """写出替换脚本并以无窗口方式启动。调用方随后应退出程序。

    替换脚本先等本进程退出（否则 exe 与 Qt DLL 都被占用、拷不进去），再把
    staged 目录盖到程序目录上，最后按 restart 决定要不要把新 exe 拉起来。
    失败时它会写一个结果文件，由下次启动的 cleanup() 读出来提示用户。
    """
    bat_path = os.path.join(update_dir(), "apply_update.bat")
    os.makedirs(update_dir(), exist_ok=True)
    with open(bat_path, "w", encoding="ascii", newline="\r\n") as handle:
        handle.write(_APPLY_BAT)

    subprocess.Popen(
        [
            "cmd.exe",
            "/c",
            bat_path,
            str(os.getpid()),
            staged_dir,
            program_dir(),
            os.path.basename(sys.executable),
            "1" if restart else "0",
            os.path.join(update_dir(), _RESULT_FILE),
        ],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )


# ---------------------------------------------------------------- 启动清理


def cleanup() -> bool:
    """启动时调用：返回上次更新是否失败，随后整个删掉更新目录。

    目录不存在（绝大多数情况）直接返回 False。删不掉也不影响使用，
    顶多是把上次的更新包留在磁盘上。
    """
    directory = update_dir()
    if not os.path.isdir(directory):
        return False
    failed = os.path.exists(os.path.join(directory, _RESULT_FILE))
    shutil.rmtree(directory, ignore_errors=True)
    return failed
