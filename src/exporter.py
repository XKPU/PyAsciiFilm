# 导出为视频（高性能 + 多格式）
import os
import math
import platform
import subprocess
import logging
import tempfile
import threading
import time

import re
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ascii_art import ASCII_CHARS, make_lookup
from analyze import clean_fps
from decoder import FrameReader
from utils import (
    _write_log_file, _forward_stderr, _ffmpeg_exe,
    _probe_hw_accel, _log_level,
)

# 灰度->字符查找表构建一次复用
_GRAY_LOOKUP = make_lookup(ASCII_CHARS)

# 容器格式 -> ffmpeg 视频编码器候选（按顺序尝试）
_FMT_FFMPEG_CODECS = {
    "mp4":  [("libx264", ["-pix_fmt", "yuv420p"])],
    "mov":  [("libx264", ["-pix_fmt", "yuv420p"])],
    "mkv":  [("libx264", ["-pix_fmt", "yuv420p"])],
    "avi":  [("libx264", ["-pix_fmt", "yuv420p"]), ("mpeg4", [])],
    "webm": [("libvpx", ["-b:v", "0", "-crf", "18"]),
             ("libvpx-vp9", ["-b:v", "0", "-crf", "30"])],
}

# 单帧字节上限
_MAX_FRAME_BYTES = 50 * 1024 * 1024


class _FFmpegWriter:
    # 基于随包 ffmpeg 子进程的视频写出器

    def __init__(self, proc, codec, w, h):
        self._proc = proc
        self.codec = codec
        self._w, self._h = w, h
        self._failed = False

    def write(self, frame):
        try:
            self._proc.stdin.write(frame.tobytes())
        except Exception:
            self._failed = True
            raise

    @property
    def failed(self):
        return self._failed

    def release(self):
        try:
            self._proc.stdin.close()
        except Exception:
            pass
        try:
            self._proc.wait(timeout=30)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        try:
            self._proc.stderr.close()
        except Exception:
            pass


class QueuedWriter:
    # 编码线程分离

    def __init__(self, writer, maxsize=32):
        import queue
        self._writer = writer
        self._queue = queue.Queue(maxsize=maxsize)
        self._error = None
        self._thread = threading.Thread(target=self._encode_loop, daemon=True)
        self._thread.start()

    def _encode_loop(self):
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                self._writer.write(item)
        except Exception as e:
            self._error = e
        finally:
            try:
                self._writer.release()
            except Exception:
                pass

    def write(self, frame):
        # 将帧丢入队列
        if self._error:
            raise self._error
        self._queue.put(frame)

    @property
    def failed(self):
        return self._error is not None or self._writer.failed

    @property
    def codec(self):
        return self._writer.codec

    def release(self):
        # 通知编码线程停止并等待结束
        self._queue.put(None)
        self._thread.join(timeout=60)
        if self._error:
            raise self._error


def _make_ffmpeg_writer(output_path, fps, w, h, fmt, log):
    # 构造 _FFmpegWriter
    ff = _ffmpeg_exe()
    if not ff:
        log("错误：未找到随包 ffmpeg，无法编码导出视频")
        return None
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            log(f"无法创建输出目录 {out_dir}: {e}")
    base = _FMT_FFMPEG_CODECS.get(fmt, [("libx264", ["-pix_fmt", "yuv420p"])])
    codecs = list(base)
    if fmt in ("mp4", "mov", "mkv"):
        hw = _probe_hw_accel()
        for hw_codec, hw_params in hw["encode_h264"]:
            if hw_codec not in [c[0] for c in codecs]:
                codecs.insert(0, (hw_codec, hw_params))
    for codec, extra in codecs:
        cmd = [
            ff, "-y", "-nostdin", "-loglevel", "warning",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-",
            "-an", "-c:v", codec,
            "-force_key_frames", "expr:eq(n,0)",
        ] + list(extra)
        if fmt == "mp4":
            cmd += ["-movflags", "+faststart"]
        cmd += [output_path]
        kwargs = {"stdin": subprocess.PIPE, "stderr": subprocess.PIPE}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except Exception as e:
            log(f"编码器 {codec} 启动失败: {e}")
            continue
        _forward_stderr(proc, log)
        if proc.poll() is not None:
            log(f"错误：编码器 {codec} 初始化失败（格式 {fmt}）")
            continue
        return _FFmpegWriter(proc, codec, w, h)
    return None


