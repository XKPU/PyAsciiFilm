# 共享基础设施
import json
import logging
import math
import os
import re
import string
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path


_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _cpu_count():
    try:
        n = os.cpu_count() or 1
    except Exception:
        n = 1
    return max(1, n)


_FFMPEG_MAX_USAGE = 35


def _set_ffmpeg_max_usage(pct):
    global _FFMPEG_MAX_USAGE
    try:
        p = int(pct)
    except Exception:
        p = 35
    _FFMPEG_MAX_USAGE = max(1, min(100, p))


def _ffmpeg_usage_threads(usage=None):
    pct = usage if usage is not None else _FFMPEG_MAX_USAGE
    try:
        pct = max(1, min(100, int(pct)))
    except Exception:
        pct = _FFMPEG_MAX_USAGE
    return max(1, int(math.ceil(_cpu_count() * pct / 100.0)))


def _encode_threads(usage=None):
    return max(1, int(round(_ffmpeg_usage_threads(usage) * 0.75)))


def _decode_threads(usage=None):
    return max(1, _ffmpeg_usage_threads(usage) - _encode_threads(usage) + 1)


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


# ---- 文件日志 ----
_LOG_PATH = os.path.join(_app_dir(), "pyasciifilm.log")
_LOG_LOCK = threading.Lock()
_CONFIG_LOCK = threading.Lock()
_LOGGER = None


def _log_enabled() -> bool:
    # 日志开关，读取失败时按关闭处理
    try:
        return bool(_read_config().get("EnableFileLog", False))
    except Exception:
        return False


def _init_logger():
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    logger = logging.getLogger("pyasciifilm")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        # delay=True：延迟到真正写第一条日志时才创建文件，关日志时不留空文件
        fh = logging.FileHandler(_LOG_PATH, encoding="utf-8", delay=True)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            "%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(fh)
    except Exception:
        pass
    _LOGGER = logger
    return logger


