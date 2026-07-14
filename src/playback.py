# ASCII 帧生成与终端播放
import os
import sys
import time
import shutil
import cv2

from ascii_art import (
    generate_grayscale_frame,
    generate_colored_frame,
)
from audio import start_audio

from decoder import FrameReader
from utils import _log, _log_error


# ---------------------------------------------------------------------------
# 帧 -> 字符画
# ---------------------------------------------------------------------------
def _frame_to_terminal_text(frame, width, use_color):
    # 帧 -> 终端文本
    aspect = frame.shape[0] / frame.shape[1]
    new_height = max(1, int(aspect * width * 0.5))
    resized_bgr = cv2.resize(frame, (width, new_height))
    if use_color:
        pixels = cv2.cvtColor(resized_bgr, cv2.COLOR_BGR2RGB)
        lum = cv2.cvtColor(resized_bgr, cv2.COLOR_BGR2GRAY)
        return generate_colored_frame(pixels, lum)
    gray = cv2.cvtColor(resized_bgr, cv2.COLOR_BGR2GRAY)
    return generate_grayscale_frame(gray)


# ---------------------------------------------------------------------------
# 原始终端播放
# ---------------------------------------------------------------------------
def _enable_windows_ansi():
    # Windows 控制台启用 ANSI 转义序列
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


class _KeyReader:
    # 非阻塞读取退出键（q / Esc）

    def __init__(self):
        try:
            import msvcrt
            self._msvcrt = msvcrt
        except ImportError:
            self._msvcrt = None
        self._posix = self._setup_posix() if self._msvcrt is None else None

    def _setup_posix(self):
        # 类 Unix：播放期间保持 cbreak（逐键即时送达、无回显，保留 Ctrl+C）
        import sys
        if not sys.stdin.isatty():
            return None
        try:
            import termios
            import tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            return fd, old
        except Exception:
            return None

    def quit_pressed(self):
        if self._msvcrt is not None:
            pressed = False
            while self._msvcrt.kbhit():
                ch = self._msvcrt.getch()
                if ch in (b"q", b"Q", b"\x1b"):
                    pressed = True
            return pressed
        if not self._posix:
            return False
        import select
        fd, _old = self._posix
        try:
            r, _, _ = select.select([fd], [], [], 0)
            if not r:
                return False
            ch = os.read(fd, 1)
            return ch in (b"q", b"Q", b"\x1b")
        except Exception:
            return False

    def close(self):
        # 播放结束恢复终端原始模式
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
    # 获取终端尺寸
    cols, rows = shutil.get_terminal_size((100, 30))
    return cols, rows


def _calculate_optimal_width(term_width, term_height, video_width, video_height):
    # 最佳字符画宽度
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
    # 进度条
    if total <= 0:
        return "[未知进度]"
    progress = max(0.0, min(1.0, current / total))
    filled_width = int(width * progress)
    bar = "█" * filled_width + "░" * (width - filled_width)
    percent = progress * 100
    return f"[{bar}] {percent:.1f}%"


def play_video(video_path, use_color=False, with_audio=True):
    # 原始终端 ANSI 播放视频
    _enable_windows_ansi()
    _log(f"播放初始化: {video_path} | 彩色={use_color} 音频={with_audio}")
    out = sys.stdout

    # 播放时屏幕被视频占用，ffmpeg 日志先缓冲
    _playback_logs = []

    def _buf_log(msg):
        try:
            _playback_logs.append(msg)
        except Exception:
            pass
        _log(msg)

    try:
        cap = FrameReader(video_path, log=_buf_log)
    except Exception as e:
        _log_error(f"无法打开视频文件（{e}）")
        print(f"错误: 无法打开视频文件（{e}）")
        return False

    fps = cap.fps or 30.0
    frame_interval = 1.0 / max(fps, 1.0)
    video_width = int(cap.width)
    video_height = int(cap.height)
    total_frames = int(cap.frame_count)
    total_duration = cap.duration if cap.duration and cap.duration > 0 else (total_frames / fps if fps else 0.0)

    audio = start_audio(video_path, log=_buf_log) if with_audio else None
    stop_audio = audio[0] if audio else None
    get_audio_start = audio[1] if audio else None
    keys = _KeyReader()

    out.write("\033[2J\033[?25l")
    out.flush()

    term_width, term_height = _get_terminal_size()
    ascii_width = _calculate_optimal_width(term_width, term_height, video_width, video_height)
    last_width = ascii_width

    # 以"音频实际可闻时刻"为视频时钟基准
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
                w = _calculate_optimal_width(term_width, term_height, video_width, video_height)
                if w != last_width:
                    out.write("\033[2J\033[H")
                    last_width = w
                ascii_width = w

            ret, frame = cap.read()
            if not ret:
                break

            ascii_frame = _frame_to_terminal_text(frame, ascii_width, use_color)
            idx += 1

            color_mode_text = "全彩" if use_color else "灰度"
            performance_text = f" | 分辨率: {ascii_width}x{int(ascii_width * (video_height / video_width) * 0.5)}"
            progress_info = (
                f"平均帧率: {idx / max(time.monotonic() - start, 1e-6):.1f} FPS"
                f" | 原视频帧: {idx}/{total_frames} | {color_mode_text}{performance_text}"
            )
            elapsed = time.monotonic() - start
            if total_duration > 0:
                progress_bar = _create_progress_bar(elapsed, total_duration, max(10, ascii_width // 2))
            else:
                progress_bar = _create_progress_bar(idx, total_frames, max(10, ascii_width // 2))

            output = f"{ascii_frame}\n\n{progress_info} {progress_bar}"

            out.write("\033[H" + output + "\033[0m")
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
        out.write("\033[0m\033[?25h\033[2J\033[H")
        out.flush()
        # 播放结束后打印缓冲日志
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