def _make_log(on_log):
    # 构造传给 FrameReader 的 log 回调
    def _log(msg):
        _write_log_file(msg, level=_log_level(msg))
        if on_log is not None:
            try:
                on_log(msg)
            except Exception:
                pass
    return _log


# --------------------------- 字体 ---------------------------
def _load_mono_font(charset=None):
    # 跨平台加载一个等宽字体
    sys_name = platform.system()
    if sys_name == "Windows":
        candidates = [
            "C:/Windows/Fonts/consola.ttf",
            "C:/Windows/Fonts/cour.ttf",
            "C:/Windows/Fonts/lucon.ttf",
        ]
    elif sys_name == "Darwin":
        candidates = [
            "/System/Library/Fonts/Menlo.ttc",
            "/Library/Fonts/DejaVuSansMono.ttf",
            "/System/Library/Fonts/Monaco.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        ]
        try:
            import shutil
            if shutil.which("fc-match"):
                out = subprocess.check_output(
                    ["fc-match", "monospace:spacing=mono"], text=True
                ).split(":")[0].strip()
                if out:
                    if os.path.isabs(out) and os.path.exists(out):
                        candidates.insert(0, out)
                    else:
                        for d in ("/usr/share/fonts", "/usr/local/share/fonts"):
                            p = os.path.join(d, out)
                            if os.path.exists(p):
                                candidates.insert(0, p)
                                break
        except Exception:
            pass

    sample = list(" .:-=+*#%@MWAi01abcdefghijklmnopqrstuvwxyz[](){}/\\|")
    if charset:
        for ch in charset:
            if ch not in sample:
                sample.append(ch)

    def _is_monospace(font):
        try:
            adv = [font.getlength(c) for c in sample]
        except Exception:
            return False
        return bool(adv) and (max(adv) - min(adv)) <= 0.5

    font = None
    for path in candidates:
        if not path or not os.path.exists(path):
            continue
        try:
            f = ImageFont.truetype(path, size=20)
        except Exception:
            continue
        if _is_monospace(f):
            font = f
            break

    if font is None:
        for path in candidates:
            if path and os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, size=20)
                    break
                except Exception:
                    continue
    if font is None:
        font = ImageFont.load_default()

    cell_w = float(font.getlength("M"))
    ascent, descent = font.getmetrics()
    cell_h = ascent + descent
    if cell_w <= 0 or cell_h <= 0:
        cell_w, cell_h = 10.0, 20
    return font, cell_w, cell_h


# --------------------------- 渲染辅助 ---------------------------
def _build_glyph_atlas(font, cell_w, cell_h, chars):
    # 一次性把字符集每个字形栅格化成字模图集
    tile_w = max(1, int(math.ceil(cell_w)))
    tile_h = max(1, int(math.ceil(cell_h)))
    uniq = list(dict.fromkeys(chars))
    if " " not in uniq:
        uniq.insert(0, " ")
    G = len(uniq)
    atlas = np.zeros((G, tile_h, tile_w), dtype=np.uint8)
    for i, ch in enumerate(uniq):
        img = Image.new("L", (tile_w, tile_h), 0)
        ImageDraw.Draw(img).text((0, 0), ch, fill=255, font=font)
        atlas[i] = np.asarray(img, dtype=np.uint8)
    char_to_idx = {ch: i for i, ch in enumerate(uniq)}
    return atlas, tile_w, tile_h, char_to_idx


def _render_frame(char_grid, color_grid, atlas, tile_w, tile_h, char_to_idx, use_color,
                 canvas_w, canvas_h):
    # 纯 numpy 渲染一帧为 BGR 字节
    h, w = char_grid.shape
    H, W = h * tile_h, w * tile_w
    space_idx = char_to_idx.get(" ", 0)
    def _lookup(ch):
        return char_to_idx.get(ch, space_idx)
    idx = np.frompyfunc(_lookup, 1, 1)(char_grid.ravel())
    idx = np.asarray(idx, dtype=np.intp).reshape(h, w)
    luma = atlas[idx]
    luma = luma.swapaxes(1, 2).reshape(H, W)

    if use_color and color_grid is not None:
        color_tiled = cv2.resize(color_grid, (W, H), interpolation=cv2.INTER_NEAREST)
        rgb = (luma.astype(np.float32)[..., None]
               * color_tiled.astype(np.float32) / 255.0 + 0.5).astype(np.uint8)
        cur = rgb[:, :, ::-1].copy()
    else:
        out = np.empty((H, W, 3), dtype=np.uint8)
        out[..., 0] = luma
        out[..., 1] = luma
        out[..., 2] = luma
        cur = out
    if cur.shape[0] != canvas_h or cur.shape[1] != canvas_w:
        padded = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
        padded[:cur.shape[0], :cur.shape[1]] = cur
        cur = padded
    return cur


