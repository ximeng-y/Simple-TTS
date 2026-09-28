"""从 icons/icon.png 生成多尺寸 icons/icon.ico（手动执行，图标变更时才跑）。

    .venv\\Scripts\\python.exe tools\\make_icon.py

为什么用 PNG-in-ICO 而不是手写 DIB：ICO 的 32bpp DIB 像素是 BGRA 字节序，
手动打包时极易把 RGBA 写反，结果蓝色显示成橙色，且这种错自测时（用同样写反
的逻辑读回）会“自洽地通过”，很难发现。改成每个尺寸直接塞一张 PNG（由 Qt 编码，
通道顺序它自己保证），彻底绕开这一类错误；Vista+ 的资源管理器与 PyInstaller
都支持 PNG 压缩的图标条目。生成后可用同目录思路复核：把每条 PNG 抽出来看中心
像素应为蓝（B 高 R 低）。
"""

from __future__ import annotations

import os
import struct
import sys

from PySide6.QtCore import Qt, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QGuiApplication, QImage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "icons", "icon.png")
DST = os.path.join(ROOT, "icons", "icon.ico")
# 覆盖资源管理器/任务栏/标题栏会用到的整套尺寸；256 在目录项里用 0 表示
SIZES = [16, 24, 32, 48, 64, 128, 256]


def main() -> None:
    QGuiApplication(sys.argv)  # QImage 的缩放/编码需要 GUI application 实例

    src = QImage(SRC)
    if src.isNull():
        sys.exit(f"读不到源图：{SRC}")

    pngs = []
    for size in SIZES:
        img = src.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        buffer = QBuffer(QByteArray())
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not img.save(buffer, "PNG"):
            sys.exit(f"PNG 编码失败：{size}px")
        pngs.append(bytes(buffer.data()))
        buffer.close()

    # ICONDIR: reserved=0, type=1(icon), count；随后每尺寸一条 16 字节目录项
    header = struct.pack("<HHH", 0, 1, len(SIZES))
    offset = len(header) + 16 * len(SIZES)
    entries = bytearray()
    payload = bytearray()
    for size, data in zip(SIZES, pngs):
        dim = 0 if size == 256 else size
        # bWidth,bHeight,bColorCount,bReserved,wPlanes,wBitCount,dwBytesInRes,dwImageOffset
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)

    with open(DST, "wb") as handle:
        handle.write(header + bytes(entries) + bytes(payload))
    print(f"已写出 {DST}：{len(SIZES)} 个尺寸，{os.path.getsize(DST)} 字节")


if __name__ == "__main__":
    main()
