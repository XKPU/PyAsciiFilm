# 程序入口
import os
import sys
import threading
import traceback

from utils import _probe_hw_accel, _clear_log, _log, _log_error, _app_dir

# 清空并初始化日志文件
_clear_log()
_LOG_FILE = os.path.join(_app_dir(), "pyasciifilm.log")
_log(f"==== PyAsciiFilm 启动 ==== | Python {sys.version.split()[0]} | 平台 {sys.platform}")

threading.Thread(target=_probe_hw_accel, daemon=True).start()


def do_play(video_path, use_color, with_audio=True):
    # 退出 textual 后在原始终端播放
    from playback import play_video
    _log(f"开始播放: {video_path} | 彩色={use_color} 音频={with_audio}")
    try:
        play_video(video_path, use_color=use_color, with_audio=with_audio)
    except Exception as e:
        _log_error(f"播放异常: {e}")
        print(f"\n[错误] 播放过程中发生异常: {e}")
    finally:
        _log(f"播放结束: {video_path}")


def main():
    # 程序入口
    from ui import MenuApp

    while True:
        result = MenuApp().run()

        if result == "quit" or result is None:
            _log("用户退出")
            return

        if isinstance(result, tuple) and result[0] == "play":
            _, use_color, video_path = result
            if not video_path:
                _log("未选择视频，返回菜单")
                continue
            _log(f"已选择视频: {video_path}")
            do_play(video_path, use_color=use_color, with_audio=True)
            continue

        return


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 捕获致命异常写入日志与控制台，避免“无任何信息直接退出”
        _log_error(f"致命异常: {e}\n{traceback.format_exc()}")
        print(f"[致命错误] {e}\n详见日志: {_LOG_FILE}", file=sys.stderr)
        traceback.print_exc()
