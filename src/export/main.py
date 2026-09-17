# 导出为视频
import os
import re
import subprocess
import tempfile
import time

from core.main import ASCII_CHARS, make_lookup
from decoder.main import FrameReader
from utils.helpers import (
    clean_fps, _forward_stderr, _ffmpeg_exe,
    _probe_hw_accel, _CREATE_NO_WINDOW, _log, _set_ffmpeg_max_usage,
)
from .renderer import (
    _load_mono_font, _build_glyph_atlas, _render_frame, _small,
    _grids_from_rgb,
)
from .writer import (
    QueuedWriter, _make_ffmpeg_writer, _MAX_CANVAS_W, _MAX_CANVAS_H, _ENCODER_MAX_SIZE,
)

_GRAY_LOOKUP = make_lookup(ASCII_CHARS)


def _make_log(on_log):
    def _cb(msg):
        _log(msg)
        if on_log is not None:
            try:
                on_log(msg)
            except Exception:
                pass
    return _cb


# ---- 导出入口 ----


def export_video(video_path, output_path, target_w, target_h, target_fps,
                 use_color=False, fmt="mp4", on_progress=None, on_done=None,
                 on_log=None, hwaccel=True, ffmpeg_usage=None, cancel=None):
    """单遍导出：边解码边按目标帧率抽样、逐帧渲染编码"""
    decode_args = None
    if isinstance(hwaccel, dict):
        decode_args = hwaccel.get("decode_args")
        hwaccel = bool(decode_args)
    if ffmpeg_usage is not None:
        _set_ffmpeg_max_usage(ffmpeg_usage)
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

    if canvas_w > _MAX_CANVAS_W or canvas_h > _MAX_CANVAS_H:
        msg = (
            f"错误：画布尺寸超出上限（{canvas_w}x{canvas_h}px，"
            f"上限 {_MAX_CANVAS_W}x{_MAX_CANVAS_H}px）"
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
    writer = _make_ffmpeg_writer(output_path, target_fps, canvas_w, canvas_h, fmt, log,
                                 ffmpeg_usage=ffmpeg_usage)
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
        char_to_idx=char_to_idx, ffmpeg_usage=ffmpeg_usage, cancel=cancel)
    writer.release()
    if ok:
        _mux_audio(output_path, video_path, fmt, log)
    elif msg.startswith("已取消"):
        # 取消时删除半成品文件
        if os.path.isfile(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
    return _finish_export(ok, msg, on_done, elapsed=time.time() - t0)


def _finish_export(ok, msg, on_done, elapsed=None):
    if elapsed is not None:
        m, s = divmod(int(elapsed), 60)
        h, m = divmod(m, 60)
        ts = f"{h:d}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        msg = f"{msg}\n  耗时 {ts} ({elapsed:.1f}s)"
    _log(f"导出结束: {'成功' if ok else '失败'} | {msg.replace(chr(10), ' ')}")
    if on_done:
        on_done(ok, msg)
    return ok, msg


def _source_has_audio(video_path, log):
    ff = _ffmpeg_exe()
    if not ff:
        return False
    try:
        res = subprocess.run(
            [ff, "-hide_banner", "-i", video_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            creationflags=_CREATE_NO_WINDOW,
        )
        txt = res.stderr or ""
    except Exception:
        return False
    return bool(re.search(r"Stream.*Audio", txt))


def _mux_audio(output_video_path, source_video_path, fmt, log):
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
                           text=True, creationflags=_CREATE_NO_WINDOW)
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
                                    text=True, creationflags=_CREATE_NO_WINDOW)
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


# ---- 单线程导出 ----


def _export_single(video_path, writer, output_path, target_w, target_h, target_fps, use_color,
                   canvas_w, canvas_h, interval, est_total,
                   on_progress, log, metadata=None, hwaccel=True,
                   decode_args=None,
                   atlas=None, tile_w=None, tile_h=None, char_to_idx=None,
                   ffmpeg_usage=None, cancel=None):
    # 单线程单遍导出；cancel 返回 True 时中断
    out_count = 0
    write_err = False
    src_no = -1
    _next_out = interval

    cap = FrameReader(video_path, log=log, force_ffmpeg=True, force_size=(target_w, target_h),
                      metadata=metadata, hwaccel=hwaccel, decode_args=decode_args,
                      ffmpeg_usage=ffmpeg_usage)
    if on_progress:
        on_progress("render", 0, est_total or 0)
    try:
        while True:
            if cancel and cancel():
                break
            ret, frame = cap.read()
            if not ret:
                break
            src_no += 1
            if (src_no + 1) < _next_out:
                continue
            _next_out += interval

            rgb, gray = _small(frame, target_w, target_h)
            char_grid, color_grid = _grids_from_rgb(rgb, use_color, gray=gray, gray_lookup=_GRAY_LOOKUP)
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

    if cancel and cancel():
        return False, "已取消导出"
    if out_count == 0:
        return False, "错误：导出未写入任何帧"
    if write_err:
        return False, f"错误：导出过程中编码中断（写出 {out_count} 帧后失败）"
    msg = (f"导出完成: {output_path}\n"
           f"  帧数 {out_count} / 分辨率 {canvas_w}x{canvas_h} / 帧率 {target_fps:.2f}fps")
    log(msg.replace("\n", " | "))
    return True, msg