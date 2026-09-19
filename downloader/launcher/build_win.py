#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 打包脚本: 把 launch.py 打成单文件 exe(视频下载器.exe)。

在 OseasyVM(Win11 ARM) 里用 WorkBuddy 运行本脚本:
    pip install -U pyinstaller yt-dlp      # 注意 -U: 用最新版 yt-dlp
    python build_win.py

说明:
- 鸿蒙机器上无法打 Windows exe, 必须在 Windows 上跑本脚本。
- 打出来的 exe 双击即用: 自动起本地服务 + 打开浏览器(PCL 式体验)。
- yt-dlp 作为模块打进 exe; 若同目录已放 ffmpeg.exe, 也会一并打进 exe(无需首运行下载)。
- **必须用 x64(amd64) 版 Python 打包**(见下面的架构门禁), ARM64 版 Python 打出来
  的 exe 在班级 x64 电脑上打不开。
- 想看报错窗口, 把下面 --noconsole 改成 --console 再打包。
"""
import os
import platform
import struct
import sys

import PyInstaller.__main__ as pyi

ROOT = os.path.dirname(os.path.abspath(__file__))
sep = os.pathsep  # Windows 上为 ';'

# ---------------------------------------------------------------- 架构门禁
# ARM64 原生 Python + PyInstaller 6.22+ 现在"能打包成功", 但产物是 ARM64 exe
# (PE Machine = 0xAA64), 在 x64 电脑上双击只会报"不是有效的 Win32 应用程序"。
# 静默产出废 exe 比直接报错危险得多, 所以这里硬拦一道, 打完再复核一次 PE 头。
MACHINE = (platform.machine() or "").upper()
if MACHINE in ("ARM64", "AARCH64"):
    print("")
    print("=" * 66)
    print("✗ 架构不对: 当前 Python 是 %s, 打出来的是 ARM64 exe。" % MACHINE)
    print("  这种 exe 在普通 x64 电脑上双击打不开(会提示不是有效的 Win32 应用)。")
    print("  解决: 另装一个 x86-64 / amd64 版 Python 再跑本脚本, 例如")
    print("    https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe")
    print("  装完确认一句:  python -c \"import platform;print(platform.machine())\"")
    print("  输出 AMD64 才对；输出 ARM64 就是装错了版本。")
    print("=" * 66)
    sys.exit(2)
print("· Python 架构:", MACHINE or "未知", "→ 可用于 x64 打包")

try:
    import yt_dlp
    print("· 内置 yt-dlp 版本:", getattr(yt_dlp.version, "__version__", "未知"))
except Exception:
    print("· ⚠️ 当前环境没有 yt_dlp 模块, 打出来的 exe 将无法解析视频")
    print("   先执行:  pip install -U yt-dlp")
    sys.exit(2)

datas = []
for f in ("index.html", "mux_fmp4.py"):
    p = os.path.join(ROOT, f)
    if os.path.exists(p):
        datas.append(p + sep + ".")
ff = os.path.join(ROOT, "ffmpeg.exe")
if os.path.exists(ff):
    datas.append(ff + sep + ".")
    print("· 检测到同目录 ffmpeg.exe, 将一起打进 exe(无需首运行下载)")

args = [
    os.path.join(ROOT, "launch.py"),
    "--onefile",
    "--noconsole",
    "--name", "视频下载器",
    "--hidden-import", "yt_dlp",
    "--collect-submodules", "yt_dlp",
]
for d in datas:
    args += ["--add-data", d]

print("开始打包(可能需要几分钟, 首次会从网络拉 yt-dlp)...")


def pe_machine(path):
    """读 PE 头 Machine 字段: 0x8664 = x64, 0xAA64 = ARM64。"""
    with open(path, "rb") as f:
        b = f.read(0x400)
    off = struct.unpack_from("<I", b, 0x3C)[0]
    return struct.unpack_from("<H", b, off + 4)[0]


pyi.run(args)

exe = os.path.join(ROOT, "dist", "视频下载器.exe")
print("完成。exe 在 dist/视频下载器.exe")
if os.path.exists(exe):
    m = pe_machine(exe)
    size = os.path.getsize(exe)
    print("产物自检: %.1f MB, PE Machine = 0x%04X (%s)  %s"
          % (size / 1048576.0, m, {0x8664: "x64", 0xAA64: "ARM64"}.get(m, "未知"),
             "✅ 可以发给 x64 电脑" if m == 0x8664 else "❌ 不要发出去, 架构不对"))
    if m != 0x8664:
        sys.exit(3)
else:
    print("⚠️ 没找到 dist 下的 exe, 打包可能失败了")
    sys.exit(1)
