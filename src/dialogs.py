# 视频文件选择
import os
import traceback

import tkinter as tk
from tkinter import filedialog

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from utils import _log, _log_error


_VIDEO_EXTS = (".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v",
               ".mpg", ".mpeg", ".ts", ".m2ts", ".vob")


def select_video_path(initial=None):
    # 使用 tkinter 原生文件对话框选择视频，返回路径或 None（取消/失败）
    _log(f"视频选择：打开 tkinter 对话框，initial = {initial!r}")
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if initial and os.path.isfile(initial):
            initialdir = os.path.dirname(initial)
            initialfile = os.path.basename(initial)
        elif initial and os.path.isdir(initial):
            initialdir = initial
            initialfile = None
        else:
            initialdir = os.path.expanduser("~")
            initialfile = None
        ext_pat = " ".join(f"*{e}" for e in _VIDEO_EXTS)
        filetypes = [("视频文件", ext_pat), ("所有文件", "*.*")]
        try:
            path = filedialog.askopenfilename(
                title="请选择视频",
                initialdir=initialdir,
                initialfile=initialfile or "",
                filetypes=filetypes,
            )
        finally:
            root.destroy()
        result = path or None
        _log(f"视频选择：返回 {result!r}")
        return result
    except Exception as e:
        _log_error(f"视频选择：tkinter 对话框异常 {e}\n{traceback.format_exc()}")
        return None


class SelectingScreen(Screen):
    CSS = """
    Screen { align: center middle; }
    #msg { width: auto; height: auto; text-style: bold; }
    """

    def __init__(self, initial=None, on_done=None):
        super().__init__()
        self._initial = initial
        self._on_done = on_done

    def compose(self) -> ComposeResult:
        yield Static("请选择视频…", id="msg")

    def on_mount(self) -> None:
        self.set_timer(0.25, self._pick)

    def _pick(self):
        path = None
        try:
            path = select_video_path(self._initial)
        finally:
            if self._on_done:
                self._on_done(path)
