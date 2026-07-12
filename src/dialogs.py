# 视频文件选择
import os
import subprocess
import sys
import traceback

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from utils import _log, _log_error
from ascii_art import (
    _read_config, _write_config_value,
    LAST_VIDEO_DIR_KEY, LAST_EXPORT_DIR_KEY,
)


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


# 在独立子进程中弹出原生文件对话框的脚本。
# 单独进程可避免 tkinter 与 textual 终端控制互相干扰，
# 对话框作为独立 OS 窗口必然置顶弹出。
_DIALOG_SCRIPT = r'''
import os
import sys
from tkinter import Tk, filedialog

VIDEO_EXTS = [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
              ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob"]


def _split(initial):
    initialdir = None
    initialfile = None
    if initial and os.path.isfile(initial):
        initialdir = os.path.dirname(initial)
        initialfile = os.path.basename(initial)
    elif initial and os.path.isdir(initial):
        initialdir = initial
    return initialdir, initialfile


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    initial = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else ""
    def_ext = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else ""
    default_dir = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else ""

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()

    initialdir, initialfile = _split(initial)
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
        ext_pat = " ".join("*" + e for e in VIDEO_EXTS)
        filetypes = [("视频文件", ext_pat), ("所有文件", "*.*")]
        path = filedialog.askopenfilename(
            title="请选择视频",
            initialdir=initialdir or os.getcwd(),
            initialfile=initialfile or "",
            filetypes=filetypes,
        )

    print(path or "", end="")
    root.destroy()


main()
'''


def _run_dialog(mode, initial=None, def_ext=None, default_dir=None):
    # 在子进程中弹出原生对话框，返回所选路径或 None（取消/失败）
    args = [sys.executable, "-c", _DIALOG_SCRIPT, mode]
    args.append(initial or "")
    args.append(def_ext or "")
    args.append(default_dir or "")
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
        )
        out = (proc.stdout or "").strip()
        if proc.returncode != 0 or not out:
            if proc.stderr and proc.stderr.strip():
                _log_error(f"对话框子进程错误: {proc.stderr.strip()}")
            return None
        return out
    except Exception as e:
        _log_error(f"对话框子进程异常 {e}\n{traceback.format_exc()}")
        return None


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
