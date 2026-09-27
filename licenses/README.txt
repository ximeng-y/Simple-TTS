Simple TTS 随附的第三方组件与许可
==================================

本目录收的是随程序一同分发的第三方组件的许可文件。这些条款独立于本程序自身
的许可，特此说明。


Qt for Python（PySide6-Essentials 6.11.2）与 Qt 6
--------------------------------------------------

许可：GNU Lesser General Public License v3（LGPLv3）
许可正文见同目录下的 LGPL-3.0.txt 与 GPL-3.0.txt
（LGPLv3 以引用 GPLv3 条款的方式成立，因此两份都需要随附）。

本程序使用的是 PySide6-Essentials，其中包含的 Qt 模块为 Core、Gui、Widgets，
均为 LGPLv3；未使用 Qt Charts、Data Visualization、Virtual Keyboard 等
仅限 GPL 的模块。

对应源码的获取地址：

- Qt for Python（PySide6）：
  https://code.qt.io/cgit/pyside/pyside-setup.git/
- Qt 本体：
  https://download.qt.io/

LGPLv3 要求使用者能够替换本程序所使用的 Qt 库。本程序以解压即用的目录形式
分发（非单文件打包），Qt 的动态链接库就放在程序目录下的：

    _internal\PySide6\

其中的 DLL 可以直接用任何 ABI 兼容的版本替换，替换后本程序会使用替换后的
库运行。程序目录下的其他文件不参与 Qt 的版本选择，替换 Qt 库无需重新编译
本程序。PySide6 的 Python 模块（.pyd 与附带的 .py）同样位于该目录。


Python 运行时
-------------

许可：PSF License Agreement（见 https://docs.python.org/3/license.html）
本程序由 PyInstaller 打包，程序目录的 _internal\ 下含 Python 解释器与标准库。

PyInstaller 的引导程序（bootloader）以 GPL-2.0-or-later 附带例外条款分发，
例外允许打包专有程序，因此不要求本程序以 GPL 发布。
