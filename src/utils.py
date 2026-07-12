# 共享基础设施
import logging
import math
import os
import subprocess
import sys
import threading


# Windows 下隐藏子进程（ffmpeg 等）弹出的控制台窗口
_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW


def _cpu_count():
    # 返回逻辑 CPU 核心数（至少为 1）
    try:
        n = os.cpu_count() or 1
    except Exception:
        n = 1
    return max(1, n)


# ffmpeg 最高占用（两个 ffmpeg 进程合计的核心占用百分比），默认 35%
_FFMPEG_MAX_USAGE = 35


def _set_ffmpeg_max_usage(pct):
    # 设置 ffmpeg 合计最高占用百分比（1~100）
    global _FFMPEG_MAX_USAGE
    try:
        p = int(pct)
    except Exception:
        p = 35
    _FFMPEG_MAX_USAGE = max(1, min(100, p))


def _ffmpeg_usage_threads(usage=None):
    # 由合计占用百分比换算成两个 ffmpeg 的总线程数（向上取整）
    pct = usage if usage is not None else _FFMPEG_MAX_USAGE
    try:
        pct = max(1, min(100, int(pct)))
    except Exception:
        pct = _FFMPEG_MAX_USAGE
    return max(1, int(math.ceil(_cpu_count() * pct / 100.0)))


def _encode_threads(usage=None):
    # 编码进程线程数：占合计预算的 75%（至少 1）
    return max(1, int(round(_ffmpeg_usage_threads(usage) * 0.75)))


def _decode_threads(usage=None):
    # 解码进程线程数：占合计预算的剩余部分（至少 1）
    return max(1, _ffmpeg_usage_threads(usage) - _encode_threads(usage) + 1)


def _app_dir():
    # 程序所在目录：打包后用 exe 同目录；源码运行用启动时的当前工作目录
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


# ---------------------------------------------------------------------------
# 持久日志文件（位于程序所在目录，与 setting.json 同目录，启动即清空）
# ---------------------------------------------------------------------------
_LOG_PATH = os.path.join(_app_dir(), "pyasciifilm.log")
_LOG_LOCK = threading.Lock()
_LOGGER = None


def _init_logger():
    # 惰性配置全局 logger（仅写文件，线程安全）
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
    # 程序启动时清空日志文件
    try:
        with open(_LOG_PATH, "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass


def _log(msg, level=logging.INFO):
    # 写入一行日志到持久文件（全模块共用）
    if not isinstance(msg, str):
        msg = str(msg)
    try:
        with _LOG_LOCK:
            _init_logger().log(level, msg)
    except Exception:
        pass


def _log_error(msg):
    # 便捷：写入错误级日志
    _log(msg, level=logging.ERROR)


def _default_log(msg):
    # 默认日志：转发到真实终端 stderr
    try:
        print(msg, file=sys.stderr)
    except Exception:
        pass


def clean_fps(fps):
    # 把 cv2 探测到的帧率收拢为名义整数帧率
    if fps is None or fps <= 0:
        return 30.0
    r = round(fps)
    if abs(fps - r) < 0.5:
        return float(r)
    return float(fps)


# ---------------------------------------------------------------------------
# ffmpeg 路径
# ---------------------------------------------------------------------------
_FFMPEG = None


def _ffmpeg_exe():
    # 返回随包 ffmpeg 路径；不可用返回 None
    global _FFMPEG
    if _FFMPEG is not None:
        return _FFMPEG
    try:
        import imageio_ffmpeg
        _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        _FFMPEG = False
    return _FFMPEG or None


# ---------------------------------------------------------------------------
# 子进程 stderr 转发
# ---------------------------------------------------------------------------
def _forward_stderr(proc, log):
    # 后台线程逐行读取子进程 stderr 并转发给 log(line)
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


# ---------------------------------------------------------------------------
# 硬件加速探测
# ---------------------------------------------------------------------------
_HW_ACCEL = None


def _validate_encoder(ff, encoder, extra_args, w=160, h=120):
    # 用 1 帧 160x120 yuv420p 实际编码验证编码器是否可用
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
    # 探测随包 ffmpeg 可用的硬件加速后端，返回结构化字典（缓存）
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
            for name in ("h264_nvenc", "h264_qsv", "h264_amf"):
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

    encode_h264 = []
    _H264_CANDIDATES = [
        ("h264_nvenc", ["-preset", "p4", "-rc", "vbr", "-cq", "23",
                         "-pix_fmt", "yuv420p"]),
        ("h264_qsv",   ["-pix_fmt", "yuv420p"]),
        ("h264_amf",   ["-pix_fmt", "yuv420p"]),
    ]
    for enc_name, enc_params in _H264_CANDIDATES:
        if enc_name in listed_encoders and _validate_encoder(ff, enc_name, enc_params):
            encode_h264.append((enc_name, enc_params))

    _HW_ACCEL = {"decode": decode, "encode_h264": encode_h264}
    return _HW_ACCEL


# ---------------------------------------------------------------------------
# 解码后端运行时验证
# ---------------------------------------------------------------------------
def _verify_decode_backend(decode_args):
    # 用 1 帧测试视频验证指定解码后端是否真正可用
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
    # 返回所有经运行时验证可用的解码后端列表
    hw = _probe_hw_accel()
    result = []
    _LABELS = {
        "cuda": "CUDA (NVIDIA)",
        "d3d12va": "D3D12VA",
        "d3d11va": "D3D11VA",
        "dxva2": "DXVA2",
        "qsv": "QSV (Intel)",
    }
    _PRIORITY = {"cuda": 0, "dxva2": 10, "d3d11va": 11, "d3d12va": 12, "qsv": 13}
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