def _small(frame, target_w, target_h):
    # 把一帧缩放到目标字符网格尺寸
    if frame.shape[1] == target_w and frame.shape[0] == target_h:
        resized = frame
    else:
        resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    return rgb, gray


def _grids_from_rgb(rgb, use_color, gray=None):
    # 由已缩放的 RGB 数组生成字符网格与颜色网格
    lum = gray if gray is not None else cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    char_grid = _GRAY_LOOKUP[lum]
    color_grid = rgb if use_color else None
    return char_grid, color_grid


# --------------------------- 主导出入口 ---------------------------
def export_video(video_path, output_path, target_w, target_h, target_fps,
                 use_color=False, fmt="mp4", on_progress=None, on_done=None,
                 on_log=None, hwaccel=True):
    # 单遍导出：解码的同时按目标帧率抽样并逐帧渲染编码
    decode_args = None
    if isinstance(hwaccel, dict):
        decode_args = hwaccel.get("decode_args")
        hwaccel = bool(decode_args)
    log = _make_log(on_log)
    log(f"开始导出: 输入={video_path} -> 输出={output_path} (格式 {fmt}, 彩色={use_color})")
    try:
        cap = FrameReader(video_path, log=log, force_ffmpeg=True, hwaccel=hwaccel,
                          decode_args=decode_args)
    except Exception as e:
        msg = f"错误：无法打开视频（{e}）"
        if on_done:
            on_done(False, msg)
        return False, msg
    src_fps = clean_fps(cap.fps)
    src_w = int(cap.width)
    src_h = int(cap.height)
    src_count = int(cap.frame_count)
    cap.release()
    log(f"源视频: {src_w}x{src_h} @ {src_fps:.2f}fps -> 目标 {target_w}x{target_h} @ {target_fps:.2f}fps")

    target_w = max(1, min(int(target_w), src_w))
    target_h = max(1, min(int(target_h), src_h))
    target_fps = max(1.0, min(float(target_fps), src_fps))
    interval = max(1.0, src_fps / max(0.1, target_fps))
    est_total = max(1, int(round(src_count / interval))) if src_count > 0 else None

    font, cell_w, cell_h = _load_mono_font(ASCII_CHARS)
    atlas, tile_w, tile_h, char_to_idx = _build_glyph_atlas(font, cell_w, cell_h, ASCII_CHARS)
    canvas_w = target_w * tile_w
    canvas_h = target_h * tile_h
    canvas_w += canvas_w % 2
    canvas_h += canvas_h % 2

    frame_bytes = canvas_w * canvas_h * 3
    if frame_bytes > _MAX_FRAME_BYTES:
        msg = (
            f"错误：目标分辨率过大（字符网格 {target_w}x{target_h} → 画布 "
            f"{canvas_w}x{canvas_h}，单帧约 {frame_bytes / 1048576:.0f}MB）"
        )
        log(msg)
        if on_done:
            on_done(False, msg)
        return False, msg

    metadata = (src_w, src_h, src_fps, src_count)
    t0 = time.time()

    if decode_args:
        log(f"解码模式: {decode_args[-1]}")
    elif hwaccel:
        log("解码模式: 随包 ffmpeg 自动选择")
    else:
        log("解码模式: ffmpeg 软件解码")
    writer = _make_ffmpeg_writer(output_path, target_fps, canvas_w, canvas_h, fmt, log)
    if writer is None:
        msg = f"错误：无法初始化视频编码器（格式 {fmt}，所有候选编码器均失败）"
        log(msg)
        return _finish_export(False, msg, on_done)
    writer = QueuedWriter(writer)
    log(f"导出开始: 画布 {canvas_w}x{canvas_h} @ {target_fps:.2f}fps, 格式 {fmt}, 编码器 {writer.codec}, 彩色={use_color}")
    ok, msg = _export_single(
        video_path, writer, output_path, target_w, target_h, target_fps, use_color,
        canvas_w, canvas_h, interval, est_total, on_progress, log,
        metadata=metadata, hwaccel=hwaccel, decode_args=decode_args,
        atlas=atlas, tile_w=tile_w, tile_h=tile_h,
        char_to_idx=char_to_idx)
    writer.release()
    if ok:
        _mux_audio(output_path, video_path, fmt, log)
    return _finish_export(ok, msg, on_done, elapsed=time.time() - t0)


