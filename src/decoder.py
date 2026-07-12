# 统一视频解码器
import re
import subprocess
import time

import cv2
import numpy as np
from utils import (
    clean_fps,
    _forward_stderr, _ffmpeg_exe, _probe_hw_accel,
    _CREATE_NO_WINDOW, _log, _decode_threads,
)


# 视频帧读取器：cv2 优先，失败回退 ffmpeg 管道
class FrameReader:

    def __init__(self, video_path, log=None, force_ffmpeg=False, force_size=None,
                 metadata=None, hwaccel=True, decode_args=None, ffmpeg_usage=None):
        self.path = video_path
        self._log = log or _log
        self._ffmpeg_usage = ffmpeg_usage
        self._force = bool(force_ffmpeg)
        self._force_size = force_size
        self._hwaccel = hwaccel
        self._decode_args = tuple(decode_args) if decode_args else None
        self._cv2 = None
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
            self.width, self.height, self.fps, self.frame_count = metadata
            if self._force_size is not None:
                tw, th = self._force_size
                if tw > 0 and th > 0:
                    self.width, self.height = tw, th
                    self._scale_w, self._scale_h = tw, th
            self._launch_ffmpeg()
        else:
            self._open()

    def _open(self):
        # 尝试用 cv2 打开
        if not self._force:
            cap = cv2.VideoCapture(self.path)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = clean_fps(cap.get(cv2.CAP_PROP_FPS))
                n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                ret, _ = cap.read()
                if w > 0 and h > 0 and ret:
                    try:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    except Exception:
                        pass
                    self._cv2 = cap
                    self.width, self.height = w, h
                    self.fps, self.frame_count = fps, n
                    self.duration = self._probe_duration_ffmpeg(_ffmpeg_exe()) or (n / fps if fps else 0.0)
                    return
                cap.release()
        self._open_ffmpeg()

    def _open_ffmpeg(self):
        # 回退到 ffmpeg 管道解码
        ff = _ffmpeg_exe()
        if not ff:
            raise RuntimeError(
                "无法初始化 cv2 视频解码器，且未找到随包 ffmpeg，无法解码该视频。"
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
                hw = _probe_hw_accel() if self._hwaccel else {"decode": []}
                if hw["decode"]:
                    backends = [d[-1] for d in hw["decode"]]
                    self._log(f"导出解码：使用随包 ffmpeg + 硬件加速 {', '.join(backends)}")
                else:
                    self._log("导出解码：使用随包 ffmpeg 软件解码")
        else:
            self._log("解码回退：cv2 无法打开该视频，改用随包 ffmpeg 管道解码")
        self._launch_ffmpeg()

    def _launch_ffmpeg(self, seek_seconds=0):
        # 启动 ffmpeg 解码管道
        ff = _ffmpeg_exe()
        if self._decode_args:
            candidates = [self._decode_args, None]
        elif self._hwaccel:
            hw = _probe_hw_accel()
            candidates = list(hw["decode"]) + [None]
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
            cmd += ["-i", self.path, "-fps_mode", "passthrough"]
            if self._scale_w > 0 and self._scale_h > 0:
                cmd += ["-vf", f"scale={self._scale_w}:{self._scale_h}"]
            cmd += ["-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
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
        # 用 ffmpeg 探测视频元信息
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

        if txt:
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

        if w <= 0 or h <= 0:
            cap = cv2.VideoCapture(self.path)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or w
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or h
                fps = clean_fps(cap.get(cv2.CAP_PROP_FPS)) or fps
                n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or n
            cap.release()

        return w, h, fps, n, dur

    def _probe_duration_ffmpeg(self, ff):
        # 单独用 ffmpeg 探测真实时长（比 cv2 帧数可靠）
        if not ff:
            return 0.0
        try:
            res = subprocess.run(
                [ff, "-hide_banner", "-i", self.path],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True,
                creationflags=_CREATE_NO_WINDOW,
            )
            txt = res.stderr or ""
        except Exception:
            return 0.0
        md = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", txt)
        if md:
            return int(md.group(1)) * 3600 + int(md.group(2)) * 60 + float(md.group(3))
        return 0.0

    def read(self):
        # 读取一帧
        if self._cv2 is not None:
            return self._cv2.read()
        raw = self._proc.stdout.read(self._frame_bytes)
        if len(raw) < self._frame_bytes:
            return False, None
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(self._pipe_h, self._pipe_w, 3)
        return True, frame

    def seek(self, frame_no):
        # 跳转到指定帧
        frame_no = max(0, min(int(frame_no), max(0, self.frame_count - 1)))
        if self._cv2 is not None:
            try:
                self._cv2.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
                return True
            except Exception:
                return False
        self._kill_proc()
        seek_seconds = frame_no / max(self.fps, 1.0)
        self._launch_ffmpeg(seek_seconds)
        return True

    def _kill_proc(self):
        # 终止 ffmpeg 子进程
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
        # 释放资源
        if self._cv2 is not None:
            try:
                self._cv2.release()
            except Exception:
                pass
            self._cv2 = None
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

    @property
    def is_opened(self):
        return self._cv2 is not None or self._proc is not None
