import os
import threading

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, ProgressBar, RichLog
from textual.containers import Vertical, Horizontal

from ..widgets import KeyBar
from .._shared import _exporter


class ExportProgressScreen(Screen):

    BINDINGS = [("escape", "back_to_menu", "返回主菜单")]

    CSS = """
    Screen { align: center middle; }
    #ppanel { width: 70; height: auto; border: round $accent; padding: 1 2; }
    ProgressBar { margin: 1 0; }
    #result { height: 3; }
    #logpath { color: $text-muted; height: auto; }
    RichLog { height: 12; border: round $accent; }
    KeyBar {
        height: 1;
        background: $primary 10%;
        color: $text;
        padding: 0 1;
        text-style: bold;
        dock: bottom;
    }
    """

    def __init__(self, video_path, params):
        super().__init__()
        self.video_path = video_path
        self.params = params
        self._cancel = threading.Event()
        self._export_done = False
        self._dismissed = False

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("正在导出视频…", id="title"),
            ProgressBar(id="bar", total=100),
            Static("", id="status"),
            RichLog(id="log"),
            Static("", id="result"),
            Horizontal(Button("返回菜单", id="back")),
            id="ppanel",
        )
        yield KeyBar()

    def on_mount(self) -> None:
        self._update_hint(exporting=True)
        threading.Thread(target=self._worker, daemon=True).start()

    def _update_hint(self, exporting=True):
        hint = "Esc 取消导出并返回菜单" if exporting else "Esc 返回菜单 | Enter 点击返回按钮"
        try:
            self.query_one(KeyBar).set_hint(hint)
        except Exception:
            pass

    def _request_exit(self):
        if self._dismissed:
            return
        self._dismissed = True
        self._cancel.set()
        self.app.pop_screen()
        self.app.pop_screen()

    def _worker(self):
        out_base = os.path.splitext(self.params["out"])[0] + "." + self.params["fmt"]

        def prog(stage, done, total):
            def upd():
                try:
                    if stage == "init":
                        self.query_one("#status", Static).update("初始化导出…")
                    elif stage == "analyze":
                        self.query_one("#status", Static).update(f"分析中: {done}/{total}")
                    else:
                        self.query_one("#status", Static).update(f"导出中: {done}/{total}")
                        pct = (done / total * 100) if total else 0
                        self.query_one("#bar", ProgressBar).update(progress=pct)
                except Exception:
                    pass
            self.app.call_from_thread(upd)

        def done(success, msg):
            def upd():
                try:
                    self.query_one("#result", Static).update(msg)
                    self.query_one("#bar", ProgressBar).update(progress=100)
                    self.query_one("#back", Button).disabled = False
                    self._export_done = True
                    self._update_hint(exporting=False)
                except Exception:
                    pass
            self.app.call_from_thread(upd)

        def on_log(msg):
            def upd():
                try:
                    self.query_one("#log", RichLog).write(msg)
                except Exception:
                    pass
            self.app.call_from_thread(upd)

        try:
            _exporter()[0](
                self.video_path, out_base,
                self.params["w"], self.params["h"], self.params["fps"],
                use_color=self.params["color"], fmt=self.params["fmt"],
                on_progress=prog, on_done=done, on_log=on_log,
                hwaccel=self.params.get("hwaccel", True),
                ffmpeg_usage=self.params.get("ffmpeg_usage", 35),
                cancel=self._cancel.is_set,
            )
        except Exception as e:
            self.app.call_from_thread(
                lambda _e=e: done(False, f"导出异常: {_e}")
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self._request_exit()

    def action_back_to_menu(self):
        self._request_exit()