def _finish_export(ok, msg, on_done, elapsed=None):
    # 导出结束处理
    if elapsed is not None:
        m, s = divmod(int(elapsed), 60)
        h, m = divmod(m, 60)
        ts = f"{h:d}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        msg = f"{msg}\n  耗时 {ts} ({elapsed:.1f}s)"
    _write_log_file(
        f"导出结束: {'成功' if ok else '失败'} | {msg.replace(chr(10), ' ')}",
        level=logging.INFO if ok else logging.ERROR,
    )
    if on_done:
        on_done(ok, msg)
    return ok, msg


def _source_has_audio(video_path, log):
    # 检查原视频是否含音频流
    ff = _ffmpeg_exe()
    if not ff:
        return False
    try:
        res = subprocess.run(
            [ff, "-hide_banner", "-i", video_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        txt = res.stderr or ""
    except Exception:
        return False
    return bool(re.search(r"Stream.*Audio", txt))


def _mux_audio(output_video_path, source_video_path, fmt, log):
    # 把原视频的音频轨并入无声导出视频
    if not os.path.isfile(output_video_path):
        return
    if not _source_has_audio(source_video_path, log):
        return
    ff = _ffmpeg_exe()
    if not ff:
        return

    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(output_video_path)[1])
    os.close(fd)

    common = [
        ff, "-y", "-nostdin", "-loglevel", "warning",
        "-i", output_video_path, "-i", source_video_path,
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-shortest",
    ]
    if fmt == "mp4":
        common += ["-movflags", "+faststart"]
    cmd = common + ["-c:a", "copy", tmp]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        r = None
        log(f"警告：复制音频异常（保留无声视频）: {e}")
    if r is not None and r.returncode != 0:
        acodec = {"mp4": "aac", "mov": "aac", "mkv": "aac",
                  "avi": "aac", "webm": "libvorbis"}.get(fmt)
        if acodec:
            log("音频 copy 失败，尝试重新编码音频轨…")
            cmd2 = common + ["-c:a", acodec, tmp]
            try:
                r2 = subprocess.run(cmd2, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                    text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception as e:
                r2 = None
                log(f"警告：重编码音频异常（保留无声视频）: {e}")
            if r2 is not None and r2.returncode == 0:
                os.replace(tmp, output_video_path)
                log("已复制（重编码）原视频音频轨到导出文件")
                return
        log(f"警告：复制音频失败（保留无声视频）: {(r.stderr or '')[:300]}")
        try:
            os.remove(tmp)
        except Exception:
            pass
        return
    os.replace(tmp, output_video_path)
    log("已复制原视频音频轨到导出文件")


# --------------------------- 单线程导出 ---------------------------
def _export_single(video_path, writer, output_path, target_w, target_h, target_fps, use_color,
                   canvas_w, canvas_h, interval, est_total,
                   on_progress, log, metadata=None, hwaccel=True,
                   decode_args=None,
                   atlas=None, tile_w=None, tile_h=None, char_to_idx=None):
    # 单线程单遍导出
    out_count = 0
    write_err = False
    src_no = -1
    _next_out = interval

    cap = FrameReader(video_path, log=log, force_ffmpeg=True, force_size=(target_w, target_h),
                      metadata=metadata, hwaccel=hwaccel, decode_args=decode_args)
    if on_progress:
        on_progress("render", 0, est_total or 0)
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            src_no += 1
            if (src_no + 1) < _next_out:
                continue
            _next_out += interval

            rgb, gray = _small(frame, target_w, target_h)
            char_grid, color_grid = _grids_from_rgb(rgb, use_color, gray=gray)
            cur = _render_frame(char_grid, color_grid, atlas, tile_w, tile_h,
                                char_to_idx, use_color, canvas_w, canvas_h)
            try:
                writer.write(cur)
            except Exception as e:
                log(f"错误：写入帧失败（编码中断）: {e}")
                write_err = True
                break
            out_count += 1
            if on_progress:
                on_progress("render", out_count, est_total or out_count)
    finally:
        cap.release()

    if out_count == 0:
        return False, "错误：导出未写入任何帧"
    if write_err:
        return False, f"错误：导出过程中编码中断（写出 {out_count} 帧后失败）"
    msg = (f"导出完成: {output_path}\n"
           f"  帧数 {out_count} / 分辨率 {canvas_w}x{canvas_h} / 帧率 {target_fps:.2f}fps")
    log(msg.replace("\n", " | "))
    return True, msg
