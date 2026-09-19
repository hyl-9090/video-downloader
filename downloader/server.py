#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地视频下载器 (基于 yt-dlp) — 鸿蒙网页版
粘贴链接 -> 解析格式 -> 选清晰度 -> 下载 -> 进度; 分离流自动合并(内置 fMP4 合并器, 绕过 ffmpeg)。
"""
import os, sys, json, re, threading, queue, subprocess, glob, tempfile, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS = os.path.join(ROOT, "downloads")
MUX = "/storage/Users/currentUser/.local/opt/mux_fmp4.py"
os.makedirs(DOWNLOADS, exist_ok=True)

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
        url = (data.get("url") or "").strip()
        cookie = (data.get("cookie") or "").strip()
        if not url:
            self._send(400, json.dumps({"error": "url 为空"}))
            return
        info = extract_info(url, cookie)
        self._send(200, json.dumps(info, ensure_ascii=False))

    def handle_download(self, data):
        url = (data.get("url") or "").strip()
        fmt = (data.get("format_id") or "").strip()
        cookie = (data.get("cookie") or "").strip()
        if not url or not fmt:
            self._send(400, json.dumps({"error": "缺少 url 或 format_id"}))
            return
        tid = new_id()
        q = queue.Queue()
        tasks[tid] = {"q": q, "status": "running"}
        threading.Thread(target=download_worker, args=(tid, url, fmt, cookie, q), daemon=True).start()
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
        # 防目录穿越
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


def write_cookie(text):
    fd, p = tempfile.mkstemp(suffix=".txt", dir=DOWNLOADS)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return p


def extract_info(url, cookie):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "simulate": True, "skip_download": True}
    cf = None
    if cookie:
        cf = write_cookie(cookie)
        opts["cookiefile"] = cf
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        fmts = []
        for f in info.get("formats", []):
            fmts.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "resolution": (f.get("resolution") or (str(f.get("height")) + "p" if f.get("height") else "")),
                "vcodec": f.get("vcodec") or "none",
                "acodec": f.get("acodec") or "none",
                "tbr": f.get("tbr"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "protocol": f.get("protocol"),
            })
        return {"title": info.get("title", ""), "webpage_url": info.get("webpage_url", url), "formats": fmts}
    except Exception as e:
        return {"error": str(e)[:400]}
    finally:
        if cf and os.path.exists(cf):
            try:
                os.remove(cf)
            except Exception:
                pass


def download_worker(tid, url, fmt, cookie, q):
    import yt_dlp
    cf = write_cookie(cookie) if cookie else None

    def hook(stage):
        def f(d):
            if d.get("status") == "downloading":
                q.put({"type": "progress", "stage": stage, "percent": d.get("_percent_str", "").strip(),
                       "filename": os.path.basename(d.get("filename", ""))})
            elif d.get("status") == "finished":
                q.put({"type": "progress", "stage": stage, "percent": "100%",
                       "filename": os.path.basename(d.get("filename", ""))})
        return f

    try:
        base_opts = {"quiet": True, "simulate": True, "noplaylist": True}
        if cf:
            base_opts["cookiefile"] = cf
        with yt_dlp.YoutubeDL(base_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        title = safe_name(info.get("title", "video"))
        fobj = next((f for f in info.get("formats", []) if f.get("format_id") == fmt), None)
        vcodec = (fobj or {}).get("vcodec") or "none"
        acodec = (fobj or {}).get("acodec") or "none"
        need_merge = (acodec in (None, "none")) and vcodec not in (None, "none")

        base = os.path.join(DOWNLOADS, title)
        vpath = base + ".video.mp4"
        apath = base + ".audio.m4a"
        final = base + ".mp4"

        if not need_merge:
            opts = {"format": fmt, "outtmpl": base + ".%(ext)s", "progress_hooks": [hook("下载")],
                    "quiet": True, "noplaylist": True, "noprogress": True}
            if cf:
                opts["cookiefile"] = cf
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            cand = [c for c in glob.glob(base + ".*") if not c.endswith(".video.mp4") and not c.endswith(".audio.m4a")]
            done = cand[0] if cand else base
            q.put({"type": "done", "file": os.path.basename(done)})
        else:
            vopts = {"format": fmt, "outtmpl": vpath, "progress_hooks": [hook("下载视频")],
                     "quiet": True, "noplaylist": True, "noprogress": True}
            if cf:
                vopts["cookiefile"] = cf
            with yt_dlp.YoutubeDL(vopts) as ydl:
                ydl.download([url])
            aopts = {"format": "bestaudio[ext=m4a]/bestaudio", "outtmpl": apath,
                     "progress_hooks": [hook("下载音频")], "quiet": True, "noplaylist": True, "noprogress": True}
            if cf:
                aopts["cookiefile"] = cf
            with yt_dlp.YoutubeDL(aopts) as ydl:
                ydl.download([url])
            q.put({"type": "progress", "stage": "合并", "percent": "..."})
            if os.path.exists(vpath) and os.path.exists(apath):
                r = subprocess.run([sys.executable, MUX, vpath, apath, final],
                                   capture_output=True, text=True)
                if r.returncode == 0 and os.path.exists(final):
                    try:
                        os.remove(vpath)
                        os.remove(apath)
                    except Exception:
                        pass
                    q.put({"type": "done", "file": os.path.basename(final), "note": "已用内置合并器(绕过 ffmpeg)"})
                else:
                    q.put({"type": "done", "file": os.path.basename(vpath),
                           "note": "合并失败(本机 ffmpeg 不可用), 视频/音频已分别保存"})
            else:
                q.put({"type": "done", "file": os.path.basename(vpath), "note": "音频缺失, 仅视频"})
    except Exception as e:
        q.put({"type": "error", "message": str(e)[:400]})
    finally:
        if cf and os.path.exists(cf):
            try:
                os.remove(cf)
            except Exception:
                pass


def main():
    port = 8000
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("serving on http://127.0.0.1:%d" % port)
    srv.serve_forever()


if __name__ == "__main__":
    main()
