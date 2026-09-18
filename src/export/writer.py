# 导出写出（ffmpeg 子进程 + 队列编码）
import os
import queue
import subprocess
import threading

from utils.helpers import (
    _forward_stderr, _ffmpeg_exe, _probe_hw_accel, _CREATE_NO_WINDOW,
    _encode_threads,
)


_FMT_FFMPEG_CODECS = {
    "mp4":  [("libx264", ["-pix_fmt", "yuv420p"])],
    "mov":  [("libx264", ["-pix_fmt", "yuv420p"])],
    "mkv":  [("libx264", ["-pix_fmt", "yuv420p"])],
    "avi":  [("libx264", ["-pix_fmt", "yuv420p"]), ("mpeg4", [])],
    "webm": [("libvpx", ["-pix_fmt", "yuv420p", "-deadline", "realtime",
                         "-cpu-used", "8", "-b:v", "0", "-crf", "18"]),
             ("libvpx-vp9", ["-pix_fmt", "yuv420p", "-deadline", "realtime",
                             "-cpu-used", "8", "-b:v", "0", "-crf", "30"])],
}

_ENCODER_MAX_SIZE = {
    "h264_nvenc": (4096, 4096),
    "h264_qsv":   (4096, 4096),
    "h264_amf":   (4096, 4096),
}
_MAX_CANVAS_W = 8192
_MAX_CANVAS_H = 8192

_ENCODER_MIN_SIZE = {
    "h264_nvenc": (145, 65),
    "h264_qsv":   (32, 32),
    "h264_amf":   (64, 64),
}


class _FFmpegWriter:
    """ffmpeg 子进程写出器"""

    def __init__(self, proc, codec):
        self._proc = proc
        self.codec = codec

    def write(self, frame):
        self._proc.stdin.write(frame.tobytes())

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
    """帧队列+后台编码线程"""

    def __init__(self, writer, maxsize=32):
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
        if self._error:
            raise self._error
        self._queue.put(frame)

    @property
    def codec(self):
        return self._writer.codec

    def release(self):
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        self._thread.join(timeout=60)
        if self._error:
            raise self._error


def _make_ffmpeg_writer(output_path, fps, w, h, fmt, log, ffmpeg_usage=None):
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
                max_w, max_h = _ENCODER_MAX_SIZE.get(hw_codec, (_MAX_CANVAS_W, _MAX_CANVAS_H))
                if w > max_w or h > max_h:
                    log(f"画布 {w}x{h}px 超出 {hw_codec} 限制 {max_w}x{max_h}，跳过")
                    continue
                min_w, min_h = _ENCODER_MIN_SIZE.get(hw_codec, (1, 1))
                if w < min_w or h < min_h:
                    log(f"画布 {w}x{h}px 低于 {hw_codec} 最低要求 {min_w}x{min_h}，跳过")
                    continue
                codecs.insert(0, (hw_codec, hw_params))
    for codec, extra in codecs:
        cmd = [
            ff, "-y", "-nostdin", "-loglevel", "warning",
            "-threads", str(_encode_threads(ffmpeg_usage)),
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-",
            "-an", "-c:v", codec,
            "-force_key_frames", "expr:eq(n,0)",
        ] + list(extra)
        if fmt == "mp4":
            cmd += ["-movflags", "+faststart"]
        cmd += [output_path]
        kwargs = {"stdin": subprocess.PIPE, "stderr": subprocess.PIPE,
                  "creationflags": _CREATE_NO_WINDOW}
        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except Exception as e:
            log(f"编码器 {codec} 启动失败: {e}")
            continue
        _forward_stderr(proc, log)
        if proc.poll() is not None:
            log(f"错误：编码器 {codec} 初始化失败（格式 {fmt}）")
            continue
        return _FFmpegWriter(proc, codec)
    return None