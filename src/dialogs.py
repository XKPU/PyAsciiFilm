import os


def _system_select_video():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[("视频文件", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v"),
                       ("所有文件", "*.*")],
        )
        root.destroy()
        return path or None
    except Exception as e:
        from utils import _write_log_file
        import logging
        _write_log_file(f"回退终端: {e}", level=logging.WARNING)
        return None


def select_video_path():
    path = _system_select_video()
    if path:
        return path
    from ui import _input_select_video
    return _input_select_video()
