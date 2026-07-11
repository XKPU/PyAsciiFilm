# 程序入口
import sys
import threading

from utils import _probe_hw_accel, _clear_log, _log, _log_error
from dialogs import select_video_path

# 清空并初始化日志文件
_clear_log()
_log(f"==== PyAsciiFilm 启动 ==== | Python {sys.version.split()[0]} | 平台 {sys.platform}")

# 后台预热硬件加速探测缓存
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
        print("\n已返回菜单")


def main():
    # 程序入口
    video_path = select_video_path()
    if not video_path:
        _log("未选择视频，退出")
        return

    _log(f"已选择视频: {video_path}")

    from ui import MenuApp

    while True:
        result = MenuApp(video_path).run()

        if result == "quit" or result is None:
            _log("用户退出")
            return

        if isinstance(result, tuple) and result[0] == "play":
            do_play(video_path, use_color=result[1], with_audio=True)
            continue

        if isinstance(result, tuple) and result[0] == "reselect":
            new_path = select_video_path()
            if new_path:
                video_path = new_path
                _log(f"重新选择视频: {video_path}")
            continue

        return


if __name__ == "__main__":
    main()
