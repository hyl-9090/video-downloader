# 视频下载器 · VM 侧验收报告

> 本报告由 VM 里的 AI 执行生成，按 `downloader/launcher/VERIFY.md` 的清单逐项实跑。
> **全程只验不改**：F 盘原有文件一个字节都没动（见文末《只验不改的凭据》）。
> 本报告文件本身是应主机侧要求新增的唯一一个文件。

---

## 0. 报告信息

| 项目 | 内容 |
|---|---|
| 验收时间 | 2026-09-19 12:55 – 14:40（VM 本地时间） |
| 验收对象（源码） | `F:\2026 英语歌曲大赛MV\downloader\launcher\`（= `\\HwFs\HMOS_F\2026 英语歌曲大赛MV\downloader\launcher\`） |
| 验收对象（交付产物） | `F:\2026 英语歌曲大赛MV\视频下载器.exe` |
| 执行环境 | OseasyVM（Windows 11 **ARM64**）；Python 3.13.15 **ARM64 原生版**；node v24.19.0；ffmpeg 9.0-full_build（WinGet 装的 Gyan.FFmpeg，在 PATH 里） |
| 依赖情况 | yt-dlp 单文件 2026.08.19（首次运行自动下载，17,840,399 字节）；为做第 4 项另装了 pyinstaller 6.22.3 与 pip 版 yt-dlp 2026.8.19（VERIFY.md 第 4 项允许的步骤） |
| 验收方式 | 源码整份拷到 `%TEMP%\wb_verify_launcher\` 上跑（哈希与原文件一致），F 盘目录只读不改 |

### 源码哈希（验收前后一致）

| 文件 | 大小 | 修改时间 | SHA256 |
|---|---|---|---|
| `index.html` | 29,365 | 2026/9/19 12:47:02 | `A3D2C14EB5218528DF665011AC9CBE43BCF6F53D4D24A229058AA5C7A7AED1F9` |
| `launch.py` | 33,566 | 2026/9/19 12:37:40 | `977A7EE68BE4DE12C6A1085AB71A5F439B46BE19BDA1469010C1D303D55DF258` |
| `build_win.py` | 1,458 | 2026/9/19 9:49:04 | `A141E853E273DED1F8C9E45F3EAD04122EF6FF2A62EA2A83905394E0943AB4D5` |
| `VERIFY.md` | 9,149 | 2026/9/19 12:52:02 | `41478B2A8047E6C48610F1E784C5D4C0F1D0B236ABEF278F432CDB6FC5AC1226` |

### ⚠️ 重要：验收期间交付 exe 被换过一次（14:27:27）

| 版本 | 大小 | 修改时间 | SHA256 | 内置界面 | v1.5 拦截 |
|---|---|---|---|---|---|
| **A 版**（12:55–13:20 期间我在验的） | 46,112,570 | 2026/9/19 12:37:53 | `139B6A123EB5CD9D1D211D01654557D25C550A2A3549E207FC4CB24DA97B8CDE` | **界面 v1.4** | ❌ 未生效 |
| **B 版**（现存，14:27:27 起） | 46,114,396 | 2026/9/19 14:27:27 | `E33A93D9478EC57D92C763D15A184F2420276EBE4C4545B11EB8B34AF18CBCD5` | **界面 v1.5** | ✅ 已生效 |

两版都是 **x64（PE Machine = 0x8664）**。本文档里凡是"交付 exe"的结论都注明了是 A 版还是 B 版。
**如果你在 14:27 之前看过我的中间结论，请以本报告为准：A 版确实缺 v1.5，B 版已经补上了。**

---

## 1. 结论速览

| # | 项目 | 结果 |
|---|---|---|
| 0 | 版本确认（界面 v1.5 + 6 个新函数） | ✅ 通过 |
| 1.1 | `py_compile launch.py` | ✅ 通过 |
| 1.2 | 界面 JS 语法（`node --check`） | ✅ 通过 |
| 1.3 | 界面体积（文档写"约 26 KB"） | ⚠️ 实测 29,365 字节，文档数字过期 |
| 2.1 | 启动不阻塞界面 | ✅ 通过（265 ms 返回 `ready:false`） |
| 2.2 | 依赖状态（yt-dlp + ffmpeg 两条 notes） | ✅ 通过 |
| 2.3 | `/health` | ✅ 通过 |
| 2.4 | 首页（输入框 / 三步说明 / 底部说明表） | ✅ 通过 |
| 2.附 | 首次自动下载 ffmpeg（"只下一次"） | ⚠️ 部分验证：首次下载未测完（见 §3.6），**"第二次不重下"验证通过** |
| 3.1 | 正常解析（只粘 BV 号） | ✅ 通过：5 档，每档带 filesize + merge |
| 3.2 | 分享文案自动识别 | ✅ 通过 |
| 3.3 | 不支持平台提前拦下（视频号 / 快手） | ✅ 通过：中文 + `friendly:true`，0.0 秒返回 |
| 3.4 | cookie 格式自动转换 + 对照实验 | ✅ 通过：不带 5 档 / 带伪造 3 档 |
| 3.5 | 真下载（源码 / 免安装单文件模式） | ❌ **不通过**：`--noplaylist` 参数失效，下载 100% 失败（P0 缺陷） |
| 3.5 | 真下载（交付 exe，走内置 yt-dlp 模块） | ✅ 通过：下载视频→下载音频→合并，产物可播、有声音 |
| 4 | 打包（PyInstaller） | ⚠️ 打包**成功**，但产物是 **ARM64**（不符合"班级 x64 电脑能跑"） |
| 4.附 | 交付 exe 与源码一致性 | B 版：界面逐字节一致 ✅；但同一条链接比源码**少 2 个清晰度档**（P1） |

---

## 2. 【版本确认】

`findstr` 那条命令在**本机查不到**（UTF-8 文件 + GBK 控制台），改用 PowerShell `Select-String`：

```
L94: <div class="tip">把视频链接粘进来 → 点「解析」→ 选清晰度 → 下载 <span style="opacity:.6">(界面 v1.5)</span></div>
```

`launch.py` 里 6 个新函数**全部存在**：

```
def find_ffmpeg():
def normalize_cookie(text, url=""):
def build_choices(info):
def normalize_url(raw):
def unsupported_hint(url):
def _prep_deps():
```

> 📌 给文档的建议：`findstr /C:"界面 v"` 在中文 Windows 控制台（GBK）下匹配不到 UTF-8 文件里的中文，
> 建议 VERIFY.md 改成 `powershell -c "Select-String -Path index.html -Pattern '界面 v'"`。

---

## 3. 逐项原始输出

### 3.1 静态检查

**1.1 Python 语法**
```
> python -m py_compile launch.py
(无输出)  [exit=0]
```

**1.2 界面 JS 语法**（抽出 `<script>` 存 `t.js` 再 `node --check`）
```
script 块数 = 1  总字符 = 9190
已写出: t.js 10612 bytes
> node --check t.js
(无输出)  [exit=0]   node = v24.19.0
```

**1.3 界面体积**
```
index.html  29,365 字节（28.68 KB）      ← VERIFY.md 写"约 26 KB"，实际偏大 ~3 KB
launch.py   33,566 字节（32.78 KB）
```
（不影响"判断是不是旧版"这个用途，但文档数字建议更新。）

### 3.2 服务与接口

**2.1 起服务后立刻访问 `/status`（关键：不能卡界面）**
```
命令: python launch.py 8932
HTTP 200   耗时 265.25 ms
{"ready": false, "phase": "正在准备运行环境…", "notes": [], "error": null, "harmony": false}
```
→ 界面**立刻可用**，依赖在后台准备 ✅

**2.2 依赖就绪后的 `/status`**
```
{"ready": true, "phase": "运行环境已就绪",
 "notes": ["yt-dlp: 同目录单文件", "ffmpeg: 系统 PATH"],
 "error": null, "harmony": false}
