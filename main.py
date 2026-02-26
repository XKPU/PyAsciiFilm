from tkinter import filedialog
import subprocess
import os
from player import play_video

# 选择视频文件
def select_video_file():
    try:
        import tkinter as tk
    except ImportError:
        return None

    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title="选择视频文件",
        filetypes=[("视频文件", "*.mp4 *.avi *.mkv *.mov *.wmv"), ("所有文件", "*.*")]
    )
    root.destroy()
    return file_path

# 是否播放音频
def ask_audio_play():
    while True:
        choice = input("是否播放音频(回车默认播放，输入n不播放): ").strip().lower()
        if choice == "" or choice == "y":
            return True
        elif choice == "n":
            return False
        else:
            print("无效输入，请输入 y 或 n")

# 询问显示模式
def ask_color_mode():
    while True:
        choice = input("是否使用全彩播放(回车默认灰度，输入y全彩): ").strip()
        if choice == "" or choice == "n":
            return False
        elif choice == "y":
            return True
        else:
            print("无效输入，请输入 y 或 n")

# 音频播放
def play_audio(video_path):
    try:
        ffplay_path = os.path.join(os.path.dirname(__file__), "ffplay.exe")

        if not os.path.exists(ffplay_path):
            print("找不到ffplay.exe，将无音频播放")
            return None

        process = subprocess.Popen([
            ffplay_path,
            "-nodisp",
            "-autoexit",
            "-vn",
            video_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return process
    except Exception as e:
        print(f"无法启动音频播放: {str(e)}")
        return None

# 程序入口
def main():
    video_path = select_video_file()
    if not video_path:
        print("未选择视频文件，程序退出")
        return

    print("=== PyAsciiFilm 视频播放器 ===")
    print(f"已选择视频: {video_path}")

    play_audio_flag = ask_audio_play()
    use_color = ask_color_mode()

    audio_process = None
    try:
        if play_audio_flag:
            audio_process = play_audio(video_path)

        play_video(video_path, use_color)

    except Exception as e:
        print(f"\n[错误] 播放过程中发生异常: {str(e)}")
    finally:
        if audio_process and audio_process.poll() is None:
            audio_process.terminate()
            try:
                audio_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                audio_process.kill()
        print("\n程序已退出")


if __name__ == "__main__":
    main()