"""导出/播放设置页共享的纯函数辅助"""
import math
import os

from utils.helpers import _read_config, LAST_VIDEO_DIR_KEY


def _load_last_dir(key="last_video_dir"):
    try:
        return _read_config().get(LAST_VIDEO_DIR_KEY) or ""
    except Exception:
        return ""


def _load_last_export_dir():
    try:
        return _read_config().get("last_export_dir") or ""
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
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return None
        info = {
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        }
        cap.release()
        fps = info.get("fps", 0) or 0
        frames = info.get("frame_count", 0) or 0
        info["duration"] = frames / fps if fps > 0 and frames > 0 else 0
        return info
    except Exception:
        return None


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