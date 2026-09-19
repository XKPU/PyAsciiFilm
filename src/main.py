# 程序入口
import os
import sys
import threading
import asyncio
import traceback

from utils.helpers import _clear_log, _log, _log_error, _app_dir

_clear_log()
_LOG_FILE = os.path.join(_app_dir(), "pyasciifilm.log")
_log(f"==== PyAsciiFilm 启动 ==== | Python {sys.version.split()[0]} | 平台 {sys.platform}")


_ORIG_EXCEPTHOOK = sys.excepthook


def _global_excepthook(exc_type, exc_value, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _log_error(f"未捕获异常:\n{msg}")
    if _ORIG_EXCEPTHOOK is not None and _ORIG_EXCEPTHOOK != _global_excepthook:
        _ORIG_EXCEPTHOOK(exc_type, exc_value, exc_tb)


sys.excepthook = _global_excepthook

_ORIG_THREAD_EXCEPTHOOK = threading.excepthook


def _thread_excepthook(args):
    msg = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    _log_error(f"线程未捕获异常:\n{msg}")
    if _ORIG_THREAD_EXCEPTHOOK is not None and _ORIG_THREAD_EXCEPTHOOK != _thread_excepthook:
        _ORIG_THREAD_EXCEPTHOOK(args)


threading.excepthook = _thread_excepthook


def _asyncio_excepthook(loop, context):
    msg = context.get("message", "未知 asyncio 错误")
    exc = context.get("exception")
    if exc:
        msg += f"\n{''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))}"
    _log_error(f"asyncio 异常: {msg}")


def do_play(video_path, use_color, with_audio=True,
            target_fps=None, decode_args=None, ffmpeg_usage=None):
    from core.main import reload_charset
    reload_charset()
    from playback.main import play_video
    _log(f"开始播放: {video_path} | 彩色={use_color} 音频={with_audio}"
         f" | 目标帧率={target_fps} | 解码={decode_args} | CPU占用={ffmpeg_usage}")
    try:
        play_video(video_path, use_color=use_color, with_audio=with_audio,
                   target_fps=target_fps, decode_args=decode_args,
                   ffmpeg_usage=ffmpeg_usage)
    except Exception as e:
        _log_error(f"播放异常: {e}")
        print(f"\n[错误] 播放过程中发生异常: {e}")
    finally:
        _log(f"播放结束: {video_path}")


def _startup_notice(text):
    # 在进入 Textual 全屏前的黑屏期，给终端一个可见提示。Textual 启动要接管整个终端，在此之前有数百毫秒到数秒的 "什么都没显示"的空窗
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def _startup_clear():
    # 清掉启动提示，交还干净的屏幕给 Textual
    try:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
    except Exception:
        pass


def main():
    try:
        asyncio.get_running_loop().set_exception_handler(_asyncio_excepthook)
    except RuntimeError:
        pass

    _startup_notice("正在初始化 PyAsciiFilm，请稍候…")

    from ui.main import MenuApp

    while True:
        try:
            result = MenuApp().run()
        except Exception as e:
            _log_error(f"Textual 应用崩溃: {e}\n{traceback.format_exc()}")
            print(f"\n[错误] 程序异常退出: {e}", file=sys.stderr)
            return

        if result is None:
            _log_error("程序异常终止（未获得退出结果）")
            return

        if isinstance(result, str):
            if result == "quit":
                _log("用户退出")
                return
            _log_error(f"程序异常终止（未知退出码: {result!r})")
            return

        if isinstance(result, tuple) and result[0] == "play":
            _, use_color, video_path = result[0], result[1], result[2]
            target_fps = result[3] if len(result) > 3 else None
            decode_args = result[4] if len(result) > 4 else None
            ffmpeg_usage = result[5] if len(result) > 5 else None
            if not video_path:
                _log("未选择视频，返回菜单")
                continue
            _log(f"已选择视频: {video_path}")
            do_play(video_path, use_color=use_color, with_audio=True,
                    target_fps=target_fps, decode_args=decode_args,
                    ffmpeg_usage=ffmpeg_usage)
            continue

        return


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log_error(f"致命异常: {e}\n{traceback.format_exc()}")
        print(f"[致命错误] {e}\n详见日志: {_LOG_FILE}", file=sys.stderr)
        traceback.print_exc()