#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 打包脚本: 把 launch.py 打成单文件 exe(视频下载器.exe)。

在 OseasyVM(Win11 ARM) 里用 WorkBuddy 运行本脚本:
    pip install pyinstaller yt-dlp
    python build_win.py

说明:
- 鸿蒙机器上无法打 Windows exe, 必须在 Windows 上跑本脚本。
- 打出来的 exe 双击即用: 自动起本地服务 + 打开浏览器(PCL 式体验)。
- yt-dlp 作为模块打进 exe; 若同目录已放 ffmpeg.exe, 也会一并打进 exe(无需首运行下载)。
- 想看报错窗口, 把下面 --noconsole 改成 --console 再打包。
"""
import os
import PyInstaller.__main__ as pyi

ROOT = os.path.dirname(os.path.abspath(__file__))
sep = os.pathsep  # Windows 上为 ';'

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
pyi.run(args)
print("完成。exe 在 dist/视频下载器.exe")
