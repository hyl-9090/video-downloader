#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""视频下载器 · 自举启动器（单目录分发版）
双击/运行后: 检测系统 -> 自检 yt-dlp -> 选合并方式 -> 起本地服务 -> 开浏览器。
- 鸿蒙(HarmonyOS): yt-dlp 用已装 python 包; 合并用内置 mux_fmp4.py(绕过崩掉的 ffmpeg)
- 其它系统(Win/Mac/Linux): yt-dlp 用同目录单文件; 合并用同目录/系统 ffmpeg
依赖缺失时自动从网上下载对应平台版本(首次运行)。
"""
import os, sys, json, re, threading, queue, subprocess, glob, tempfile, urllib.parse, webbrowser, platform, shutil, socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    # PyInstaller onefile: 运行时解压到临时目录, 下载目录放到用户下载文件夹以保证持久
    DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads", "视频下载器")
else:
    DOWNLOADS = os.path.join(ROOT, "downloads")
os.makedirs(DOWNLOADS, exist_ok=True)
MUX = os.path.join(ROOT, "mux_fmp4.py")
if not os.path.exists(MUX):
    MUX = "/storage/Users/currentUser/.local/opt/mux_fmp4.py"
FFMPEG = None  # 非鸿蒙时设置
# 依赖准备状态: 前端 /status 会读它, 让"首次下载组件"不再表现为双击假死
DEPS = {"ready": False, "phase": "正在准备运行环境…", "notes": [], "error": None}
DEPS_DONE = threading.Event()


def _exe_dir():
    """exe 所在目录(frozen 时才有意义): 方便手动丢一个 ffmpeg.exe 到 exe 旁边。"""
    if getattr(sys, "frozen", False):
        try:
            return os.path.dirname(os.path.abspath(sys.executable))
        except Exception:
            pass
    return ROOT


def _persist_dir(create=False):
    """持久化目录。onefile 模式下 ROOT 是临时解压目录, 依赖放那儿 = 每次运行都重下。"""
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "VideoDownloader", "bin")
    else:
        d = os.path.join(ROOT, "bin")
    if create:
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
    return d


def dep_status(msg=None, **kw):
    if msg:
        DEPS["phase"] = msg
    DEPS.update(kw)


def is_harmony():
    if platform.system() == "HarmonyOS":
        return True
    # 兜底: aarch64 + musl 加载器(鸿蒙特征)
    if platform.machine() == "aarch64" and os.path.exists("/lib/ld-musl-aarch64.so.1"):
        return True
    return False


def have_yt_dlp_api():
    try:
        import yt_dlp  # noqa
        return True
    except Exception:
        return False


YTDL_BIN = None  # 单文件模式时的可执行路径


def resolve_ytdl():
    """返回 yt-dlp 调用方式: 'module' / 'bin' / None。"""
    global YTDL_BIN
    if have_yt_dlp_api():
        return "module"
    exe = os.path.join(ROOT, "yt-dlp.exe") if platform.system() == "Windows" else os.path.join(ROOT, "yt-dlp")
    if os.path.exists(exe):
        YTDL_BIN = exe
        return "bin"
    if download_yt_dlp(exe):
        YTDL_BIN = exe
        return "bin"
    return None


def ensure_deps():
    """自检依赖, 缺失则尝试下载。返回 (ytdl_mode, notes)。"""
    notes = []
    mode = resolve_ytdl()
    if mode == "module":
        notes.append("yt-dlp: 使用已装 Python 包")
    elif mode == "bin":
        notes.append("yt-dlp: 同目录单文件" if os.path.exists(YTDL_BIN) else "yt-dlp: 已下载单文件")
    else:
        notes.append("yt-dlp: 不可用, 请手动安装或联网首运行")
    # ffmpeg (非鸿蒙)
    global FFMPEG
    if not is_harmony():
        dep_status("正在准备合并组件 ffmpeg…")
        fe = find_ffmpeg()
        if fe:
            FFMPEG = fe
            d = os.path.dirname(os.path.normpath(fe))
            where = "内置/同目录" if d in (os.path.normpath(ROOT), os.path.normpath(_exe_dir())) else \
                    ("本地缓存(以后直接用)" if d == os.path.normpath(_persist_dir()) else "系统 PATH")
            notes.append("ffmpeg: " + where)
        elif download_ffmpeg():
            notes.append("ffmpeg: 已下载并缓存到本地(以后不再下载)")
        else:
            notes.append("ffmpeg: 未找到(合并不可用, 请选含音频格式或手动安装)")
    else:
        notes.append("ffmpeg: 鸿蒙用内置 Python 合并器(无需 ffmpeg)")
    return mode, notes


def download_yt_dlp(dest):
    # 从 GitHub release 下载对应平台单文件
    base = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
    name = "yt-dlp.exe" if platform.system() == "Windows" else "yt-dlp"
    url = base + name
    try:
        import urllib.request
        print("下载 yt-dlp 单文件(首次运行)...")
        urllib.request.urlretrieve(url, dest)
        os.chmod(dest, 0o755)
        return os.path.exists(dest)
    except Exception as e:
        print("下载 yt-dlp 失败:", e)
        return False


def find_ffmpeg():
    """按 内置/同目录 -> exe 旁边 -> 本地缓存 -> 系统 PATH 的顺序找 ffmpeg。"""
    names = ["ffmpeg.exe"] if platform.system() == "Windows" else ["ffmpeg"]
    cands = []
    for n in names:
        cands.append(os.path.join(ROOT, n))            # 打包内置的 / 源码目录的
        cands.append(os.path.join(_exe_dir(), n))      # 用户手动丢到 exe 旁边的
        cands.append(os.path.join(_persist_dir(), n))  # 上次自动下好的缓存
    for c in cands:
        try:
            if c and os.path.exists(c):
                return c
        except Exception:
            pass
    return shutil.which("ffmpeg")


FFMPEG_URLS = [
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
]


def _extract_ffmpeg(zf, dest):
    """从 ffmpeg 的 zip 里刨出 bin/ffmpeg.exe 写进 dest。"""
    for nm in zf.namelist():
        if nm.replace("\\", "/").endswith("/bin/ffmpeg.exe"):
            with zf.open(nm) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            try:
                os.chmod(dest, 0o755)
            except Exception:
                pass
            return True
    return False


def download_ffmpeg():
    """首次运行把 ffmpeg 下到**持久目录**(只下一次, 之后复用; 不再每次重下)。"""
    global FFMPEG
    if platform.system() != "Windows":
        return False
    import io, zipfile, urllib.request
    dest = os.path.join(_persist_dir(create=True), "ffmpeg.exe")
    if os.path.exists(dest):                      # 已缓存, 直接用
        FFMPEG = dest
        return True
    part = dest + ".part"
    for url in FFMPEG_URLS:
        try:
            dep_status("正在下载合并组件 ffmpeg（首次约 50MB，只下一次）…")
            print("下载 ffmpeg:", url)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            dep_status("正在解压 ffmpeg…")
            if _extract_ffmpeg(zipfile.ZipFile(io.BytesIO(data)), part):
                os.replace(part, dest)            # 完整了再落盘, 避免半成品被当成好的
                FFMPEG = dest
                print("ffmpeg 已缓存到:", dest)
                return True
            print("该源里没找到 bin/ffmpeg.exe, 换下一个源")
        except Exception as e:
            print("下载 ffmpeg 失败(%s): %s" % (url, e))
    try:
        if os.path.exists(part):
            os.remove(part)
    except Exception:
        pass
    return False


# ---------------- yt-dlp 调用封装 (module / bin 两种模式) ----------------
def ydl_extract(url, cookie):
    if not (have_yt_dlp_api() or YTDL_BIN):
        return None, "yt-dlp 不可用"
    info, err = _ydl_extract_once(url, cookie)
    if err and cookie:
        # 粘错/过期的 cookie 会让**整个解析**失败 -> 丢掉 cookie 再试一次, 至少能用
        info2, err2 = _ydl_extract_once(url, "")
        if not err2 and info2:
            info2["_cookie_dropped"] = True
            return info2, None
    return info, err


def _ydl_extract_once(url, cookie):
    if have_yt_dlp_api():
        return ydl_extract_mod(url, cookie)
    return ydl_extract_bin(url, cookie)


def ydl_extract_mod(url, cookie):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "simulate": True, "skip_download": True,
            "retries": 5, "fragment_retries": 5, "socket_timeout": 30}
    cf = write_cookie(cookie, url) if cookie else None
    if cf:
        opts["cookiefile"] = cf
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False), None
    except Exception as e:
        return None, str(e)[:400]
    finally:
        if cf and os.path.exists(cf):
            try: os.remove(cf)
            except Exception: pass


def ydl_extract_bin(url, cookie):
    args = [YTDL_BIN, "-J", "--simulate", "--retries", "5", "--socket-timeout", "30", url]
    cf = write_cookie(cookie, url) if cookie else None
    if cf:
        args += ["--cookies", cf]
    try:
        out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
        return json.loads(out), None
    except Exception as e:
        return None, str(e)[:400]
    finally:
        if cf and os.path.exists(cf):
            try: os.remove(cf)
            except Exception: pass


def ydl_download(url, fmt, cookie, hooks, outtmpl):
    if have_yt_dlp_api():
        return ydl_download_mod(url, fmt, cookie, hooks, outtmpl)
    if YTDL_BIN:
        return ydl_download_bin(url, fmt, cookie, hooks, outtmpl)
    raise RuntimeError("yt-dlp 不可用")


def ydl_download_mod(url, fmt, cookie, hooks, outtmpl):
    import yt_dlp
    opts = {"format": fmt, "outtmpl": outtmpl, "progress_hooks": [hooks], "quiet": True, "noplaylist": True, "noprogress": True,
            # 国内 CDN(如 B站 mcdn) 偶发抽风, 多试几次比直接失败强
            "retries": 10, "fragment_retries": 10, "socket_timeout": 30}
    cf = write_cookie(cookie, url) if cookie else None
    if cf:
        opts["cookiefile"] = cf
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    finally:
        if cf and os.path.exists(cf):
            try: os.remove(cf)
            except Exception: pass


def ydl_download_bin(url, fmt, cookie, hooks, outtmpl):
    import re as _re
    args = [YTDL_BIN, "-f", fmt, "-o", outtmpl, "--noplaylist", "--newline",
            "--retries", "10", "--fragment-retries", "10", "--socket-timeout", "30"]
    cf = write_cookie(cookie, url) if cookie else None
    if cf:
        args += ["--cookies", cf]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1)
    for line in proc.stderr:
        m = _re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", line)
        if m:
            hooks({"status": "downloading", "_percent_str": m.group(1) + "%", "filename": os.path.basename(outtmpl)})
    proc.wait()
    if cf and os.path.exists(cf):
        try: os.remove(cf)
        except Exception: pass
    if proc.returncode != 0:
        raise RuntimeError("yt-dlp 下载失败(returncode=%s)" % proc.returncode)


def merge_av(vpath, apath, final):
    # 首次运行时 ffmpeg 可能还在后台下, 等一下(最多5分钟), 别直接判失败
    if not is_harmony() and not DEPS.get("ready"):
        DEPS_DONE.wait(300)
    if is_harmony() and os.path.exists(MUX):
        r = subprocess.run([sys.executable, MUX, vpath, apath, final], capture_output=True, text=True)
        return (r.returncode == 0 and os.path.exists(final), "内置合并器(绕过 ffmpeg)" if r.returncode == 0 else "合并失败:" + (r.stderr or "")[:200])
    elif FFMPEG:
        r = subprocess.run([FFMPEG, "-i", vpath, "-i", apath, "-c", "copy", final, "-y"], capture_output=True, text=True)
        return (r.returncode == 0 and os.path.exists(final), "ffmpeg 合并" if r.returncode == 0 else "ffmpeg 合并失败")
    return False, "本机无 ffmpeg 且非鸿蒙, 无法合并; 请选含音频格式"


def normalize_cookie(text, url=""):
    """把用户粘进来的 cookie 统一成 yt-dlp 能读的 Netscape 格式。

    yt-dlp 只认**严格的 Netscape 格式**(且必须有 '# Netscape HTTP Cookie File' 头行),
    所以这里做两件事:
      1) 已经是 Netscape(含制表符分隔列)的 → 只补上头行
      2) 是浏览器 F12 里那串 'SESSDATA=xx; bili_jct=yy'(或带 'Cookie: ' 前缀)的 → 自动转换
    这样"不会用扩展的老师"也能直接用 F12 复制粘贴。
    """
    t = (text or "").strip()
    if not t:
        return None
    # 1) 看起来已经是 Netscape 格式(有制表符分隔的列)
    if "\t" in t or t.startswith("# Netscape") or t.startswith("# HTTP Cookie File"):
        if not t.startswith("#"):
            t = "# Netscape HTTP Cookie File\n" + t
        return t if t.endswith("\n") else t + "\n"
    # 2) 请求头风格: 支持 'Cookie: a=b; c=d' 与 'a=b; c=d'
    body = t
    if body[:7].lower() == "cookie:":
        body = body.split(":", 1)[1]
    skip = {"path", "domain", "expires", "max-age", "secure", "httponly", "samesite", "priority"}
    pairs = []
    for part in re.split(r"[;\n]", body):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        if not k or k.lower() in skip:
            continue
        pairs.append((k, v.strip()))
    if not pairs:
        return None
    # 域名从视频链接推(取末两段, 如 www.bilibili.com -> .bilibili.com)
    host = "."
    try:
        h = urllib.parse.urlparse(url).hostname or ""
        seg = [x for x in h.split(".") if x]
        if len(seg) >= 2:
            host = "." + ".".join(seg[-2:])
        elif seg:
            host = seg[0]
    except Exception:
        pass
    lines = ["# Netscape HTTP Cookie File"]
    for k, v in pairs:
        lines.append("\t".join([host, "TRUE", "/", "TRUE", "4102444800", k, v]))
    return "\n".join(lines) + "\n"


def write_cookie(text, url=""):
    norm = normalize_cookie(text, url)
    if not norm:
        return None
    fd, p = tempfile.mkstemp(suffix=".txt", dir=DOWNLOADS)
    with os.fdopen(fd, "w") as f:
        f.write(norm)
    return p


# ---------------- HTTP 服务 ----------------
tasks = {}
_lock = threading.Lock()
_counter = [0]


def new_id():
    with _lock:
        _counter[0] += 1
        return str(_counter[0])


def safe_name(s):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", s or "")
    return s.strip().strip(".")[:80] or "video"


# ---------------- 格式聚合: 把一堆原始流收成「一行一个清晰度」 ----------------
def _size_of(f):
    return f.get("filesize") or f.get("filesize_approx") or 0


def _is_approx(f):
    # 有 filesize = 精确值; 只有 filesize_approx 或完全靠码率估 = 大约值
    return not f.get("filesize")


def _bitrate(f):
    return f.get("tbr") or f.get("abr") or f.get("vbr") or 0


def _est_size(f, duration):
    """没有 filesize 时用 码率x时长 估一个, 好让界面能显示大小。"""
    s = _size_of(f)
    if s:
        return int(s)
    br = _bitrate(f)
    if br and duration:
        try:
            return int(float(br) * 1000 / 8 * float(duration))
        except Exception:
            return 0
    return 0


def human_res(h, fps=None):
    if not h:
        return "原始画质"
    try:
        h = int(h)
    except Exception:
        return str(h)
    names = {4320: "8K", 2160: "4K", 1440: "2K", 1080: "1080P", 720: "720P",
             480: "480P", 360: "360P", 240: "240P", 144: "144P"}
    label = names.get(h, "%dP" % h)
    try:
        if fps and float(fps) >= 50:
            label += " 60fps"
    except Exception:
        pass
    return label


def _codec_short(c):
    c = (c or "").lower()
    if not c or c == "none":
        return ""
    for pre, nm in (("avc", "H.264"), ("h264", "H.264"), ("hev", "H.265"), ("hvc", "H.265"),
                    ("h265", "H.265"), ("av01", "AV1"), ("vp09", "VP9"), ("vp9", "VP9"),
                    ("vp8", "VP8"), ("mp4a", "AAC"), ("aac", "AAC"), ("opus", "Opus"),
                    ("flac", "FLAC"), ("mp3", "MP3")):
        if c.startswith(pre):
            return nm
    return c.split(".")[0][:6]


def _mk(label, fmt, vfmt, afmt, merge, size, approx, vcodec, acodec, ext, h=0):
    return {"label": label, "fmt": fmt, "vfmt": vfmt, "afmt": afmt, "merge": bool(merge),
            "filesize": int(size) if size else None, "size_approx": bool(approx),
            "vcodec": vcodec or "", "acodec": acodec or "", "ext": ext or "", "h": int(h or 0)}


def build_choices(info):
    """按清晰度聚合。每档优先「纯视频流+最佳音频」(画质更高), 没有独立音轨时退回整段流。"""
    formats = [f for f in (info.get("formats") or []) if f.get("format_id")]
    duration = info.get("duration") or 0
    vids, auds, progs = [], [], []
    for f in formats:
        v = f.get("vcodec") or "none"
        a = f.get("acodec") or "none"
        if v == "none" and a == "none":
            continue
        if v != "none" and a != "none":
            progs.append(f)
        elif v != "none":
            vids.append(f)
        else:
            auds.append(f)

    best_audio = max(auds, key=_bitrate, default=None)
    a_size = _est_size(best_audio, duration) if best_audio else 0
    a_approx = _is_approx(best_audio) if best_audio else False
    a_codec = _codec_short(best_audio.get("acodec")) if best_audio else ""

    def by_height(lst):
        g = {}
        for f in lst:
            h = f.get("height")
            if not h:
                continue
            cur = g.get(h)
            if cur is None or _bitrate(f) > _bitrate(cur):
                g[h] = f
        return g

    vg, pg = by_height(vids), by_height(progs)
    choices = []
    for h in sorted(set(list(vg.keys()) + list(pg.keys())), reverse=True):
        vf, pf = vg.get(h), pg.get(h)
        if vf is not None and best_audio is not None:
            vsize = _est_size(vf, duration)
            choices.append(_mk(
                human_res(h, vf.get("fps")),
                "%s+%s" % (vf["format_id"], best_audio["format_id"]),
                vf["format_id"], best_audio["format_id"], True,
                vsize + a_size, _is_approx(vf) or a_approx,
                _codec_short(vf.get("vcodec")), a_codec,
                vf.get("ext") or "mp4", h))
        elif pf is not None:
            choices.append(_mk(
                human_res(h, pf.get("fps")), pf["format_id"], pf["format_id"], None, False,
                _est_size(pf, duration), _is_approx(pf),
                _codec_short(pf.get("vcodec")), _codec_short(pf.get("acodec")),
                pf.get("ext") or "mp4", h))

    if best_audio is not None and choices:
        choices.append(_mk("仅音频", best_audio["format_id"], None, best_audio["format_id"],
                           False, a_size, a_approx, "", a_codec,
                           best_audio.get("ext") or "m4a", 0))

    if not choices:
        # 拿不到分辨率信息(纯音频/直播回放等): 退回「最高码率的整段流」
        pool = progs or vids or formats
        pf = max(pool, key=_bitrate, default=None)
        if pf is not None:
            is_v = (pf.get("vcodec") or "none") != "none"
            choices.append(_mk(
                human_res(pf.get("height")) if is_v else "仅音频",
                pf["format_id"], pf["format_id"], None, is_v and (pf.get("acodec") or "none") == "none",
                _est_size(pf, duration), _is_approx(pf),
                _codec_short(pf.get("vcodec")), _codec_short(pf.get("acodec")),
                pf.get("ext") or "mp4", pf.get("height") or 0))
    return choices


# ---------------- 链接识别: 从"分享文案"里抠出真链接 ----------------
def normalize_url(raw):
    """抖音/快手/小红书等 App 的"分享->复制链接"给的是**一整段文案**,
    链接夹在汉字中间。这里自动把它抠出来, 顺带支持只粘 BV 号。
    """
    s = (raw or "").strip()
    if not s:
        return ""
    # 1) 文案里抠 http(s) 链接(中文标点/引号/空格都当边界)
    m = re.search(r'https?://[^\s，,、。；;！!？?"\'<>()（）【】\[\]]+', s)
    if m:
        return m.group(0).rstrip(".,;!")
    # 2) 只粘了 B站 BV 号 / av 号
    m = re.search(r'(BV[0-9A-Za-z]{10})', s)
    if m:
        return "https://www.bilibili.com/video/" + m.group(1)
    m = re.search(r'\bav(\d{4,})', s, re.I)
    if m:
        return "https://www.bilibili.com/video/av" + m.group(1)
    # 3) 其它情况原样返回(交给 yt-dlp 判断)
    return s


# ---------------- 已知下不了的平台: 提前拦截, 直接说人话 ----------------
# 依据: 实测 yt-dlp 2026.08.19 的提取器清单(共 1751 个), 以下平台**没有**任何提取器。
# 与其让用户对着 "Unsupported URL" 的英文报错发呆, 不如一进来就告诉他怎么回事。
UNSUPPORTED_PLATFORMS = [
    (("channels.weixin.qq.com", "weixin.qq.com/sph", "mp.weixin.qq.com"),
     "微信视频号（以及公众号文章里的视频）目前下不了",
     "微信的视频是加密的、必须登录微信才能看，公开的下载工具都拿不到，这不是本工具的问题。"
     "替代办法：① 请视频作者把原视频文件发给你；② 用手机自带的「屏幕录制」功能录下来。"),
    (("kuaishou.com", "gifshow.com", "kwai.com"),
     "快手目前下不了",
     "下载引擎（yt-dlp）还没有支持快手。"
     "替代办法：① 在快手 App 里看作者是否允许「保存到相册」；② 用手机录屏。"),
    (("weishi.qq.com",),
     "腾讯微视目前下不了",
     "下载引擎还没有支持微视。可以用手机录屏，或让作者发原视频。"),
    (("pipixia", "pipigx"),
     "皮皮虾目前下不了",
     "下载引擎还没有支持皮皮虾。可以用手机录屏。"),
    (("migu.cn", "miguvideo.com"),
     "咪咕视频目前下不了",
     "下载引擎还没有支持咪咕视频。"),
]


def unsupported_hint(url):
    """命中已知不支持的平台时, 返回一句人话说明; 否则返回 None。"""
    u = (url or "").lower()
    for keys, title, advice in UNSUPPORTED_PLATFORMS:
        if any(k in u for k in keys):
            return title + "。" + advice
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            try:
                with open(os.path.join(ROOT, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except Exception as e:
                self._send(500, str(e))
        elif p == "/progress":
            self.serve_sse()
        elif p == "/file":
            self.serve_file()
        elif p == "/health":
            self._send(200, json.dumps({"ok": True, "harmony": is_harmony()}))
        elif p == "/status":
            self._send(200, json.dumps({"ready": bool(DEPS.get("ready")), "phase": DEPS.get("phase") or "",
                                        "notes": DEPS.get("notes") or [], "error": DEPS.get("error"),
                                        "harmony": is_harmony()}, ensure_ascii=False))
        else:
            self._send(404, "not found")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b""
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        if self.path == "/parse":
            self.handle_parse(data)
        elif self.path == "/download":
            self.handle_download(data)
        else:
            self._send(404, "not found")

    def handle_parse(self, data):
        url = normalize_url(data.get("url"))
        cookie = (data.get("cookie") or "").strip()
        if not url:
            self._send(400, json.dumps({"error": "url 为空"}))
            return
        hint = unsupported_hint(url)
        if hint:
            self._send(200, json.dumps({"error": hint, "friendly": True}, ensure_ascii=False))
            return
        info, err = ydl_extract(url, cookie)
        if err:
            self._send(200, json.dumps({"error": err}, ensure_ascii=False))
            return
        fmts = []
        for f in info.get("formats", []):
            fmts.append({
                "format_id": f.get("format_id"), "ext": f.get("ext"),
                "resolution": (f.get("resolution") or (str(f.get("height")) + "p" if f.get("height") else "")),
                "vcodec": f.get("vcodec") or "none", "acodec": f.get("acodec") or "none",
                "tbr": f.get("tbr"), "filesize": f.get("filesize") or f.get("filesize_approx"),
                "protocol": f.get("protocol"),
            })
        warn = None
        if info.get("_cookie_dropped"):
            warn = ("你填的 cookie 好像无效或已过期（带着它反而解析不了），已经自动改用「不带 cookie」重试成功。"
                    "想要更高画质，请重新复制一次最新的 cookie；不需要就把它清空。")
        self._send(200, json.dumps({
            "title": info.get("title", ""),
            "thumbnail": info.get("thumbnail") or "",
            "uploader": info.get("uploader") or info.get("channel") or info.get("creator") or "",
            "duration": info.get("duration"),
            "webpage_url": info.get("webpage_url", url),
            "choices": build_choices(info),
            "formats": fmts,
            "warn": warn,
        }, ensure_ascii=False))

    def handle_download(self, data):
        url = normalize_url(data.get("url"))
        fmt = (data.get("format_id") or "").strip()
        cookie = (data.get("cookie") or "").strip()
        if not url or not fmt:
            self._send(400, json.dumps({"error": "缺少 url 或 format_id"}))
            return
        vfmt = (data.get("vfmt") or "").strip() or None
        afmt = (data.get("afmt") or "").strip() or None
        merge = data.get("merge")
        merge = None if merge is None else bool(merge)
        label = (data.get("label") or "").strip()
        title = (data.get("title") or "").strip()
        tid = new_id()
        q = queue.Queue()
        tasks[tid] = {"q": q, "status": "running"}
        threading.Thread(target=download_worker, args=(tid, url, fmt, cookie, q),
                         kwargs={"vfmt": vfmt, "afmt": afmt, "merge": merge,
                                 "label": label, "title": title},
                         daemon=True).start()
        self._send(200, json.dumps({"task_id": tid}))

    def serve_sse(self):
        qs = urllib.parse.urlparse(self.path).query
        tid = urllib.parse.parse_qs(qs).get("task", [""])[0]
        q = tasks.get(tid, {}).get("q")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        if not q:
            self.wfile.write(b"event: error\ndata: no task\n\n")
            return
        try:
            while True:
                msg = q.get()
                self.wfile.write(("data: " + json.dumps(msg, ensure_ascii=False) + "\n\n").encode("utf-8"))
                self.wfile.flush()
                if msg.get("type") in ("done", "error"):
                    break
        except Exception:
            pass

    def serve_file(self):
        qs = urllib.parse.urlparse(self.path).query
        name = urllib.parse.unquote(urllib.parse.parse_qs(qs).get("name", [""])[0])
        path = os.path.normpath(os.path.join(DOWNLOADS, name))
        if not path.startswith(DOWNLOADS) or not os.path.isfile(path):
            self._send(404, "not found")
            return
        ctype = "video/mp4" if path.endswith(".mp4") else "application/octet-stream"
        try:
            with open(path, "rb") as f:
                data = f.read()
            self._send(200, data, ctype)
        except Exception as e:
            self._send(500, str(e))


def download_worker(tid, url, fmt, cookie, q, vfmt=None, afmt=None, merge=None, label=None, title=None):
    def hook(stage):
        def f(d):
            if d.get("status") == "downloading":
                q.put({"type": "progress", "stage": stage, "percent": d.get("_percent_str", "").strip(),
                       "filename": os.path.basename(d.get("filename", ""))})
            elif d.get("status") == "finished":
                q.put({"type": "progress", "stage": stage, "percent": "100%", "filename": os.path.basename(d.get("filename", ""))})
        return f

    try:
        # 前端没说明「要不要合并」时(如原始格式表直下), 才自己解析一次判断
        if merge is None or not title:
            info, err = ydl_extract(url, cookie)
            if err:
                q.put({"type": "error", "message": err})
                return
            if not title:
                title = info.get("title", "video")
            if merge is None:
                fobj = next((f for f in info.get("formats", []) if f.get("format_id") == fmt), None)
                vcodec = (fobj or {}).get("vcodec") or "none"
                acodec = (fobj or {}).get("acodec") or "none"
                merge = (acodec in (None, "none")) and vcodec not in (None, "none")
                if merge:
                    vfmt, afmt = fmt, None

        name = safe_name(title or label or "video")
        base = os.path.join(DOWNLOADS, name)
        vpath = base + ".video.mp4"
        apath = base + ".audio.m4a"
        final = base + ".mp4"

        if merge:
            ydl_download(url, vfmt or fmt, cookie, hook("下载视频"), vpath)
            ydl_download(url, afmt or "bestaudio[ext=m4a]/bestaudio", cookie, hook("下载音频"), apath)
            q.put({"type": "progress", "stage": "合并", "percent": "..."})
            if not is_harmony() and not DEPS.get("ready"):
                q.put({"type": "progress", "stage": "合并", "percent": "等待组件",
                       "filename": "首次要下载合并组件(约50MB), 稍等一下…"})
            ok, note = merge_av(vpath, apath, final)
            if ok:
                try:
                    os.remove(vpath); os.remove(apath)
                except Exception:
                    pass
                q.put({"type": "done", "file": os.path.basename(final), "note": note})
            else:
                q.put({"type": "done", "file": os.path.basename(vpath), "note": note})
        else:
            ydl_download(url, fmt, cookie, hook("下载"), base + ".%(ext)s")
            cand = [c for c in glob.glob(base + ".*")
                    if not c.endswith(".video.mp4") and not c.endswith(".audio.m4a")]
            newest = max(cand, key=os.path.getmtime) if cand else base
            q.put({"type": "done", "file": os.path.basename(newest)})
    except Exception as e:
        q.put({"type": "error", "message": str(e)[:400]})


def _prep_deps():
    """后台准备依赖(yt-dlp / ffmpeg), 不挡界面打开。"""
    try:
        mode, notes = ensure_deps()
        for n in notes:
            print("·", n)
        if not mode:
            print("⚠️ yt-dlp 不可用, 无法下载。请先安装 yt-dlp 或联网首次运行自动下载。")
        dep_status("运行环境已就绪", ready=True, notes=notes)
    except Exception as e:
        print("依赖准备失败:", e)
        dep_status("运行环境准备失败", ready=True, error=str(e)[:300])
    finally:
        DEPS_DONE.set()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    url = "http://127.0.0.1:%d" % port
    print("视频下载器已启动:", url)
    # 依赖放后台准备: 首次下 ffmpeg 时界面照样打开, 不会像卡死
    threading.Thread(target=_prep_deps, daemon=True).start()
    try:
        webbrowser.open(url)
        print("(已尝试自动打开浏览器; 若没弹窗, 手动访问上面的地址)")
    except Exception:
        print("(请手动在浏览器打开:", url, ")")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("已停止")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        try:
            logp = os.path.join(DOWNLOADS, "launch_error.log")
            with open(logp, "a", encoding="utf-8") as f:
                f.write("\n=== " + __import__("datetime").datetime.now().isoformat() + " ===\n")
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise
