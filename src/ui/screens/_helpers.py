import math
import os
import threading

from utils.helpers import (
    _read_config, _probe_video_meta, _app_dir, user_dirs, list_drives,
    LAST_VIDEO_DIR_KEY,
)

# 视频元数据缓存：(路径 -> (mtime, size, info)) 探测会启动 ffmpeg 子进程，耗时约 50~120 ms
_META_CACHE = {}
_META_CACHE_LOCK = threading.Lock()
_META_CACHE_MAX = 512


def _cached_video_metadata(path: str):
    # 带缓存的元数据读取（同步）。未命中时较慢，勿在 UI 线程直接调用
    try:
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return None
    with _META_CACHE_LOCK:
        hit = _META_CACHE.get(path)
        if hit is not None and hit[0] == key:
            return hit[1]
    info = _probe_video_meta(path)
    with _META_CACHE_LOCK:
        if len(_META_CACHE) >= _META_CACHE_MAX:
            _META_CACHE.clear()
        _META_CACHE[path] = (key, info)
    return info


def _peek_video_metadata(path: str):
    # 只读缓存，绝不触发探测。命中返回 info，否则返回 (False) 哨兵。用于 UI 线程：立即给出结果或提示"尚未就绪"，不阻塞
    try:
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return False
    with _META_CACHE_LOCK:
        hit = _META_CACHE.get(path)
        if hit is not None and hit[0] == key:
            return hit[1]
    return False


def _detect_pending_text():
    """检测未完成时返回待检测项文案（"解码"/"编码"/"解码/编码"），已完成返回空串。"""
    from utils.helpers import _detect_status
    pending = []
    if _detect_status("decode") == "running":
        pending.append("解码")
    if _detect_status("encode") == "running":
        pending.append("编码")
    return "/".join(pending)


def _warn_detect_pending(screen):
    """硬件加速仍在检测中就点了"开始"：黄色提示并返回 True（调用方应中止启动）。

    检测跑在后台线程，此时拿到的后端列表可能不全，直接开跑会用到错误的
    解码/编码模式，所以这里拦下并让用户稍等。
    """
    text = _detect_pending_text()
    if not text:
        return False
    from ..widgets import safe_notify
    safe_notify(screen, f"请等待{text}模式检测完成", severity="warning", timeout=4)
    return True


def _videos_dir():
    # 用户的"视频"目录（三平台；找不到返回空串）
    for name, path in user_dirs():
        if name == "视频" and os.path.isdir(path):
            return path
    return ""


def _fallback_browser_dir():
    # 文件浏览器找不到配置记录时的起始目录。依次尝试：视频目录 -> 程序运行目录 -> 用户主目录 -> 可用驱动器根目录
    home = os.path.expanduser("~")
    for path in (_videos_dir(), _app_dir() or "", home or ""):
        if path and os.path.isdir(path):
            return path
    try:
        drives = list_drives()
        if drives:
            return drives[0][0]
    except Exception:
        pass
    return os.getcwd()


def _load_last_dir():
    try:
        return _read_config().get(LAST_VIDEO_DIR_KEY) or ""
    except Exception:
        return ""


def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "未知"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _probe_video_metadata(path: str) -> dict | None:
    # 读取视频元数据（宽/高/帧率/总帧数/时长）
    return _cached_video_metadata(path)


def _probe_for_confirm(path: str) -> dict | None:
    # 判定"这是不是一个能用的视频"，用于确认选择时校验
    info = _cached_video_metadata(path)
    if info and info.get("frame_count", 0) > 0:
        return info
    # 容器未提供帧数/时长 -> 交给统一入口（内含随包 ffmpeg 兜底）
    from utils.helpers import _probe_video_meta
    info = _probe_video_meta(path, count_frames=True)
    if not info or info.get("frame_count", 0) <= 0:
        return None
    try:
        st = os.stat(path)
        with _META_CACHE_LOCK:
            _META_CACHE[path] = ((st.st_mtime_ns, st.st_size), info)
    except OSError:
        pass
    return info


def char_h_for_w(char_w, src_w, src_h, cell_w, cell_h):
    if src_w <= 0 or src_h <= 0:
        return max(1, round(char_w * 3 / 4))
    h = char_w * (src_h / src_w) * (cell_w / cell_h)
    return max(1, round(h))


def char_w_for_h(char_h, src_w, src_h, cell_w, cell_h):
    if src_w <= 0 or src_h <= 0:
        return max(1, round(char_h * 4 / 3))
    w = char_h * (src_w / src_h) * (cell_h / cell_w)
    return max(1, round(w))


def canvas_bytes(char_w, char_h, cell_w, cell_h):
    cw = int(math.ceil(char_w * cell_w))
    ch = int(math.ceil(char_h * cell_h))
    cw += cw % 2
    ch += ch % 2
    return cw * ch * 3, cw, ch


def recommended_char_size(src_w, src_h, cell_w, cell_h, max_rec_char_w, max_w, max_h):
    if src_w <= 0 or src_h <= 0:
        return 160, 120
    cw = min(max_rec_char_w, max(1, round(src_w / cell_w)))
    ch = char_h_for_w(cw, src_w, src_h, cell_w, cell_h)
    _, rcw, rch = canvas_bytes(cw, ch, cell_w, cell_h)
    if rcw > max_w or rch > max_h:
        scale = min(max_w / rcw, max_h / rch)
        cw = max(1, int(cw * scale))
        ch = char_h_for_w(cw, src_w, src_h, cell_w, cell_h)
    return cw, ch
