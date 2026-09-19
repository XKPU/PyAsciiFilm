# 统一视频解码器
import re
import subprocess
import time

import numpy as np
from utils.helpers import (
    clean_fps,
    _forward_stderr, _ffmpeg_exe, _probe_hw_decode,
    _CREATE_NO_WINDOW, _log, _decode_threads,
)


_FPS_FLAG = None


def _fps_flag():
    global _FPS_FLAG
    if _FPS_FLAG is not None:
        return _FPS_FLAG
    flag = ["-vsync", "0"]
    ff = _ffmpeg_exe()
    if ff:
        try:
            r = subprocess.run(
                [ff, "-fps_mode", "passthrough", "-h"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True, creationflags=_CREATE_NO_WINDOW,
            )
            if "Unrecognized option 'fps_mode'" not in (r.stderr or ""):
                flag = ["-fps_mode", "passthrough"]
        except Exception:
            pass
    _FPS_FLAG = flag
    return flag


class FrameReader:
    # 视频帧读取器：统一使用随包 ffmpeg 管道解码

    def __init__(self, video_path, log=None, force_ffmpeg=False, force_size=None,
                 metadata=None, hwaccel=True, decode_args=None, ffmpeg_usage=None):
        self.path = video_path
        self._log = log or _log
        self._ffmpeg_usage = ffmpeg_usage
        self._force = bool(force_ffmpeg)
        self._force_size = force_size
        self._hwaccel = hwaccel
        self._decode_args = tuple(decode_args) if decode_args else None
        self._proc = None
        self._frame_bytes = 0
        self._pipe_w = self._pipe_h = 0
        self._scale_w = 0
        self._scale_h = 0
        self.width = self.height = 0
        self.fps = 0.0
        self.frame_count = 0
        self.duration = 0.0
        if metadata is not None:
            # metadata 是**源视频**的真实宽高，必须原样保留：调用方要据此按纵横比算显示尺寸
            self.width, self.height, self.fps, self.frame_count = metadata
            if self._force_size is not None:
                tw, th = self._force_size
                if tw > 0 and th > 0:
                    self._scale_w, self._scale_h = tw, th
            self._launch_ffmpeg()
        else:
            self._open()

    def _open(self):
        # 统一走随包 ffmpeg 管道：imageio 的解码路径已移除 （慢 2.15x、拒绝部分容器、打包后解析不到二进制）
        self._open_ffmpeg()

    def _open_ffmpeg(self):
        ff = _ffmpeg_exe()
        if not ff:
            raise RuntimeError(
                "无法初始化视频解码器，且未找到随包 ffmpeg，无法解码该视频。"
            )
        w, h, fps, n, dur = self._probe_with_ffmpeg(ff)
        if w <= 0 or h <= 0:
            raise RuntimeError(
                f"无法初始化视频解码器：无法探测视频分辨率（{self.path}）"
            )
        scale_w = scale_h = 0
        if self._force_size is not None:
            tw, th = self._force_size
            if tw > 0 and th > 0:
                w, h = tw, th
                scale_w, scale_h = tw, th
        self._scale_w, self._scale_h = scale_w, scale_h
        self.width, self.height, self.fps, self.frame_count = w, h, fps, n
        self.duration = dur or (n / fps if fps else 0.0)

        if self._force:
            if self._decode_args:
                self._log(f"导出解码：使用指定后端 {self._decode_args[-1]}")
            else:
                backends = [d[-1] for d in _probe_hw_decode()] if self._hwaccel else []
                if backends:
                    self._log(f"导出解码：使用随包 ffmpeg + 硬件加速 {', '.join(backends)}")
                else:
                    self._log("导出解码：使用随包 ffmpeg 软件解码")
        else:
            self._log("解码回退：改用随包 ffmpeg 管道解码")
        self._launch_ffmpeg()

    def _launch_ffmpeg(self, seek_seconds=0):
        ff = _ffmpeg_exe()
        if self._decode_args:
            candidates = [self._decode_args, None]
        elif self._hwaccel:
            # 只探解码：播放不编码，没必要为编码器验证白等半秒
            candidates = list(_probe_hw_decode()) + [None]
        else:
            candidates = [None]

        used = None
        for decode_args in candidates:
            cmd = [ff, "-nostdin", "-loglevel", "warning",
                   "-threads", str(_decode_threads(self._ffmpeg_usage))]
            if decode_args:
                cmd += list(decode_args)
            if seek_seconds > 0:
                cmd += ["-ss", f"{seek_seconds:.3f}"]
            cmd += ["-i", self.path] + _fps_flag()
            if self._scale_w > 0 and self._scale_h > 0:
                cmd += ["-vf", f"scale={self._scale_w}:{self._scale_h}:flags=neighbor"]
            cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
            kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
                      "creationflags": _CREATE_NO_WINDOW}
            self._proc = subprocess.Popen(cmd, **kwargs)
            _forward_stderr(self._proc, self._log)
            time.sleep(0.2)
            if self._proc.poll() is None:
                used = decode_args
                break
            self._proc.terminate()
            if decode_args:
                self._log(f"解码加速 {decode_args[-1]} 不可用，回退下一项…")
        else:
            self._proc = None
            raise RuntimeError("所有解码后端均不可用，无法启动视频解码管道。")

        if used:
            self._log(f"解码加速：已启用 {used[-1]}")
        else:
            self._log("已回退到软件解码")
        w = self._scale_w if self._scale_w > 0 else self.width
        h = self._scale_h if self._scale_h > 0 else self.height
        self._pipe_w, self._pipe_h = w, h
        self._frame_bytes = w * h * 3

    def _probe_with_ffmpeg(self, ff):
        try:
            res = subprocess.run(
                [ff, "-hide_banner", "-i", self.path],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True,
                creationflags=_CREATE_NO_WINDOW,
            )
            txt = res.stderr or ""
        except Exception:
            txt = ""

        w = h = 0
        m = re.search(r"Stream.*?Video.*?(\d{2,})x(\d{2,})", txt)
        if m:
            w, h = int(m.group(1)), int(m.group(2))

        fps = 0.0
        mf = re.search(r"(\d+(?:\.\d+)?)\s*fps", txt)
        if mf:
            fps = clean_fps(float(mf.group(1)))

        n = 0
        dur = 0.0
        mn = re.search(r"nb_frames\s*=\s*(\d+)", txt)
        if mn:
            n = int(mn.group(1))
        md = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", txt)
        if md:
            dur = int(md.group(1)) * 3600 + int(md.group(2)) * 60 + float(md.group(3))
            if not n and fps:
                n = int(dur * fps)


        return w, h, fps, n, dur

    def read(self):
        # _frame_bytes 为 0 时会得到 (0,0,3) 的假帧，渲染时按宽度相除直接 ZeroDivisionError
        if self._frame_bytes <= 0:
            return False, None
        raw = self._proc.stdout.read(self._frame_bytes)
        if len(raw) < self._frame_bytes:
            return False, None
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(self._pipe_h, self._pipe_w, 3)
        return True, frame

    def skip_frames(self, count):
        # 丢弃 count 帧（不构造图像），用于播放落后时追赶时间轴。只从管道读走字节并丢弃，比逐帧 read + 渲染便宜得多
        if count <= 0:
            return True
        nbytes = count * self._frame_bytes
        if nbytes <= 0:
            return False
        got = 0
        while got < nbytes:
            chunk = self._proc.stdout.read(nbytes - got)
            if not chunk:
                return False
            got += len(chunk)
        return True

    def _kill_proc(self):
        if self._proc is None:
            return
        try:
            self._proc.stdout.close()
        except Exception:
            pass
        try:
            self._proc.terminate()
        except Exception:
            pass
        try:
            self._proc.wait(timeout=2)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None

    def release(self):
        if self._proc is not None:
            try:
                self._proc.stdout.close()
            except Exception:
                pass
            try:
                self._proc.terminate()
            except Exception:
                pass
            try:
                self._proc.wait(timeout=2)
            except Exception:
                pass
            self._proc = None
