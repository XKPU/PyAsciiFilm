# 共享基础设施
import json
import logging
import math
import os
import string
import subprocess
import sys
import threading
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
_LOGGER = None


def _init_logger():
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    logger = logging.getLogger("pyasciifilm")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        fh = logging.FileHandler(_LOG_PATH, encoding="utf-8", delay=False)
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
    """启动时清空日志文件"""
    try:
        with open(_LOG_PATH, "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass


def _log(msg, level=logging.INFO):
    """文件日志（受 EnableFileLog 配置控制）"""
    if not isinstance(msg, str):
        msg = str(msg)
    try:
        cfg = _read_config()
        if not cfg.get("EnableFileLog", False):
            return
    except Exception:
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
    if fps is None or fps <= 0:
        return 30.0
    r = round(fps)
    if abs(fps - r) < 0.5:
        return float(r)
    return float(fps)


# ---- ffmpeg ----
_FFMPEG = None


def _ffmpeg_exe():
    global _FFMPEG
    if _FFMPEG is not None:
        return _FFMPEG
    try:
        import imageio_ffmpeg
        _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
        os.environ.setdefault("IMAGEIO_FFMPEG_EXE", _FFMPEG)
    except Exception:
        _FFMPEG = False
    return _FFMPEG or None


def _init_ffmpeg():
    ff = _ffmpeg_exe()
    if not ff:
        raise RuntimeError("未找到随包 ffmpeg，程序无法运行。请确保 imageio-ffmpeg 已正确安装。")
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", ff)
    return ff


# ---- imageio 视频元数据 ----
def _imageio_probe(path):
    """用 imageio 的 FFMPEG 插件读取视频元数据。

    返回 {"width","height","fps","frame_count","duration"}，失败返回 None。

    要点：
    - 插件名必须是大写 "FFMPEG"：imageio 对插件名大小写敏感，
      传 "ffmpeg" 会抛 ValueError。
    - ffmpeg 插件的 nframes 在非 loop 模式下恒为 inf（见 imageio
      plugins/ffmpeg.py 中 _nframes 的初始化），因此总帧数由
      duration * fps 推算，时长直接取 duration 字段。
    """
    try:
        import imageio.v3 as iio
        meta = iio.immeta(path, plugin="FFMPEG")
        if not meta:
            return None
        size = meta.get("source_size") or meta.get("size") or (0, 0)
        w = int(size[0] or 0)
        h = int(size[1] or 0)
        if w <= 0 or h <= 0:
            return None
        try:
            fps = float(meta.get("fps") or 0)
        except (TypeError, ValueError):
            fps = 0.0
        try:
            duration = float(meta.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0.0
        nframes = meta.get("nframes")
        if isinstance(nframes, int) and nframes > 0:
            n = nframes
            if duration <= 0 and fps > 0:
                duration = n / fps
        else:
            n = int(round(duration * fps)) if duration > 0 and fps > 0 else 0
        return {
            "width": w,
            "height": h,
            "fps": fps,
            "frame_count": n,
            "duration": duration,
        }
    except Exception:
        return None


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


# ---- 硬件加速 ----
_HW_ACCEL = None


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
    for enc_name, enc_params in _H264_CANDIDATES:
        if enc_name in listed_encoders and _validate_encoder(ff, enc_name, enc_params):
            encode_h264.append((enc_name, enc_params))

    _HW_ACCEL = {"decode": decode, "encode_h264": encode_h264}
    return _HW_ACCEL


# ---- 解码后端验证 ----
def _verify_decode_backend(decode_args):
    if not decode_args:
        return True
    ff = _ffmpeg_exe()
    if not ff:
        return False
    import tempfile
    tp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tp = f.name
        r = subprocess.run(
            [ff, "-y", "-hide_banner", "-f", "lavfi",
             "-i", "testsrc=duration=1:size=64x64:rate=1",
             "-pix_fmt", "yuv420p", tp],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        if r.returncode != 0 or not os.path.isfile(tp):
            return False
        cmd = [ff, "-nostdin", "-hide_banner", "-loglevel", "error"] + \
            list(decode_args) + \
            ["-i", tp, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        p = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        return p.returncode == 0 and len(p.stdout) >= 64 * 64 * 3
    except Exception:
        return False
    finally:
        if tp and os.path.isfile(tp):
            try:
                os.remove(tp)
            except Exception:
                pass


def _list_verified_decode_backends():
    hw = _probe_hw_accel()
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
    for args in hw["decode"]:
        name = args[-1]
        label = _LABELS.get(name, name.upper())
        if _verify_decode_backend(args):
            result.append((label, args, _PRIORITY.get(name, 99)))
    result.sort(key=lambda x: x[2])
    hw_items = [(label, args) for label, args, _p in result]
    cuda = [item for item in hw_items if "CUDA" in item[0].upper()]
    others = [item for item in hw_items if "CUDA" not in item[0].upper()]
    return cuda + others + [("软件解码", None)]


# ---- 视频文件类型 ----
VIDEO_EXTS = frozenset({
    ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob",
})


def is_video_file(name):
    """检查文件名是否为支持的视频格式"""
    _, ext = os.path.splitext(name)
    return ext.lower() in VIDEO_EXTS


# ---- 文件系统工具 ----
def user_dirs():
    """返回用户目录快捷访问列表：[(显示名, 路径), ...]（三平台）"""
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
    """枚举可用驱动器 / 挂载点（三平台）"""
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
    """列出目录内容，目录在前、文件在后，各自按字母序。
    返回 (dirs, files)，每项为 (sort_key, name, is_dir)。
    video_only=True 时只返回视频文件。
    hide_hidden=True 时隐藏以 . 开头的文件/目录。"""
    try:
        entries = list(os.scandir(path))
    except PermissionError:
        return [], []
    except OSError:
        return [], []

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
    """将字节数转换为人类可读的文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_datetime_ts(timestamp):
    """将时间戳格式化为 YYYY-MM-DD HH:MM:SS"""
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
LAST_EXPORT_DIR_KEY = "LastExportDir"


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
    cfg = _read_config()
    cfg[key] = value
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass