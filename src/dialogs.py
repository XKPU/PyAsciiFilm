# 视频文件选择
import os
import sys

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Input

from utils import _log, _log_error
from ascii_art import (
    _read_config, _write_config_value,
    LAST_VIDEO_DIR_KEY, LAST_EXPORT_DIR_KEY,
)


def _gui_available():
    # 是否可用图形文件对话框（tkinter + 显示服务），否则回退文本输入
    if os.environ.get("PYASCIIFILM_NO_GUI"):
        return False
    if sys.platform == "win32":
        try:
            import tkinter  # noqa: F401
            return True
        except Exception:
            return False
    # 类 Unix 需要 X11 / Wayland 显示服务
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False

_VIDEO_EXTS = [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
               ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob"]


def _load_last_dir(key):
    # 上次选择目录（无则空串）
    try:
        return _read_config().get(key) or ""
    except Exception:
        return ""


def _save_last_dir(key, path):
    # 记录所选目录到配置
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
    # 弹原生对话框，返回路径或 None
    if not _gui_available():
        return None
    from tkinter import Tk, filedialog
    try:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
    except Exception as e:
        _log_error(f"无法初始化图形对话框（已回退文本输入）: {e}")
        return None
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
    # 选择视频，返回路径或 None
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
    # 选择导出输出路径，返回路径或 None
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
    #path { width: 60; }
    """

    def __init__(self, initial=None, on_done=None):
        super().__init__()
        self._initial = initial
        self._on_done = on_done
        self._use_text = not _gui_available()

    def compose(self) -> ComposeResult:
        if self._use_text:
            yield Static("当前环境无图形文件对话框，请直接输入视频路径：", id="msg")
            yield Input(value=self._initial or "", id="path",
                        placeholder="输入视频路径后回车，Esc 取消")
        else:
            yield Static("请选择视频…", id="msg")

    def on_mount(self) -> None:
        if self._use_text:
            self.query_one("#path", Input).focus()
        else:
            self.set_timer(0.25, self._pick)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if not self._use_text:
            return
        self._finish(event.value.strip() or None)

    def on_key(self, event) -> None:
        if self._use_text and event.key == "escape":
            self._finish(None)

    def _finish(self, path):
        try:
            if self._on_done:
                self._on_done(path)
        except Exception:
            pass

    def _pick(self):
        path = None
        try:
            path = select_video_path(self._initial)
        finally:
            if self._on_done:
                self._on_done(path)
