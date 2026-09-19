# 视频文件选择
import os
import sys

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Input

from utils.helpers import (
    _log,
    _write_config_value,
    LAST_VIDEO_DIR_KEY,
)


def _gui_available():
    if os.environ.get("PYASCIIFILM_NO_GUI"):
        return False
    if sys.platform == "win32":
        try:
            import tkinter  # noqa: F401
            return True
        except Exception:
            return False
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False

def _save_last_dir(key, path):
    try:
        if path and os.path.isdir(path):
            _write_config_value(key, path)
    except Exception:
        pass


class SelectingScreen(Screen):
    CSS = """
    Screen { align: center middle; }
    #msg { width: auto; height: auto; text-style: bold; }
    #path { width: 60; }
    #hint { color: $text-muted; text-style: bold; height: 1; margin: 1 0 0 0; }
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
            yield Static("Enter 确认路径 | Esc 取消", id="hint")
        else:
            yield Static("请选择视频…", id="msg")

    def on_mount(self) -> None:
        if self._use_text:
            self.query_one("#path", Input).focus()
        else:
            self.call_after_refresh(self._pick)

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
        # 打开文件浏览器（Textual 原生）
        from .filebrowser.main import VideoFileBrowser
        browser = VideoFileBrowser(initial=self._initial)

        def _on_browser_result(path: str | None) -> None:
            if path:
                _save_last_dir(LAST_VIDEO_DIR_KEY, os.path.dirname(path))
                _log(f"视频选择（文件浏览器）：返回 {path!r}")
            else:
                _log("视频选择（文件浏览器）：已取消")
            self._finish(path)

        self.app.push_screen(browser, callback=_on_browser_result)