def _clear_log():
    # 启动时清空日志文件；关闭日志功能时不创建文件
    if not _log_enabled():
        return
    try:
        with open(_LOG_PATH, "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass


def _log(msg, level=logging.INFO):
    # 文件日志（受 EnableFileLog 配置控制）
    if not isinstance(msg, str):
        msg = str(msg)
    if not _log_enabled():
        return
    try:
        with _LOG_LOCK:
            _init_logger().log(level, msg)
    except Exception:
        pass


def _log_error(msg):
    _log(msg, level=logging.ERROR)


def _default_log(msg):
    try:
        print(msg, file=sys.stderr)
    except Exception:
        pass


def clean_fps(fps):
    # 仅在极接近整数时取整；29.97/23.976 保留原值，避免长时间漂移
    if fps is None:
        return 30.0
    try:
        v = float(fps)
    except (TypeError, ValueError):
        return 30.0
    if v != v or v <= 0 or v == float("inf"):
        return 30.0
    r = round(v)
    if abs(v - r) < 1e-3:
        return float(r) if r > 0 else 30.0
    return v


# ---- ffmpeg ----
_FFMPEG = None


def _ffmpeg_exe():
    # 解析随包 ffmpeg 的绝对路径
    global _FFMPEG
    if _FFMPEG is not None:
        return _FFMPEG

    env = os.environ.get("IMAGEIO_FFMPEG_EXE")
    if env and os.path.isfile(env):
        _FFMPEG = env
        return _FFMPEG

    try:
        import imageio_ffmpeg
        # 临时摘掉失效的环境变量，让 get_ffmpeg_exe 走包内解析
        if env:
            os.environ.pop("IMAGEIO_FFMPEG_EXE", None)
        try:
            cand = imageio_ffmpeg.get_ffmpeg_exe()
        finally:
            if env:
                os.environ["IMAGEIO_FFMPEG_EXE"] = env
        if cand and os.path.isfile(cand):
            _FFMPEG = cand
        else:
            _FFMPEG = False
    except Exception:
        _FFMPEG = False
    return _FFMPEG or None


def _init_ffmpeg():
    # 解析并校验随包 ffmpeg，作为全程序唯一的 ffmpeg 来源。不再依赖 imageio：解码与元数据都直接用随包二进制，因此这里只需确保它真实存在且可用
    ff = _ffmpeg_exe()
    if not ff:
        raise RuntimeError("未找到随包 ffmpeg，程序无法运行。请确保 imageio-ffmpeg 已正确安装。")
    return ff


# ---- 视频元数据（随包 ffmpeg） ----


def _count_frames(path, limit=None, timeout=20.0):
    # 遍历解码统计帧数（容器不记录时长时使用，代价较高）；超时返回已计数
    ff = _ffmpeg_exe()
    if not ff:
        return 0
    proc = None
    try:
        proc = subprocess.Popen(
            [ff, "-nostdin", "-hide_banner", "-loglevel", "error",
             "-i", path, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
        )
        meta = _ffmpeg_probe(path)
        w = (meta or {}).get("width") or 0
        h = (meta or {}).get("height") or 0
        if w <= 0 or h <= 0:
            return 0
        fbytes = w * h
        n = 0
        deadline = time.monotonic() + timeout if timeout else None
        while True:
            if deadline is not None and time.monotonic() > deadline:
                break
            raw = proc.stdout.read(fbytes)
            if len(raw) < fbytes:
                break
            n += 1
            if limit is not None and n >= limit:
                break
        return n
    except Exception:
        return 0
    finally:
        if proc is not None:
            try:
                proc.stdout.close()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass


# 用随包 ffmpeg 解析 -i 输出（imageio 拒绝的容器走这条）
_RE_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_RE_FPS = re.compile(r"(\d+(?:\.\d+)?)\s*fps")
_RE_SIZE = re.compile(r"Stream.*?Video.*?(\d{2,})x(\d{2,})")
_RE_NBFRAMES = re.compile(r"nb_frames\s*=\s*(\d+)")
# 视频流识别：只认 "Stream #0:1: Video: " 这种真正的视频流行
_RE_STREAM_LINE = re.compile(r"Stream #\d+:\d+.*?: Video: ")
_RE_RES = re.compile(r"(\d{2,})x(\d{2,})")
_RE_ATTACHED = re.compile(r"attached pic", re.IGNORECASE)
_RE_ROTATE = re.compile(r"rotation of (-?\d+(?:\.\d+)?) degrees")


def _pick_video_size(txt):
    # 从 `ffmpeg -i` 输出里挑出正片的分辨率，返回 (w, h) 或 None
    candidates = []
    for line in (txt or "").splitlines():
        if not _RE_STREAM_LINE.search(line):
            continue
        mr = _RE_RES.search(line)
        if not mr:
            continue
        w, h = int(mr.group(1)), int(mr.group(2))
        if w <= 0 or h <= 0:
            continue
        candidates.append((w, h, "(default)" in line, bool(_RE_ATTACHED.search(line))))
    if not candidates:
        return None
    for w, h, is_default, _att in candidates:
        if is_default and not _att:
            return w, h
    for w, h, _d, att in candidates:
        if not att:
            return w, h
    return candidates[0][0], candidates[0][1]


def _ffmpeg_probe(path):
    # 用随包 ffmpeg 读取元数据，失败返回 None
    ff = _ffmpeg_exe()
    if not ff:
        return None
    try:
        res = subprocess.run(
            [ff, "-hide_banner", "-i", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, creationflags=_CREATE_NO_WINDOW,
        )
        txt = res.stderr or ""
    except Exception:
        return None

    size = _pick_video_size(txt)
    if size is None:
        return None
    w, h = size
    # 旋转 90/270 度的视频，实际显示宽高要对调
    mr = _RE_ROTATE.search(txt)
    if mr:
        try:
            if abs(float(mr.group(1))) % 180 == 90:
                w, h = h, w
        except ValueError:
            pass

    fps = 0.0
    mf = _RE_FPS.search(txt)
    if mf:
        try:
            fps = clean_fps(float(mf.group(1)))
        except ValueError:
            fps = 0.0

    duration = 0.0
    md = _RE_DURATION.search(txt)
    if md:
        try:
            duration = (int(md.group(1)) * 3600 + int(md.group(2)) * 60
                        + float(md.group(3)))
        except ValueError:
            duration = 0.0

    n = 0
    mn = _RE_NBFRAMES.search(txt)
    if mn:
        n = int(mn.group(1))
    if not n and duration > 0 and fps > 0:
        n = int(round(duration * fps))

    return {
        "width": w,
        "height": h,
        "fps": fps,
        "frame_count": n,
        "duration": duration,
    }


def _probe_video_meta(path, count_frames=False):
    # 统一的视频元数据入口（随包 ffmpeg）
    info = _ffmpeg_probe(path)
    if info is None:
        return None
    if count_frames and info["frame_count"] <= 0:
        n = _count_frames(path)
        if n > 0:
            info["frame_count"] = n
    return info


def _forward_stderr(proc, log):
    if getattr(proc, "stderr", None) is None:
        return

    def _pump():
        try:
            for raw in iter(proc.stderr.readline, b""):
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line:
                    log(line)
        except Exception:
            pass
        finally:
            try:
                proc.stderr.close()
            except Exception:
                pass

    threading.Thread(target=_pump, daemon=True).start()


# 硬件加速
_HW_ACCEL = None
_HW_DECODE_ONLY = None

# 启动检测调度
_DETECT_LOCK = threading.Lock()
_DETECT = {
    "decode": {"state": "idle", "result": None, "event": threading.Event()},
    "encode": {"state": "idle", "result": None, "event": threading.Event()},
}
_DETECT_STARTED = False


def _detect_status(kind):
    # -> "idle" | "running" | "done"；UI 据此显示"检测中"
    with _DETECT_LOCK:
        return _DETECT[kind]["state"]


def _detect_ready(kind):
    with _DETECT_LOCK:
        d = _DETECT[kind]
        return d["state"] == "done", d["result"]


def _detect_result(kind):
    # 已完成则返回结果，否则返回 None（不阻塞）
    ok, res = _detect_ready(kind)
    return res if ok else None


def wait_detect(kind, timeout=None):
    # 等到该组检测完成；返回结果（超时/未启动则返回 None）
    with _DETECT_LOCK:
        d = _DETECT[kind]
        ev = d["event"]
        if d["state"] == "done":
            return d["result"]
        if d["state"] == "idle":
            return None
    ev.wait(timeout)
    with _DETECT_LOCK:
        d = _DETECT[kind]
        return d["result"] if d["state"] == "done" else None


def _run_detect(kind, fn):
    try:
        res = fn()
    except Exception:
        res = None
    with _DETECT_LOCK:
        d = _DETECT[kind]
        d["result"] = res
        d["state"] = "done"
        d["event"].set()


def start_detect():
    # 启动解码/编码两组检测
    global _DETECT_STARTED
    with _DETECT_LOCK:
        if _DETECT_STARTED:
            return
        _DETECT_STARTED = True
        for k in ("decode", "encode"):
            _DETECT[k]["state"] = "running"

    def decode_job():
        # 解码组：探测硬件解码后端并逐个验证（不碰编码器）
        try:
            return _list_verified_decode_backends()
        except Exception:
            return [("软件解码", None)]

    def encode_job():
        # 编码组：只验证可用的 H.264 编码器
        try:
            hw = _probe_hw_accel()
            return list(hw.get("encode_h264", []))
        except Exception:
            return []

    threading.Thread(target=_run_detect, args=("decode", decode_job),
                     name="detect-decode", daemon=True).start()
    threading.Thread(target=_run_detect, args=("encode", encode_job),
                     name="detect-encode", daemon=True).start()


def _validate_encoder(ff, encoder, extra_args, w=160, h=120):
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "yuv420p",
           "-s", f"{w}x{h}", "-r", "24", "-i", "-",
           "-frames:v", "1", "-c:v", encoder] + list(extra_args) + ["-f", "null", "-"]
    try:
        sz = w * h * 3 // 2
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             creationflags=_CREATE_NO_WINDOW)
        _, stderr = p.communicate(input=b"\x80" * sz, timeout=10)
        return p.returncode == 0
    except Exception:
        return False


def _probe_hw_decode():
    # 只探测可用的硬件解码后端
    global _HW_DECODE_ONLY
    if _HW_DECODE_ONLY is not None:
        return _HW_DECODE_ONLY
    ff = _ffmpeg_exe()
    if not ff:
        _HW_DECODE_ONLY = []
        return _HW_DECODE_ONLY

    hwaccels = set()
    try:
        r = subprocess.run([ff, "-hide_banner", "-hwaccels"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, timeout=5,
                           creationflags=_CREATE_NO_WINDOW)
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line and not line.startswith("-") and not line.startswith("Hardware"):
                hwaccels.add(line)
    except Exception:
        pass

    decode = []
    for name in ("cuda", "d3d12va", "d3d11va", "dxva2", "qsv", "vaapi",
                 "videotoolbox"):
        if name in hwaccels:
            decode.append(("-hwaccel", name))
    _HW_DECODE_ONLY = decode
    return _HW_DECODE_ONLY


def _probe_hw_accel():
    global _HW_ACCEL
    if _HW_ACCEL is not None:
        return _HW_ACCEL
    ff = _ffmpeg_exe()
    if not ff:
        _HW_ACCEL = {"decode": [], "encode_h264": []}
        return _HW_ACCEL

    hwaccels = set()
    listed_encoders = set()
    try:
        r = subprocess.run([ff, "-hide_banner", "-hwaccels"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, timeout=5,
                           creationflags=_CREATE_NO_WINDOW)
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line and not line.startswith("-") and not line.startswith("Hardware"):
                hwaccels.add(line)
    except Exception:
        pass
    try:
        r = subprocess.run([ff, "-hide_banner", "-encoders"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, timeout=5,
                            creationflags=_CREATE_NO_WINDOW)
        for line in (r.stdout or "").splitlines():
            for name in ("h264_nvenc", "h264_qsv", "h264_amf",
                         "h264_vaapi", "h264_videotoolbox"):
                if name in line:
                    listed_encoders.add(name)
    except Exception:
        pass

    decode = []
    if "cuda" in hwaccels:
        decode.append(("-hwaccel", "cuda"))
    if "d3d12va" in hwaccels:
        decode.append(("-hwaccel", "d3d12va"))
    if "d3d11va" in hwaccels:
        decode.append(("-hwaccel", "d3d11va"))
    if "dxva2" in hwaccels:
        decode.append(("-hwaccel", "dxva2"))
    if "qsv" in hwaccels:
        decode.append(("-hwaccel", "qsv"))
    if "vaapi" in hwaccels:
        decode.append(("-hwaccel", "vaapi"))
    if "videotoolbox" in hwaccels:
        decode.append(("-hwaccel", "videotoolbox"))

    encode_h264 = []
    _H264_CANDIDATES = [
        ("h264_nvenc", ["-preset", "p4", "-rc", "vbr", "-cq", "23",
                         "-pix_fmt", "yuv420p"]),
        ("h264_qsv",   ["-pix_fmt", "yuv420p"]),
        ("h264_amf",   ["-pix_fmt", "yuv420p"]),
        ("h264_vaapi", ["-vf", "format=nv12,hwupload", "-pix_fmt", "vaapi"]),
        ("h264_videotoolbox", ["-allow_sw", "1", "-pix_fmt", "yuv420p"]),
    ]
    # 编码器验证：每个候选都要跑"编码+回读"两次子进程（实测约 240ms），串行做 5 个要 1 秒以上。各候选彼此独立，并行验证
    present = [(n, p) for n, p in _H264_CANDIDATES if n in listed_encoders]
    if present:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(4, len(present))) as ex:
            results = list(ex.map(
                lambda np: (np, _validate_encoder(ff, np[0], np[1])),
                present,
            ))
        encode_h264 = [np for np, ok in results if ok]
    else:
        encode_h264 = []

    _HW_ACCEL = {"decode": decode, "encode_h264": encode_h264}
    return _HW_ACCEL


# ---- 解码后端验证 ----
def _make_probe_clip(ff):
    # 生成一次探测用的小视频，供所有后端复用。原先每个后端各建一次临时文件（还要跑一次编码），5 个后端就是 5 次多余编码。现在只生成一次
    import tempfile
    try:
        fd, tp = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        r = subprocess.run(
            [ff, "-y", "-hide_banner", "-f", "lavfi",
             "-i", "testsrc=duration=1:size=64x64:rate=1",
             "-pix_fmt", "yuv420p", tp],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        if r.returncode != 0 or not os.path.isfile(tp):
            try:
                os.remove(tp)
            except OSError:
                pass
            return None
        return tp
    except Exception:
        return None


def _verify_decode_backend_with(ff, decode_args, clip):
    # 用已有探测片段验证某个解码后端
    if not decode_args:
        return True
    if not ff or not clip:
        return False
    try:
        cmd = [ff, "-nostdin", "-hide_banner", "-loglevel", "error"] + \
            list(decode_args) + \
            ["-i", clip, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        p = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        return p.returncode == 0 and len(p.stdout) >= 64 * 64 * 3
    except Exception:
        return False


def _verify_decode_backend(decode_args):
    # 单个后端自检（自建探测片段，保留给外部单独调用）
    if not decode_args:
        return True
    ff = _ffmpeg_exe()
    if not ff:
        return False
    clip = _make_probe_clip(ff)
    if not clip:
        return False
    try:
        return _verify_decode_backend_with(ff, decode_args, clip)
    finally:
        try:
            os.remove(clip)
        except OSError:
            pass


def _list_verified_decode_backends():
    # 只取解码部分；不可调 _probe_hw_accel()，否则会白验证全部编码器
    candidates = _probe_hw_decode()
    result = []
    _LABELS = {
        "cuda": "CUDA (NVIDIA)",
        "d3d12va": "D3D12VA",
        "d3d11va": "D3D11VA",
        "dxva2": "DXVA2",
        "qsv": "QSV (Intel)",
        "vaapi": "VAAPI (Linux)",
        "videotoolbox": "VideoToolbox (macOS)",
    }
    _PRIORITY = {"cuda": 0, "dxva2": 10, "d3d11va": 11, "d3d12va": 12, "qsv": 13,
                 "vaapi": 14, "videotoolbox": 15}

    ff = _ffmpeg_exe()
    clip = _make_probe_clip(ff) if (ff and candidates) else None
    try:
        if clip:
            # 各后端互不依赖，并行验证（每个都是一次独立短解码）
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(4, len(candidates))) as ex:
                oks = list(ex.map(
                    lambda a: _verify_decode_backend_with(ff, a, clip),
                    candidates,
                ))
        else:
            oks = [False] * len(candidates)
    finally:
        if clip:
            try:
                os.remove(clip)
            except OSError:
                pass

    for args, ok in zip(candidates, oks):
        if not ok:
            continue
        name = args[-1]
        label = _LABELS.get(name, name.upper())
        result.append((label, args, _PRIORITY.get(name, 99)))

    result.sort(key=lambda x: x[2])
    hw_items = [(label, args) for label, args, _p in result]
    cuda = [item for item in hw_items if "CUDA" in item[0].upper()]
    others = [item for item in hw_items if "CUDA" not in item[0].upper()]
    return cuda + others + [("软件解码", None)]


# ---- 编码模式 ---- 各硬件编码器在界面上的显示名
_ENCODER_LABELS = {
    "h264_nvenc": "NVENC (NVIDIA)",
    "h264_qsv": "QSV (Intel)",
    "h264_amf": "AMF (AMD)",
    "h264_vaapi": "VAAPI",
    "h264_videotoolbox": "VideoToolbox (Apple)",
    "libx264": "软件编码 (libx264)",
}


def _list_encoder_options():
    # 列出编码模式选项：[("自动", None), (标签, 编码器名), ...]。第一项固定为「自动」——保持现有的自动挑选行为（优先硬件、失败回退软件）
    options = [("自动（优先硬件）", None)]
    try:
        hw = _probe_hw_accel()
        for codec, _params in hw.get("encode_h264", []):
            label = _ENCODER_LABELS.get(codec, codec)
            options.append((label, codec))
    except Exception:
        pass
    options.append((_ENCODER_LABELS["libx264"], "libx264"))
    return options


def _encoder_label(codec):
    # 编码器名 -> 显示名（用于日志与提示）
    return _ENCODER_LABELS.get(codec, codec or "自动")


# ---- 视频文件类型 ----
VIDEO_EXTS = frozenset({
    ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob",
})


def is_video_file(name):
    # 检查文件名是否为支持的视频格式
    _, ext = os.path.splitext(name)
    return ext.lower() in VIDEO_EXTS


# ---- 文件系统工具 ----
def user_dirs():
    # 返回用户目录快捷访问列表：[(显示名, 路径), ...]（三平台）
    home = Path.home()
    candidates = [
        ("桌面", home / "Desktop"),
        ("下载", home / "Downloads"),
        ("视频", home / "Videos"),
        ("文档", home / "Documents"),
        ("音乐", home / "Music"),
        ("图片", home / "Pictures"),
    ]
    if sys.platform == "darwin":
        candidates[2] = ("视频", home / "Movies")
    return [(name, str(p)) for name, p in candidates if p.is_dir()]



def list_drives():
    # 枚举可用驱动器 / 挂载点（三平台）
    if sys.platform == "win32":
        drives = []
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if os.path.isdir(root):
                drives.append((root, root))
        return drives
    result = [("/", "/")]
    if sys.platform == "linux":
        for base in ("/media", "/mnt"):
            if os.path.isdir(base):
                try:
                    for entry in os.scandir(base):
                        if entry.is_dir(follow_symlinks=False):
                            result.append((entry.name, entry.path))
                except PermissionError:
                    pass
    elif sys.platform == "darwin":
        volumes = Path("/Volumes")
        if volumes.is_dir():
            try:
                for entry in volumes.iterdir():
                    if entry.is_dir():
                        result.append((entry.name, str(entry)))
            except PermissionError:
                pass
    return result


def sorted_entries(path, video_only=False, hide_hidden=False):
    # 列出目录内容，目录在前文件在后各自按字母序；不可读时向上抛
    entries = list(os.scandir(path))

    dirs, files = [], []
    for entry in entries:
        try:
            if hide_hidden and entry.name.startswith("."):
                continue
            if entry.is_dir(follow_symlinks=False):
                dirs.append((entry.name.lower(), entry.name, True))
            elif entry.is_file(follow_symlinks=False):
                if not video_only or is_video_file(entry.name):
                    files.append((entry.name.lower(), entry.name, False))
        except OSError:
            continue

    dirs.sort(key=lambda x: x[0])
    files.sort(key=lambda x: x[0])
    return dirs, files


# ---- 格式化工具 ----
def format_file_size(size_bytes):
    # 将字节数转换为人类可读的文件大小
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_datetime_ts(timestamp):
    # 将时间戳格式化为 YYYY-MM-DD HH:MM:SS
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "未知"


# ---- 配置文件 ----
CONFIG_FILE = os.path.join(_app_dir(), "setting.json")

_DEFAULT_CONFIG = {
    "EnableFileLog": False,
    "CharSets": {
        "ASCII_CHARS_10": " .:-=+*#%@",
        "ASCII_CHARS_16": " .\"!~])txzOp*8$",
        "ASCII_CHARS_32": " .`\";!>~?[)|/frncXUCQOqjka*W8B$",
        "ASCII_CHARS_70": " .'`^\":;Il!i><~+-?][}{)(|\\/tfjrxnuvczXYUJCLQOZwmpqdjbkhao*#MW&8%B@$",
        "ASCII_CHARS_NUMERIC": " 0123456789",
        "ASCII_CHARS_BLOCK": " ░▒▓█"
    },
    "Charset": "ASCII_CHARS_10"
}

LAST_VIDEO_DIR_KEY = "LastVideoDir"


def _ensure_config():
    if not os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(_DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def load_charset():
    _ensure_config()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            selected = config.get("Charset", "ASCII_CHARS_10")
            charsets = config.get("CharSets", {})
            if selected in charsets:
                return charsets[selected]
            return next(iter(charsets.values()), " .:-=+*#%@")
    except (FileNotFoundError, json.JSONDecodeError):
        return " .:-=+*#%@"


def _read_config():
    _ensure_config()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_config_value(key, value):
    # 加锁串行化，避免并发读改写丢更新
    with _CONFIG_LOCK:
        cfg = _read_config()
        cfg[key] = value
        tmp = CONFIG_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            # 原子替换，避免写入中断截断配置
            os.replace(tmp, CONFIG_FILE)
        except Exception:
            try:
                os.remove(tmp)
            except Exception:
                pass
