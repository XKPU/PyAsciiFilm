# 导出写出（ffmpeg 子进程 + 队列编码）
import os
import queue
import subprocess
import threading

from utils.helpers import (
    _forward_stderr, _ffmpeg_exe, _probe_hw_accel, _CREATE_NO_WINDOW,
    _encode_threads, _validate_encoder,
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
    # ffmpeg 子进程写出器

    def __init__(self, proc, codec):
        self._proc = proc
        self.codec = codec

    def write(self, frame):
        # 编码器中途退出时给出可读的报错，而不是 BrokenPipeError
        rc = self._proc.poll()
        if rc is not None:
            raise RuntimeError(
                f"编码器 {self.codec} 已退出（返回码 {rc}），导出中断"
            )
        try:
            self._proc.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(
                f"写入编码器 {self.codec} 失败，导出中断: {e}"
            ) from e

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
    # 帧队列+后台编码线程

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
        # 不能用阻塞 put：编码线程一旦因编码器死亡而退出，队列会一直是满的，put 永久阻塞 -> 取消再也检查不到，导出卡死无法恢复
        while True:
            if self._error:
                raise self._error
            try:
                self._queue.put(frame, timeout=0.25)
                return
            except queue.Full:
                if not self._thread.is_alive():
                    if self._error:
                        raise self._error
                    raise RuntimeError("编码线程已退出，导出未能完成")

    @property
    def codec(self):
        return self._writer.codec

    def release(self):
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        self._thread.join(timeout=60)
        if self._thread.is_alive():
            # 超时说明编码线程还卡着（编码器不消费 stdin）。此时不能假装成功，否则后续 _mux_audio 会去读一个还在被写入的文件
            raise RuntimeError("编码线程未能在超时内结束，导出可能不完整")
        if self._error:
            raise self._error


def _make_ffmpeg_writer(output_path, fps, w, h, fmt, log, ffmpeg_usage=None,
                        encoder=None):
    # 创建 ffmpeg 编码写入器。encoder=None 表示自动：优先硬件编码器，失败再回退软件
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

    if encoder:
        # 用户指定：只用它，参数取该编码器的标准参数
        params = None
        try:
            for hw_codec, hw_params in _probe_hw_accel().get("encode_h264", []):
                if hw_codec == encoder:
                    params = list(hw_params)
                    break
        except Exception:
            pass
        if params is None:
            # 软件编码器或未在硬件列表中的，取格式默认参数
            for c_name, c_params in base:
                if c_name == encoder:
                    params = list(c_params)
                    break
        if params is None:
            params = ["-pix_fmt", "yuv420p"]
        # 用户指定也要做尺寸校验：画布低于编码器下限会直接失败，与其让 ffmpeg 报错，不如提前说明并回退软件编码
        max_w, max_h = _ENCODER_MAX_SIZE.get(encoder, (_MAX_CANVAS_W, _MAX_CANVAS_H))
        min_w, min_h = _ENCODER_MIN_SIZE.get(encoder, (1, 1))
        if w > max_w or h > max_h:
            log(f"画布 {w}x{h}px 超出 {encoder} 限制 {max_w}x{max_h}，改用软件编码")
            encoder, params = None, None
        elif w < min_w or h < min_h:
            log(f"画布 {w}x{h}px 低于 {encoder} 最低要求 {min_w}x{min_h}，改用软件编码")
            encoder, params = None, None
        if encoder is None:
            codecs = list(base)
        else:
            # 校验该编码器真能用：不存在的名字若不拦住，会在写入时以 BrokenPipeError 的形式炸出来（ffmpeg 启动后才退出）
            if not _validate_encoder(ff, encoder, params, w=min(w, 320), h=min(h, 240)):
                log(f"编码器 {encoder} 不可用，改用软件编码")
                codecs = list(base)
            else:
                codecs = [(encoder, params)]
                log(f"编码模式：指定 {encoder}")
    else:
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
