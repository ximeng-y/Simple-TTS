"""打包发版脚本（手动执行，不接入 CI）。

跑一遍就把 release 需要的两个文件产出来：

    dist/SimpleTTS-{version}-win64.zip    程序本体（zip 顶层是 SimpleTTS/ 目录）
    dist/latest.json                      更新清单，客户端按它判断与校验

用法（在项目根目录）：

    .venv\\Scripts\\python.exe tools\\build_release.py --notes-file .XMTEMP\\notes.txt

之后把这两个文件连同 tag 一起发到 GitHub Release。完整流程见 AGENTS.md「发版流程」。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
APP_DIR = os.path.join(DIST, "SimpleTTS")
EXE_NAME = "SimpleTTS.exe"
# 版本号只认 x.y.z：清单里的 tag 与文件名都由它拼出来，形状不对就不该继续
_VERSION_RE = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE)
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

# 不进 zip 的目录。userdata/ 是本地试跑留下的，里面有按当前 Windows 账户加密的
# API Key 密文与合成产物，绝不能跟着发布包发出去。
_EXCLUDED_DIRS = {"userdata"}


def read_version() -> str:
    path = os.path.join(ROOT, "simple_tts", "__init__.py")
    with open(path, encoding="utf-8") as handle:
        match = _VERSION_RE.search(handle.read())
    if not match:
        sys.exit(f"读不到 __version__：{path}")
    version = match.group(1)
    if not _SEMVER_RE.match(version):
        sys.exit(f"__version__ 必须是 x.y.z 形式，当前是 {version!r}")
    return version


def run_pyinstaller() -> None:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "SimpleTTS",
        "main.py",
    ]
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def copy_licenses() -> None:
    """把仓库里的 licenses/ 拷进程序目录 —— LGPLv3 要求许可随二进制分发。"""
    source = os.path.join(ROOT, "licenses")
    target = os.path.join(APP_DIR, "licenses")
    if not os.path.isdir(source):
        sys.exit(f"缺少许可文件目录：{source}")
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target)
    print("已拷入许可文件：", ", ".join(sorted(os.listdir(target))))


def make_zip(version: str) -> str:
    """把程序目录打成 zip，返回产物路径。arcname 一律以 SimpleTTS/ 开头。"""
    zip_path = os.path.join(DIST, f"SimpleTTS-{version}-win64.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for base, dirs, files in os.walk(APP_DIR):
            # 原地改 dirs 才能剪掉整棵子树，os.walk 是按它决定往下走的
            dirs[:] = [name for name in dirs if name not in _EXCLUDED_DIRS]
            for name in files:
                full = os.path.join(base, name)
                arcname = os.path.join("SimpleTTS", os.path.relpath(full, APP_DIR))
                archive.write(full, arcname.replace("\\", "/"))
    return zip_path


def write_manifest(version: str, zip_path: str, notes: str) -> str:
    """算 zip 的 sha256 与大小，写 latest.json。字段约定见 AGENTS.md「发版流程」。"""
    digest = hashlib.sha256()
    with open(zip_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    manifest = {
        "version": version,
        "tag": f"v{version}",
        "asset": os.path.basename(zip_path),
        "size": os.path.getsize(zip_path),
        "sha256": digest.hexdigest(),
        "notes": notes,
    }
    path = os.path.join(DIST, "latest.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="打包 Simple TTS 并生成更新清单")
    parser.add_argument(
        "--notes-file",
        help="UTF-8 文本文件，内容作为 latest.json 的更新说明（缺省则留空）",
    )
    args = parser.parse_args()

    notes = ""
    if args.notes_file:
        if not os.path.isfile(args.notes_file):
            sys.exit(f"找不到说明文件：{args.notes_file}")
        with open(args.notes_file, encoding="utf-8") as handle:
            notes = handle.read().strip()
    else:
        print("（未给 --notes-file，更新说明留空）")

    version = read_version()
    print(f"版本号：{version}")

    shutil.rmtree(os.path.join(ROOT, "build"), ignore_errors=True)
    shutil.rmtree(DIST, ignore_errors=True)

    run_pyinstaller()

    if not os.path.isfile(os.path.join(APP_DIR, EXE_NAME)):
        sys.exit(f"打包结果里没有 {EXE_NAME}：{APP_DIR}")
    if not os.path.isdir(os.path.join(APP_DIR, "_internal")):
        sys.exit(f"打包结果里没有 _internal/：{APP_DIR}")

    copy_licenses()
    zip_path = make_zip(version)
    manifest_path = write_manifest(version, zip_path, notes)

    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print()
    print("产物：")
    print(f"  {zip_path}  （{size_mb:.1f} MB）")
    print(f"  {manifest_path}")
    print()
    print("下一步（详见 AGENTS.md「发版流程」）：")
    print(f"  1. 双击 {os.path.join(APP_DIR, EXE_NAME)} 冒烟；跑完删掉它生成的 userdata/")
    print(f"  2. git tag v{version} && git push origin v{version}")
    print(f'  3. gh release create v{version} "{zip_path}" "{manifest_path}" --title "v{version}" --notes-file <说明文件>')
    print("     （不要勾选 pre-release，否则 releases/latest 不会指向它）")


if __name__ == "__main__":
    main()