```
→ yt-dlp 与 ffmpeg 两条 notes 都在 ✅
（顺带实测：首次运行自动下载 yt-dlp 单文件成功，**17,840,399 字节**，`yt-dlp --version` = **2026.08.19** ✅）

**2.3 健康检查**
```
{"ok": true, "harmony": false}
```

**2.4 首页**
```
HTTP 200   Content-Type: text/html; charset=utf-8   字节 = 29,365
含: id="url"（输入框）  ✅
含: 「三步搞定」流程条   ✅
含: 底部《📖 使用说明》+「各平台怎么复制链接」表格  ✅
含: (界面 v1.5)  ✅
```

**2.附 ffmpeg「只下一次」（v1.2 修的那个 bug）**

⚠️ 本机 PATH 里**已经有 ffmpeg 9.0**（WinGet 的 Gyan.FFmpeg），所以正常运行时这条下载路径**根本不触发**（notes 直接是 `ffmpeg: 系统 PATH`，也没生成 `%LOCALAPPDATA%\VideoDownloader\bin`）。
我人为构造了"exe 环境 + PATH 里没有 ffmpeg"来逼它下载：

```
[run] 模拟 exe 环境: sys.frozen=True, PATH 置空
持久缓存目录 (_persist_dir) = C:\Users\OseasyVM\AppData\Local\VideoDownloader\bin
find_ffmpeg() 现在返回 = None
ensure_deps() … → 开始下载 https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
```
实测那个 zip **现在已经是 106.1 MB**（HTTP `Content-Length: 111253802`；备用源 BtbN 那个是 194,553,535 字节），
在这台 VM 上拉了**一个多小时仍未下完**（进程内存不再增长、连接基本不动）→ **"首次下载"整条没测完**（据实报）。
顺带发现：`download_ffmpeg()` 是 `data = r.read()` 把**整个 zip 读进内存**再解压，106 MB 的包峰值内存偏高。

**但"第二次不再重下"这个 v1.2 的核心修复点验证通过**——预先在缓存目录放一个文件后：
```
[run2] 持久缓存目录 = C:\Users\OseasyVM\AppData\Local\VideoDownloader\bin
       find_ffmpeg() = '...\\VideoDownloader\\bin\\ffmpeg.exe'
       ensure_deps() 用时 0.5 秒
         note: yt-dlp: 使用已装 Python 包
         note: ffmpeg: 本地缓存(以后直接用)      ← 完全没有发起下载
