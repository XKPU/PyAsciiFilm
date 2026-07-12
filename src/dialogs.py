# 视频文件选择
import os

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from utils import _log, _log_error
from ascii_art import (
    _read_config, _write_config_value,
    LAST_VIDEO_DIR_KEY, LAST_EXPORT_DIR_KEY,
)

_VIDEO_EXTS = [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
               ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob"]


def _load_last_dir(key):
    # 读取配置中记录的上次选择目录（不存在返回空串）
    try:
        return _read_config().get(key) or ""
    except Exception:
        return ""


def _save_last_dir(key, path):
    # 将所选文件所在目录写入配置
    try:
        if path and os.path.isdir(path):
            _write_config_value(key, path)
    except Exception:
        pass


def _split_initial(initial):
    # 拆分初始路径为目录与文件名
    initialdir = None
    initialfile = None
    if initial and os.path.isfile(initial):
        initialdir = os.path.dirname(initial)
        initialfile = os.path.basename(initial)
    elif initial and os.path.isdir(initial):
        initialdir = initial
    return initialdir, initialfile


def _run_dialog(mode, initial=None, def_ext=None, default_dir=None):
    # 弹出 tkinter 原生对话框，返回所选路径或 None（取消/失败）
    from tkinter import Tk, filedialog
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()
    try:
        initialdir, initialfile = _split_initial(initial)
        if not initialdir and default_dir and os.path.isdir(default_dir):
            initialdir = default_dir
        if mode == "save":
            se = def_ext if def_ext.startswith(".") else ("." + def_ext if def_ext else ".mp4")
            filetypes = [("视频文件", "*" + se), ("所有文件", "*.*")]
            path = filedialog.asksaveasfilename(
                title="选择导出文件路径",
                initialdir=initialdir or os.getcwd(),
                initialfile=initialfile or "",
                defaultextension=se,
                filetypes=filetypes,
            )
        else:
            ext_pat = " ".join("*" + e for e in _VIDEO_EXTS)
            filetypes = [("视频文件", ext_pat), ("所有文件", "*.*")]
            path = filedialog.askopenfilename(
                title="请选择视频",
                initialdir=initialdir or os.getcwd(),
                initialfile=initialfile or "",
                filetypes=filetypes,
            )
        return path or None
    except Exception as e:
        _log_error(f"对话框异常: {e}")
        return None
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def select_video_path(initial=None):
    # 使用原生文件对话框选择视频，返回路径或 None（取消/失败）
    _log(f"视频选择：打开对话框，initial = {initial!r}")
    default_dir = _load_last_dir(LAST_VIDEO_DIR_KEY) or os.getcwd()
    result = _run_dialog("open", initial, default_dir=default_dir)
    if result:
        _save_last_dir(LAST_VIDEO_DIR_KEY, os.path.dirname(result))
        _log(f"视频选择：返回 {result!r}")
    else:
        _log("视频选择：已取消或无结果")
    return result


def select_output_path(initial=None, def_ext=None):
    # 使用原生保存对话框选择导出输出路径，返回路径或 None（取消/失败）
    _log(f"导出输出选择：打开对话框，initial = {initial!r}, def_ext = {def_ext!r}")
    default_dir = (_load_last_dir(LAST_EXPORT_DIR_KEY)
                   or _load_last_dir(LAST_VIDEO_DIR_KEY)
                   or os.getcwd())
    result = _run_dialog("save", initial, def_ext, default_dir=default_dir)
    if result:
        _save_last_dir(LAST_EXPORT_DIR_KEY, os.path.dirname(result))
        _log(f"导出输出选择：返回 {result!r}")
    else:
        _log("导出输出选择：已取消或无结果")
    return result


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
