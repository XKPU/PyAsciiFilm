import os

from utils import _log


def _system_select_video():
    try:
        import tkinter as tk
        from tkinter import filedialog
        _log("打开系统文件选择对话框")
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[("视频文件", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v"),
                        ("所有文件", "*.*")],
        )
        root.destroy()
        return path or None
    except Exception:
        _log("系统文件对话框不可用，回退终端输入")
        return None


def select_video_path():
    path = _system_select_video()
    if path:
        return path
    from ui import _input_select_video
    return _input_select_video()
