# TUI 主界面
from textual.app import App, ComposeResult
from textual.widgets import (
    ListView, ListItem, Label, Header, Footer,
)

from utils.helpers import _list_verified_decode_backends, _log
from core.main import reload_charset

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
        self.run_worker(self._detect_decode_backends, thread=True)

    def _update_keybar(self):
        try:
            kb = self.query_one(KeyBar)
            kb.set_hint("↑↓ 选择 | Enter 确认 | Ctrl+Q 退出")
        except Exception:
            pass

    def _detect_decode_backends(self):
        _shared._cached_decode_backends = _list_verified_decode_backends()

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListView(
            ListItem(Label("播放视频"), id="play"),
            ListItem(Label("导出视频"), id="export"),
            ListItem(Label("刷新配置"), id="reload_config"),
            ListItem(Label("退出程序"), id="quit"),
        )
        yield Footer()
        yield KeyBar()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id == "play":
            _log("菜单：播放视频")
            self.push_screen(SelectingScreen(
                initial=None, on_done=self._after_pick_play))
        elif event.item.id == "export":
            _log("菜单：导出视频")
            self.push_screen(SelectingScreen(
                initial=None, on_done=self._after_export_pick))
        elif event.item.id == "reload_config":
            chars = reload_charset()
            _log("菜单：刷新配置")
            safe_notify(self, f"配置已刷新，字符集已重新加载：{chars}", markup=False)
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