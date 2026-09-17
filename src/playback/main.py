# 字符画帧生成与终端播放
import os
import sys
import time
import shutil

import cv2
import numpy as np

from audio.main import start_audio
from core.main import generate_colored_frame, generate_grayscale_frame
from decoder.main import FrameReader
from utils.helpers import _log, _log_error


_playback_logs = []


def _frame_to_terminal_text(frame, width, use_color):
    aspect = frame.shape[0] / frame.shape[1]
    new_height = max(1, int(aspect * width * 0.5))
    resized = cv2.resize(frame, (width, new_height))
    if use_color:
        pixels = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        lum = (pixels[:, :, 0].astype(np.uint32) * 299
               + pixels[:, :, 1].astype(np.uint32) * 587
               + pixels[:, :, 2].astype(np.uint32) * 114
               + 500) // 1000
        lum = lum.astype(np.uint8)
        frame_text = generate_colored_frame(pixels, lum)
    else:
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        frame_text = generate_grayscale_frame(gray)
    return "\n".join(line + "\033[K" for line in frame_text.split("\n"))


def _enable_windows_ansi():
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


class _KeyReader:
    """非阻塞键盘读取（三平台）"""

    def __init__(self):
        try:
            import msvcrt
            self._msvcrt = msvcrt
        except ImportError:
            self._msvcrt = None
        self._posix = self._setup_posix() if self._msvcrt is None else None

    def _setup_posix(self):
        import sys
        if not sys.stdin.isatty():
            return None
        try:
            import termios, tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            return fd, old
        except Exception:
            return None

    def quit_pressed(self):
        if self._msvcrt is not None:
            if self._msvcrt.kbhit():
                ch = self._msvcrt.getch()
                return ch in (b"\x11", b"\x1b")
            return False
        if not self._posix:
            return False
        import select
        fd, _old = self._posix
        try:
            r, _, _ = select.select([fd], [], [], 0)
            if not r:
                return False
            ch = os.read(fd, 1)
            return ch in (b"\x11", b"\x1b")
        except Exception:
            return False

    def close(self):
        if not self._posix:
            return
        import termios
        fd, old = self._posix
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass
        self._posix = None


def _get_terminal_size():
    cols, rows = shutil.get_terminal_size((100, 30))
    return cols, rows


def _calculate_optimal_width(term_width, term_height, video_width, video_height):
    max_ascii_width = min(term_width - 1, video_width)
    max_ascii_height = min(term_height - 1, video_height)

    terminal_aspect = max_ascii_height / (max_ascii_width * 0.5)
    video_aspect = video_height / video_width

    if video_aspect <= terminal_aspect:
        ascii_width = max_ascii_width
    else:
        ascii_width = int((max_ascii_height / video_aspect) * 2)

    return max(20, ascii_width)


def _create_progress_bar(current, total, width=50):
    if total <= 0:
        return "[未知进度]"
    progress = max(0.0, min(1.0, current / total))
    filled_width = int(width * progress)
    bar = "█" * filled_width + "░" * (width - filled_width)
    percent = progress * 100
    return f"[{bar}] {percent:.1f}%"


def play_video(video_path, use_color=False, with_audio=True,
               target_fps=None, decode_args=None, ffmpeg_usage=None):
    _enable_windows_ansi()
    _log(f"播放初始化: {video_path} | 彩色={use_color} 音频={with_audio}"
         f" | 目标帧率={target_fps} | 解码={decode_args} | CPU占用={ffmpeg_usage}")
    out = sys.stdout

    _playback_logs = []

    def _buf_log(msg):
        try:
            _playback_logs.append(msg)
        except Exception:
            pass
        _log(msg)

    try:
        cap = FrameReader(video_path, log=_buf_log,
                          decode_args=decode_args, ffmpeg_usage=ffmpeg_usage)
    except Exception as e:
        _log_error(f"无法打开视频文件（{e}）")
        print(f"错误: 无法打开视频文件（{e}）")
        return False

    fps = cap.fps or 30.0
    if target_fps and target_fps > 0:
        fps = min(fps, target_fps)
    frame_interval = 1.0 / max(fps, 1.0)
    video_width = int(cap.width)
    video_height = int(cap.height)
    total_frames = int(cap.frame_count)
    total_duration = cap.duration if cap.duration and cap.duration > 0 else (
        total_frames / fps if fps else 0.0)

    audio = start_audio(video_path, log=_buf_log) if with_audio else None
    stop_audio = audio[0] if audio else None
    get_audio_start = audio[1] if audio else None
    keys = _KeyReader()

    out.write("\033[?1049h\033[2J\033[?25l")
    out.flush()

    term_width, term_height = _get_terminal_size()
    ascii_width = _calculate_optimal_width(term_width, term_height,
                                           video_width, video_height)
    last_width = ascii_width

    start = time.monotonic()
    if get_audio_start is not None:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            astart = get_audio_start()
            if astart is not None:
                start = astart
                break
            time.sleep(0.01)

    idx = 0
    try:
        while True:
            if idx % 10 == 0:
                term_width, term_height = _get_terminal_size()
                w = _calculate_optimal_width(term_width, term_height,
                                             video_width, video_height)
                if w != last_width:
                    out.write("\033[H\033[J")
                    last_width = w
                ascii_width = w

            ret, frame = cap.read()
            if not ret:
                break

            ascii_frame = _frame_to_terminal_text(frame, ascii_width,
                                                   use_color)
            idx += 1

            color_mode_text = "全彩" if use_color else "灰度"
            estimate_h = int(ascii_width * (video_height / video_width) * 0.5)
            progress_info = (
                f"平均帧率: {idx / max(time.monotonic() - start, 1e-6):.1f} FPS"
                f" | 原视频帧: {idx}/{total_frames} | {color_mode_text}"
                f" | 分辨率: {ascii_width}x{estimate_h}"
            )
            elapsed = time.monotonic() - start
            max_bar = max(5, term_width - len(progress_info) - 2)
            bar_width = max(5, min(ascii_width // 2, max_bar))
            if total_duration > 0:
                progress_bar = _create_progress_bar(elapsed, total_duration,
                                                    bar_width)
            else:
                progress_bar = _create_progress_bar(idx, total_frames,
                                                    bar_width)

            output = f"{ascii_frame}\n\033[K\n{progress_info} {progress_bar}"

            frame_lines = ascii_frame.count("\n") + 1
            used = frame_lines + 2
            fill = max(0, term_height - used)
            padding = ("\n" + " " * term_width) * fill if fill > 0 else ""
            out.write("\033[r\033[H" + output + "\033[K" + padding + "\033[0m")
            out.flush()

            if keys.quit_pressed():
                break

            delay = (start + idx * frame_interval) - time.monotonic()
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        keys.close()
        if stop_audio:
            stop_audio()
        out.write("\033[0m\033[?25h\033[?1049l")
        out.flush()
        if _playback_logs:
            try:
                sys.stderr.write("\n----- 播放日志 -----\n")
                for _ln in _playback_logs:
                    sys.stderr.write(_ln + "\n")
                sys.stderr.write("-------------------\n")
                sys.stderr.flush()
            except Exception:
                pass

    return True