# 程序入口
import logging
import sys
import threading

from utils import _probe_hw_accel, _clear_log, _write_log_file, _log_path, _set_debug
from dialogs import select_video_path

# 命令行参数
if "--debug" in sys.argv:
    _set_debug(True)
    _clear_log()
    _write_log_file("==== PyAsciiFilm 启动 ====")
    _write_log_file(f"Python: {sys.version.split()[0]} | 平台: {sys.platform}")
    _write_log_file(f"日志文件: {_log_path()}")

# 后台预热硬件加速探测缓存
threading.Thread(target=_probe_hw_accel, daemon=True).start()


def do_play(video_path, use_color, with_audio=True):
    # 退出 textual 后在原始终端播放
    from playback import play_video
    _write_log_file(f"开始播放: {video_path} | 彩色={use_color} 音频={with_audio}")
    try:
        play_video(video_path, use_color=use_color, with_audio=with_audio)
    except Exception as e:
        _write_log_file(f"播放异常: {e}", level=logging.ERROR)
        print(f"\n[错误] 播放过程中发生异常: {e}")
    finally:
        _write_log_file(f"播放结束: {video_path}")
        print("\n已返回菜单")


def main():
    # 程序入口
    video_path = select_video_path()
    if not video_path:
        _write_log_file("未选择视频，退出", level=logging.WARNING)
        return
    _write_log_file(f"已选择视频: {video_path}")

    from ui import MenuApp

    while True:
        result = MenuApp(video_path).run()

        if result == "quit" or result is None:
            _write_log_file("用户退出")
            return

        if isinstance(result, tuple) and result[0] == "play":
            do_play(video_path, use_color=result[1], with_audio=True)
            continue

        if isinstance(result, tuple) and result[0] == "reselect":
            new_path = select_video_path()
            if new_path:
                video_path = new_path
                _write_log_file(f"重新选择视频: {video_path}")
            continue

        return


if __name__ == "__main__":
    main()
