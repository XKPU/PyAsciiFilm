# 字符画帧生成与终端播放
import os
import sys
import time
import shutil

import numpy as np
from PIL import Image

from audio.main import start_audio
from core.main import generate_colored_frame, generate_grayscale_frame
from decoder.main import FrameReader
from utils.helpers import _log, _log_error, _probe_video_meta, clean_fps


_playback_logs = []


def _frame_to_terminal_text(frame, width, height, use_color):
    if frame is None or frame.shape[0] == 0 or frame.shape[1] == 0:
        return ""
    width = max(1, int(width))
    height = max(1, int(height))
    # 解码时已让 ffmpeg 缩放到目标尺寸，正常情况无需再缩放；尺寸不符（如终端刚改变）时才用 PIL 兜底
    if frame.shape[1] != width or frame.shape[0] != height:
        img = Image.fromarray(frame).resize((width, height), Image.BILINEAR)
        pixels = np.asarray(img, dtype=np.uint8)
    else:
        pixels = frame
        img = None
    if use_color:
        lum = (pixels[:, :, 0].astype(np.uint32) * 299
               + pixels[:, :, 1].astype(np.uint32) * 587
               + pixels[:, :, 2].astype(np.uint32) * 114
               + 500) // 1000
        lum = lum.astype(np.uint8)
        frame_text = generate_colored_frame(pixels, lum)
    else:
        if img is None:
            img = Image.fromarray(frame)
        gray = np.asarray(img.convert("L"), dtype=np.uint8)
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
    # 非阻塞键盘读取（三平台）

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