```
（测完我把这个假缓存删掉了，恢复"本机靠 PATH 里的 ffmpeg"的原状。）

### 3.3 功能验证

**3.1 正常解析（只粘 BV 号）**
```
POST /parse  {"url":"BV1GJ411x7h7"}
HTTP 200   耗时 17.6 秒
title   = 【官方 MV】Never Gonna Give You Up - Rick Astley
uploader= 哔哩哔哩官方   duration= 212.393
choices 档数 = 5
   - 1080P   fmt=30080+30280  merge=True   size=75219776   v=H.264 a=AAC ext=mp4
   - 720P    fmt=30064+30280  merge=True   size=51942273   v=H.264 a=AAC ext=mp4
   - 480P    fmt=30032+30280  merge=True   size=26298287   v=H.264 a=AAC ext=mp4
   - 360P    fmt=30016+30280  merge=True   size=14709249   v=H.264 a=AAC ext=mp4
   - 仅音频   fmt=30280        merge=False  size=5410339    a=AAC ext=m4a
原始格式表条数 = 15
```
✅ 档数、`filesize`、`merge` 字段都符合期望；**只粘 BV 号也能认**（完整链接结果相同）。

**3.2 分享文案自动识别**
```
POST /parse  {"url":"7.15 复制打开抖音，看看【某某】 https://www.bilibili.com/video/BV1GJ411x7h7 复制此链接"}
HTTP 200   耗时 11.0 秒   → 同样 5 档、title 一致
```
✅ 从一整段汉字里把链接抠出来了。

**3.3 不支持的平台应被提前拦下**
```
视频号  POST /parse {"url":"https://channels.weixin.qq.com/web/pages/feed?x=1"}   耗时 0.0 秒
{"error": "微信视频号（以及公众号文章里的视频）目前下不了。微信的视频是加密的、必须登录微信才能看，
           公开的下载工具都拿不到，这不是本工具的问题。替代办法：① 请视频作者把原视频文件发给你；
           ② 用手机自带的「屏幕录制」功能录下来。", "friendly": true}

快手    POST /parse {"url":"https://v.kuaishou.com/abcDEF"}                       耗时 0.0 秒
{"error": "快手目前下不了。下载引擎（yt-dlp）还没有支持快手。替代办法：① 在快手 App 里看作者是否
           允许「保存到相册」；② 用手机录屏。", "friendly": true}
```
✅ 中文 + 替代办法 + `friendly:true`，**没有**出现英文 `Unsupported URL`；而且是**没走网络**就拦下了（0.0 秒）。

**3.4 cookie 格式自动转换 + 对照实验**
```
POST /parse {"url":"https://www.bilibili.com/video/BV1GJ411x7h7",
             "cookie":"SESSDATA=fakevalue%2C123; bili_jct=fakejct"}
HTTP 200   耗时 10.1 秒   → 没有报"cookie 格式不对"（自动转 Netscape 生效 ✅）
```

| 条件 | 档数 | 档位 | 原始格式表 |
|---|---|---|---|
| **不带 cookie** | **5** | 1080P / 720P / 480P / 360P / 仅音频 | 15 条 |
| **带伪造 cookie** | **3** | 480P / 360P / 仅音频 | 9 条 |

✅ 带无效 cookie 的档数 **≤** 不带时，与 CHANGELOG 记录的现象一致（网站按"未登录"处理，不是 bug）。
两条都在同一台机器上背靠背跑的，可重复。

**3.5 真下载（最关键）**

❌ **A. 源码 / 免安装单文件模式：失败**
```
POST /download -> HTTP 200  {"task_id": "1"}
GET /progress?task=1 的 SSE:
  t=8.0s  {"type": "error", "message": "yt-dlp 下载失败(returncode=2)"}
阶段出现顺序 = []            ← 连"下载视频"都没开始
```
**根因（已复现到原文）**：
```
> yt-dlp.exe -f 30016 -o ... --noplaylist --newline --retries 10 --fragment-retries 10 --socket-timeout 30 <url>
Usage: yt-dlp.exe [OPTIONS] URL [URL...]
yt-dlp.exe: error: no such option: --noplaylist        [exit=2]
```
逐参数单独校验（2026.08.19）：
```
--noplaylist         -> Usage: yt-dlp.exe [OPTIONS] URL [URL...]     ← 已不存在
--no-playlist        -> OK(参数被接受)                                ← 现在叫这个
--newline            -> OK
--fragment-retries   -> OK
--retries            -> OK
--socket-timeout     -> OK
```
`yt-dlp --help` 里只有 `--no-playlist`（"Download only the video, if the URL refers to a video and a playlist"）。

**定位**：`launch.py:293` 的 `ydl_download_bin()`：
```python
args = [YTDL_BIN, "-f", fmt, "-o", outtmpl, "--noplaylist", "--newline", ...]
```
（API 模式的字典键叫 `noplaylist` 是对的，命令行参数不是。）

**影响面**：凡是"没装 `yt_dlp` 模块、靠首次自动下载 `yt-dlp.exe` 单文件"的环境（**正是 VERIFY.md §3.5 描述的这台 VM 的场景**），
**下载 100% 失败**，而且 `ydl_download_bin` 丢弃了 stderr，界面只会显示 `yt-dlp 下载失败(returncode=2)`，
老师/排查者看不到真正原因。

**修法**：`--noplaylist` → `--no-playlist`（一行）。

✅ **B. 交付 exe（内置 yt-dlp 模块，走 API 模式）：成功**（A 版、B 版都跑过，结果一致）
```
POST /download -> {"task_id":"1"}
  t=  1.3s  [下载视频] 0.0% … 100%   【官方 MV】….video.mp4
  t=  3.0s  [下载音频] 0.0% … 100%   【官方 MV】….audio.m4a
  t=  6.2s  [合并] ...
  t=  9.0s  {"type": "done", "file": "【官方 MV】Never Gonna Give You Up - Rick Astley.mp4",
             "note": "ffmpeg 合并"}
阶段出现顺序 = ["下载视频", "下载音频", "合并"]        ✅ 与 VERIFY.md 期望一致
```
- 落地文件：`C:\Users\OseasyVM\Downloads\视频下载器\【官方 MV】Never Gonna Give You Up - Rick Astley.mp4`
  ✅ 就是「下载」文件夹下的 **视频下载器** 子文件夹
- **文件大小 = 14,767,125 字节**（界面预估 14,709,249，基本一致）
- **能播放吗（有声音吗）= 能，有真实声音**：
```
ffprobe: h264 640x360 @25fps + aac 48000Hz stereo，duration 212.309167，size 14767125
文件头: 000000206674797069736f6d00000200  → ftyp ✅
全片解码 ffmpeg -v error -i <file> -f null -   → [exit=0]，无任何报错 ✅
音轨单独解码                                     → [exit=0]
音轨响度 mean_volume: -16.9 dB / max_volume: -0.8 dB  ← 不是静音轨 ✅
```

### 3.6 打包验证（第 4 项）

```
python -V   → Python 3.13.15   platform.machine() = ARM64
pip install pyinstaller → 拿到的是 pyinstaller-6.22.3-py3-none-win_arm64.whl
python build_win.py  →  [exit=0]
   79567 INFO: Analyzing hidden import 'yt_dlp.compat._legacy'
   89335 INFO: Bootloader …\PyInstaller\bootloader\Windows-64bit-arm\runw.exe
   89579 INFO: Building EXE from EXE-00.toc completed successfully.
   完成。exe 在 dist/视频下载器.exe
产物: dist\视频下载器.exe  16,828,219 字节
PE:  Machine = 0xAA64 (ARM64)     ← ❗
```

**结论**：VERIFY.md 里"ARM64 原生 Python 会因**缺 arm64 引导器**而打包失败——这是已知坑"这句**已经过期**：
PyInstaller 6.22.3 自带 `Windows-64bit-arm` 引导器，**打包会成功**，但产物是 **ARM64 exe（0xAA64）**，
按文档要求（`Machine = 0x8664`、班级 x64 电脑要能跑）**这不算合格**——比"直接报错"更容易被误当成能发。
这台 ARM64 机器上它确实能跑（`/health` ok、内置界面 v1.5）。

对照：F 盘那份交付 exe 是 **x64（0x8664）** ✅，这点是对的。

### 3.7 交付 exe 与源码的一致性（B 版，14:27:27 之后）

```
           交付 exe(B版)                        当前源码
首页字节   29,365                              29,365
首页哈希   A3D2C14EB5218528DF665011AC9CBE43BCF6F53D4D24A229058AA5C7A7AED1F9
源码哈希   A3D2C14EB5218528DF665011AC9CBE43BCF6F53D4D24A229058AA5C7A7AED1F9
```
✅ **B 版内置的 index.html 与源码逐字节一致**（同一 SHA256），界面 v1.5、v1.5 的平台表（"❌ 不行"列）都在。
✅ B 版对视频号的 `/parse` 也返回了 v1.5 的中文说明（`friendly: true`）。

⚠️ **但下面这条差异两版都在，仍然存在**——同一条链接、同一时刻、背靠背对照：
```
【交付 exe（F 盘 视频下载器.exe）】 /parse(BV1GJ411x7h7) → choices = 3 档 ['480P','360P','仅音频']   原始格式表 9 条
【当前源码（launch.py + index.html）】 /parse(BV1GJ411x7h7) → choices = 5 档 ['1080P','720P','480P','360P','仅音频']  原始格式表 15 条
```
→ **老师用 exe 会少掉 1080P / 720P 两档**，而源码侧同一秒拿到的是 5 档（可重复：源码侧 3 次都得 5 档，exe 侧 2 次都得 3 档）。
原始格式表条数（9 vs 15）说明差异出在**下载引擎给的格式清单**上，不是界面聚合逻辑。
**最可能的原因**：exe 里内置（打包时冻结）的 `yt_dlp` 版本比当前 2026.08.19 旧——旧版拿 B 站高码率的方式不同（exe 拿到的正好和"带无效 cookie"那次一样是未登录视角）。
exe 外部读不出它内置的 yt-dlp 版本号，所以这一条**原因未最终坐实**，但**现象是稳定的**。

> 建议：重打包时用当前版本的 `yt-dlp`（`pip install -U yt-dlp` 后再 `build_win.py`），并顺手核对一次"同一条链接的档数是否与源码一致"。

---

## 4. 缺陷与建议（按优先级）

| 级别 | 缺陷 | 证据 | 建议 |
|---|---|---|---|
| **P0** | 免安装/单文件模式下**下载必然失败**：`--noplaylist` 在 yt-dlp 2026.08.19 已不存在 | `yt-dlp.exe: error: no such option: --noplaylist`，`returncode=2`；`launch.py:293` | 改成 `--no-playlist`；顺便把 stderr 的末尾几行带进错误信息，别只丢 `returncode=2` |
| **P1** | 交付 exe 给的清晰度比源码少 2 档（1080P/720P） | 背靠背：exe 3 档 / 源码 5 档 | 重打包时更新内置 yt-dlp |
| **P1** | 打包产物必是 ARM64（本机 Python 是 ARM64 原生版），但文档要求 x64 | 产物 `Machine=0xAA64`；docs 要求 `0x8664` | 要么按 CHANGELOG 用 **x64 Python** 打包，要么把"必须 x64"写死成打包前检查（`build_win.py` 里加一句架构断言） |
| **P2** | 同一端口能被两个实例同时监听；两个实例的 task 表互相看不见 | `netstat`：PID 6644 与 5544 **都**在 `0.0.0.0:8000 LISTENING`；`GET /progress?task=999` 实测返回 `event: error / data: no task` | 加单实例判断（或端口占用时自动换端口）；`/progress` 查不到 task 时应回一条 `type:error` 的正常事件，别让界面干等 |
| **P2** | 界面在 SSE 收到错误时没有任何提示 | `index.html` 里 `es.onerror = () => {/* 服务器关闭流, 忽略 */}`（推断：任务串号时会静默卡住，未端到端复现） | 把 `onerror` 改成提示"任务丢失，请重新点下载" |
| **P3** | `python launch.py --console` 直接崩 | `ValueError: invalid literal for int() with base 10: '--console'`（exit 1）；`launch.py:818` 只把 `argv[1]` 当端口 | VERIFY.md 里那句改成"日志方式"说明，或真的支持 `--console` |
| **P3** | 文档数字过期：界面体积、ffmpeg 包大小、交付 exe 大小、`findstr` 命令 | 见 §1.3 / §2.附 / §0 | 见下 |

**文档需要更新的地方（都不是代码问题）**
1. `VERIFY.md` 1.3「约 26 KB」→ 实际 29,365 字节。
2. `VERIFY.md` §2「约 50MB 的 ffmpeg」→ 那个包现在 **106.1 MB**。
3. `CHANGELOG.md` / `VERIFY.md`「已交付产物：`视频下载器.exe`（17,589,901 字节）」→ F 盘实际是 **46,114,396 字节**（因为这一版把 ffmpeg 与 yt-dlp 都打进去了；`/status` 自证：`yt-dlp: 使用已装 Python 包`、`ffmpeg: 内置/同目录`）。**数字对不上不是 bug，但会让验收者误判"拿到了旧版"。**
4. `VERIFY.md` §0 的 `findstr /C:"界面 v"` 在中文控制台下查不到，建议换 `Select-String`。
5. `VERIFY.md` §2 的 `--console`（见 P3）。
6. `VERIFY.md` §4 的"ARM64 打包必失败"→ 现在会成功但产出 ARM64（见 P1）。
7. `VERIFY.md` §3.5 期望"存到「下载」文件夹下的 视频下载器 子文件夹"——这只在 **exe 模式**成立；源码模式落在 `launcher\downloads\`。

**其它观察（不算缺陷，但建议处理）**
- 合并中断会留下中间文件：`C:\Users\OseasyVM\Downloads\视频下载器\` 里就有一次中断留下的 `TESTMV.audio.m4a.part`（0 字节）+ `TESTMV.video.mp4`。规范上可以接受，但会白占磁盘，建议失败时清掉 `.part`。
- 服务端日志在 stdout 被管道接管时是**块缓冲**：我整场都没看到 `launch.py` 的任何 print（包括"视频下载器已启动"）。非交互运行排查时会误以为服务没起来，建议加 `flush=True`。
- F 盘还留着旧版残留：`downloader\server.py` + `downloader\index.html`（7,218 字节，v0.x 那一版）。老师/验收者很容易拷错，建议清理或改名 `_legacy`。
- 验收期间有**另一套脚本**也在用 8000 端口（`C:\acc\acc3.ps1`，产物 `TESTMV.*`，14:30 还在跑）。我的 3.5 是跑在自己起的实例上（当时 8000 由我起的 PID 5544 持有，netstat 可查），不影响结论，但两边同时验收会有端口/文件互相干扰。

---

## 5. 未能验证的项目（及原因）

| 项目 | 原因 |
|---|---|
| 首次自动下载 ffmpeg 的完整过程 | 本机 PATH 已有 ffmpeg 所以不触发；人为触发后，106 MB 的包在这台 VM 上 > 1 小时仍未下完（网络太慢/连接停滞） |
| exe 双击后"浏览器自动打开"的肉眼确认 | 无 GUI 自动化能力；改为验证"服务起来 + 首页内容正确 + 代码里确实调用了 `webbrowser.open`"。另外 exe 启动时确实弹了浏览器进程 |
| 界面点击操作（手工路径） | 同上；我调的是界面按钮背后同一套接口（`POST /download` + SSE `/progress`），并且核对了 `index.html` 里确实是这两个接口 |
| YouTube 及各平台真实下载 | 与作者自述边界一致：只对 B 站做了真实下载；视频号/快手是"确认不支持"，属于预期结果 |
| exe 内置 yt-dlp 的具体版本号 | 打进去了、外部读不出来；只能证明"它给的格式清单比当前版本少 6 条" |
| 多 P / 合集 / 播放列表 | 清单里声明为已知边界，未测 |

---

## 6. 只验不改的凭据

- **F 盘原有文件零改动**：验收前后 `index.html`（`A3D2C14E…`）、`launch.py`（`977A7EE6…`）、`build_win.py`（`A141E853…`）、`VERIFY.md`（`41478B2A…`）哈希不变；`downloader\launcher\` 目录清单、大小、修改时间全部不变，**没有新增任何文件**。
- 所有测试都在 `%TEMP%\wb_verify_launcher\`（源码副本，哈希与原文件一致）里跑；我编译出的 `__pycache__`、下载下来的 `yt-dlp.exe`、打包出的 `build\`+`dist\` 全在 VM 的临时目录里，没落到 F 盘。
- 为做第 4 项装的 `pyinstaller` / `pip 版 yt-dlp` 在 VM 的 Python 环境里（VERIFY.md 第 4 项允许）。
- 测试造出来的假 ffmpeg 缓存（`%LOCALAPPDATA%\VideoDownloader`）**已删除**，恢复"靠 PATH 里的 ffmpeg"原状。
- 我起过的服务（端口 8000 / 8010 / 8011 / 8020 / 8030 / 8040 / 8932）**全部已停**，无遗留进程（`netstat` 已复核）。
- **本报告是唯一新增的文件**（应主机侧要求写的，覆盖 VERIFY.md 里"不要新建文件"那一条）。
- 原始转录留在 VM 里备查：
  - `%TEMP%\wb_verify\out_35.txt`（3.5 源码模式的失败现场）
  - `%TEMP%\wb_verify\out_exe35.txt`（3.5 exe 模式的成功现场，B 版）
  - `%TEMP%\wb_verify\out_exe35_旧exe_v1.4.txt`（A 版当时的现场）
  - `%TEMP%\wb_verify\out_compare.txt`（exe 与源码的背靠背对照）
  - `%TEMP%\wb_verify\exe_index_旧exe_v1.4.html`（A 版首页原文，"界面 v1.4" 就在这里）

---

## 7. 给主机侧的一页行动清单

1. **`launch.py:293`：`--noplaylist` → `--no-playlist`**（P0，一行；改完请用"没装 yt_dlp 的环境"复测一次真下载）。
2. 重新打包 x64 exe 时：**用当前版本 yt-dlp**、**用 x64 Python**（打完用 PE 头确认 `0x8664`），并复核"同一条链接的清晰度档数与源码一致"。
3. 需要的话加两条小加固：单实例/端口占用处理；SSE 查不到 task 时返回正常 error 事件。
4. VERIFY.md / CHANGELOG.md 里 7 处过期数字与描述（见 §4）更新一下，下一轮验收就不会再被"46MB vs 17.6MB""ARM64 打包必失败"这类过期信息带偏。
5. 清掉 `downloader\server.py` + `downloader\index.html` 旧版残留。

---

*报告完 · 由 VM 侧 AI 于 2026-09-19 生成 · 只验不改*
