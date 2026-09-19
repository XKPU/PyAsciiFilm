# TUI 主界面
import threading

from textual.app import App, ComposeResult
from textual.widgets import (
    ListView, ListItem, Label, Header, Footer, Static,
)

from utils.helpers import start_detect, _detect_status, _log, wait_detect

from .dialogs import SelectingScreen
from .widgets import KeyBar, safe_notify
from .screens.play_settings import PlaySettingsScreen
from .screens.export_settings import ExportSettingsScreen
from . import _shared


class MenuApp(App):

    CSS = """
    Screen { align: center middle; }
    ListView { width: 40; height: auto; border: round $accent; padding: 1 2; }
    ListItem { padding: 0 1; }
    #detect-status {
        width: 40;
        height: 1;
        text-align: center;
        color: $text-muted;
    }
    KeyBar {
        height: 1;
        background: $primary 10%;
        color: $text;
        padding: 0 1;
        text-style: bold;
        dock: bottom;
    }
    """

    BINDINGS = [("ctrl+q", "quit", "退出")]

    def on_mount(self) -> None:
        self.title = "PyAsciiFilm"
        self.query_one(ListView).focus()
        self._update_keybar()
        self._start_backend_detect()
        self._refresh_detect_status()
        self.set_interval(0.25, self._refresh_detect_status)

    def _update_keybar(self):
        try:
            kb = self.query_one(KeyBar)
            kb.set_hint("↑↓ 选择 | Enter 确认 | Ctrl+Q 退出")
        except Exception:
            pass

    def _start_backend_detect(self):
        # 启动解码/编码两组检测
        def _publish():
            res = wait_detect("decode")
            try:
                if res:
                    _shared._cached_decode_backends = res
            except Exception:
                pass

        start_detect()
        threading.Thread(target=_publish, name="detect-publish",
                         daemon=True).start()

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListView(
            ListItem(Label("播放视频"), id="play"),
            ListItem(Label("导出视频"), id="export"),
            ListItem(Label("退出程序"), id="quit"),
        )
        yield Static("", id="detect-status")
        yield Footer()
        yield KeyBar()

    def _refresh_detect_status(self):
        # 显示"检测中"，检测完成后自动隐藏
        try:
            w = self.query_one("#detect-status", Static)
        except Exception:
            return
        parts = []
        if _detect_status("decode") == "running":
            parts.append("解码加速器")
        if _detect_status("encode") == "running":
            parts.append("编码加速器")
        if parts:
            w.update(f"正在检测：{' / '.join(parts)}…")
            w.display = True
        else:
            w.display = False

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id == "play":
            _log("菜单：播放视频")
            self.push_screen(SelectingScreen(
                initial=None, on_done=self._after_pick_play))
        elif event.item.id == "export":
            _log("菜单：导出视频")
            self.push_screen(SelectingScreen(
                initial=None, on_done=self._after_export_pick))
        elif event.item.id == "quit":
            _log("菜单：退出")
            self.app.exit(result="quit")

    def _after_export_pick(self, path):
        self.pop_screen()
        if path:
            self.push_screen(ExportSettingsScreen(video_path=path))
        else:
            safe_notify(self, "未选择视频，已返回主菜单", severity="error")

    def _after_pick_play(self, path):
        self.pop_screen()
        if path:
            self.push_screen(PlaySettingsScreen(video_path=path))
        else:
            safe_notify(self, "未选择视频，已返回主菜单", severity="error")