def _show_startup_notice(out, text):
    # 在首帧出现前，居中显示一行缓冲提示，避免黑屏等待。音频要等 ffmpeg 解出并填满缓冲才出声（实测几十到几百毫秒，最坏会等满 3 秒超时），此期间终端本来是空的
    try:
        term_width, term_height = _get_terminal_size()
        pad = max(0, (term_height // 2) - 1)
        line = text.center(max(0, term_width))
        out.write("\033[2J\033[H" + "\n" * pad + line)
        out.write(f"\033[{term_height};1H")
        out.flush()
    except Exception:
        pass


_OWNS_SCREEN = False
# main() 全程持有备用屏幕时置 True，播放就不再自己进出屏幕
_IN_ALT_SCREEN = False


def set_alt_screen(active):
    # 由 main() 告知当前是否已在备用屏幕中
    global _IN_ALT_SCREEN
    _IN_ALT_SCREEN = bool(active)


def _leave_screen(out):
    # 只在本次播放自己进入了备用屏幕时才离开；由 main() 全程持有的屏幕不动它
    global _OWNS_SCREEN
    if not _OWNS_SCREEN:
        return
    _OWNS_SCREEN = False
    # 离开前先清屏，避免终端把那 1 帧旧画面重绘出来（看起来就是闪一下）
    try:
        out.write("\033[2J\033[H\033[0m\033[?25h\033[?1049l")
        out.flush()
    except Exception:
        pass


def play_video(video_path, use_color=False, with_audio=True,
               target_fps=None, decode_args=None, ffmpeg_usage=None):
    global _OWNS_SCREEN
    _enable_windows_ansi()
    out = sys.stdout
    # 已在备用屏幕里（由 main() 全程持有）就不用再进，避免多余的进出导致闪动
    if not _IN_ALT_SCREEN:
        out.write("\033[?1049h")
        _OWNS_SCREEN = True
    out.write("\033[2J\033[?25l")
    out.flush()
    _show_startup_notice(out, "正在缓冲…")
    _log(f"播放初始化: {video_path} | 彩色={use_color} 音频={with_audio}"
         f" | 目标帧率={target_fps} | 解码={decode_args} | CPU占用={ffmpeg_usage}")

    _playback_logs = []

    def _buf_log(msg):
        try:
            _playback_logs.append(msg)
        except Exception:
            pass
        _log(msg)

    # 先探测元数据（不建管道），据此算好目标字符宽度，再把该宽度作为解码尺寸交给 ffmpeg 缩放
    meta = _probe_video_meta(video_path) or {}
    video_width = int(meta.get("width") or 0)
    video_height = int(meta.get("height") or 0)
    if video_width <= 0 or video_height <= 0:
        _leave_screen(out)
        print("错误: 无法读取视频尺寸")
        return False
    fps = clean_fps(meta.get("fps")) or 30.0
    src_fps = fps
    if target_fps and target_fps > 0:
        fps = min(fps, target_fps)
    frame_interval = 1.0 / max(fps, 1.0)
    # 只有真正降帧时才让解码端按目标帧率抽帧；play_fps 为 0 表示不干预
    play_fps = fps if fps < src_fps - 1e-6 else 0.0
    total_frames = int(meta.get("frame_count") or 0)
    total_duration = meta.get("duration") or 0.0
    if total_duration <= 0:
        total_duration = total_frames / fps if fps else 0.0

    term_width, term_height = _get_terminal_size()
    ascii_width = _calculate_optimal_width(term_width, term_height,
                                           video_width, video_height)
    # 交给 ffmpeg 缩放到字符格对应的像素尺寸（宽=字符列数，高=字符行数）
    decode_w = max(1, ascii_width)
    decode_h = max(1, int(ascii_width * (video_height / video_width) * 0.5))

    try:
        cap = FrameReader(video_path, log=_buf_log, force_size=(decode_w, decode_h),
                          metadata=(video_width, video_height, fps, total_frames),
                          decode_args=decode_args, ffmpeg_usage=ffmpeg_usage,
                          play_fps=play_fps)
    except Exception as e:
        _log_error(f"无法打开视频文件（{e}）")
        _leave_screen(out)
        print(f"错误: 无法打开视频文件（{e}）")
        return False

    audio = start_audio(video_path, log=_buf_log) if with_audio else None
    stop_audio = audio[0] if audio else None
    get_audio_start = audio[1] if audio else None
    no_audio = audio[2] if audio and len(audio) > 2 else None
    keys = _KeyReader()

    last_width = ascii_width

    start = time.monotonic()
    if get_audio_start is not None:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            astart = get_audio_start()
            if astart is not None:
                # 等到音频真正出声，start 取此刻，画面与进度条同时起算
                gap = astart - time.monotonic()
                if gap > 0:
                    time.sleep(gap)
                start = time.monotonic()
                break
            # 无音轨/解码已结束：不必再等，立刻开播
            if no_audio is not None and no_audio():
                break
            time.sleep(0.005)

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

            ascii_height = max(1, int(ascii_width * (video_height / video_width) * 0.5))
            ascii_frame = _frame_to_terminal_text(frame, ascii_width,
                                                   ascii_height, use_color)
            idx += 1

            # 首帧：全屏清一次，抹掉"正在缓冲"提示的残留
            if idx == 1:
                out.write("\033[2J")

            color_mode_text = "全彩" if use_color else "灰度"
            estimate_h = int(ascii_width * (video_height / video_width) * 0.5)
            if play_fps and total_duration > 0:
                shown_total = max(1, int(round(total_duration * play_fps)))
            else:
                shown_total = total_frames
            progress_info = (
                f"平均帧率: {idx / max(time.monotonic() - start, 1e-6):.1f} FPS"
                f" | 帧: {idx}/{shown_total} | {color_mode_text}"
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

            # 按绝对时间轴对齐：第 idx 帧应显示在 start + idx*interval
            delay = (start + idx * frame_interval) - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -frame_interval:
                behind = int(-delay / frame_interval)
                if behind > 0 and cap.skip_frames(behind):
                    idx += behind
                    # start 不变：下一帧的目标时刻仍按同一条时间轴计算，相当于把"错过的帧"从时间轴上抹掉，误差不再累积
                    continue
                # 流已结束或无法跳帧：退化为正常渲染剩余帧
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        keys.close()
        if stop_audio:
            stop_audio()
        _leave_screen(out)
        # 日志写入日志文件；备用屏幕已退出，写 stderr 会让正常终端闪出一片日志
        if _playback_logs:
            try:
                _log("播放结束，本次日志:\n" + "\n".join(_playback_logs))
            except Exception:
                pass

    return True