import os

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Header, Footer, Input, Button, Static, Checkbox, Label,
)
from textual.containers import Vertical, Horizontal, ScrollableContainer

from ..dialogs import SelectingScreen
from ..widgets import KeyBar, PlainSelect
from .._shared import _probe_video
from ._screen_config import PLAY_ID_TO_ZONE, PLAY_ZONE_HINTS, _PLAY_INLINE


_PLAY_TAB_ORDER = ["reselect", "fps", "usage", "decode_mode", "color", "ok", "cancel"]


class PlaySettingsScreen(Screen):

    BINDINGS = [
        ("escape", "back_to_menu", "返回主菜单"),
    ]

    _ID_TO_ZONE = PLAY_ID_TO_ZONE
    _ZONE_HINTS = PLAY_ZONE_HINTS

    CSS = """
    Screen { align: center top; }
    #scroller { width: 100%; height: 1fr; }
    #panel { width: 100%; height: auto; padding: 1 2; }
    #panel > Horizontal { height: auto; margin: 1 0; }
    Label { width: auto; }
    Input { width: 1fr; }
    Select { width: 1fr; }
    #srcinfo { margin: 0 0 1 0; }
    .hint { color: $text-muted; }
    .shortcut {
        color: $text-disabled;
        text-style: none;
        width: auto;
        padding: 0 1;
    }
    #err { color: $error; height: auto; }
    #btn_row { margin: 1 0; }
    KeyBar {
        height: 1;
        background: $primary 10%;
        color: $text;
        padding: 0 1;
        text-style: bold;
        dock: bottom;
    }
    """

    def __init__(self, video_path=None):
        super().__init__()
        self.video_path = video_path
        self.src_w, self.src_h, self.src_fps = 0, 0, 0.0
        self._decode_backends = None
        self._active_zone = "src_area"

    def _focus_by_id(self, widget_id: str) -> None:
        try:
            self.query_one(f"#{widget_id}").focus()
        except Exception:
            pass

    def _focus_with_zone(self, widget_id: str) -> None:
        self._focus_by_id(widget_id)
        zone = self._ID_TO_ZONE.get(widget_id)
        if zone:
            self._active_zone = zone
            self._update_keybar()

    def _tab_cycle(self, forward: bool = True) -> None:
        order = _PLAY_TAB_ORDER
        focused = self.app.focused
        fid = getattr(focused, "id", "") if focused else None
        if fid in order:
            idx = order.index(fid)
            idx = (idx + (1 if forward else -1)) % len(order)
            self._focus_with_zone(order[idx])
        else:
            self._focus_with_zone(order[0])

    def on_mount(self) -> None:
        if self.video_path:
            self._set_video(self.video_path)
        else:
            self.call_after_refresh(self._select_video)
        self._decode_backends = []
        self._apply_decode_options()
        self._update_keybar()
        self.set_interval(0.5, self._poll_decode_backends)

    def _poll_decode_backends(self):
        if self._decode_backends:
            return
        from .. import _shared
        if _shared._cached_decode_backends is None:
            return
        self._decode_backends = _shared._cached_decode_backends or []
        self._apply_decode_options()

    def _update_keybar(self):
        hints = self._ZONE_HINTS.get(self._active_zone, "")
        try:
            self.query_one(KeyBar).set_hint(hints)
        except Exception:
            pass

    def on_focus(self, event) -> None:
        widget = event.widget
        if widget is None:
            return
        fid = getattr(widget, "id", "") or ""
        zone = self._ID_TO_ZONE.get(fid)
        if not zone:
            w = widget
            while hasattr(w, "parent") and w.parent is not None:
                w = w.parent
                fid = getattr(w, "id", "") or ""
                zone = self._ID_TO_ZONE.get(fid)
                if zone:
                    break
        if zone:
            self._active_zone = zone
            self._update_keybar()

    def on_click(self, event) -> None:
        widget = self.app.focused
        if widget is None:
            return
        fid = getattr(widget, "id", "") or ""
        zone = self._ID_TO_ZONE.get(fid)
        if not zone:
            w = widget
            while hasattr(w, "parent") and w.parent is not None:
                w = w.parent
                fid = getattr(w, "id", "") or ""
                zone = self._ID_TO_ZONE.get(fid)
                if zone:
                    break
        if zone:
            self._active_zone = zone
            self._update_keybar()

    async def on_key(self, event) -> None:
        key = event.key

        # Tab / Shift+Tab
        if key == "tab":
            event.stop()
            self._tab_cycle(forward=True)
            return
        if key == "shift+tab":
            event.stop()
            self._tab_cycle(forward=False)
            return

        # Ctrl+ 快捷键
        _MAP = {
            "ctrl+f": "fps",
            "ctrl+u": "usage",
            "ctrl+d": "decode_mode",
            "ctrl+t": "color",
        }
        if key in _MAP:
            event.stop()
            self._focus_with_zone(_MAP[key])
            return
        if key == "ctrl+r":
            event.stop()
            self._select_video()
            return
        if key == "ctrl+s":
            event.stop()
            self._do_play()
            return

    def _do_play(self):
        if not self.video_path:
            self.query_one("#err", Static).update("请先选择视频文件")
            return
        try:
            fps = float(self.query_one("#fps", Input).value)
        except ValueError:
            self.query_one("#err", Static).update("帧率必须为数字")
            return
        if fps <= 0:
            self.query_one("#err", Static).update("帧率必须大于 0")
            return
        color = self.query_one("#color", Checkbox).value
        sel_val = self.query_one("#decode_mode", PlainSelect).value
        if self._decode_backends and isinstance(sel_val, int) and sel_val < len(self._decode_backends):
            _label, decode_args = self._decode_backends[sel_val]
        else:
            decode_args = None
        try:
            usage = int(self.query_one("#usage", Input).value)
        except ValueError:
            usage = 35
        usage = max(1, min(100, usage))
        self.app.exit(result=("play", color, self.video_path, fps, decode_args, usage))

    def action_back_to_menu(self):
        self.app.pop_screen()

    def _select_video(self):
        self.app.push_screen(SelectingScreen(
            initial=self.video_path, on_done=self._on_video_picked))

    def _on_video_picked(self, path):
        if path:
            self._set_video(path)
        self.app.pop_screen()

    def _set_video(self, video_path):
        self.video_path = video_path
        self.src_w, self.src_h, self.src_fps = _probe_video(video_path)
        try:
            self.query_one("#srcinfo", Static).update(
                f"视频: {os.path.basename(video_path)}  "
                f"{self.src_w}x{self.src_h}  帧率: {self.src_fps:.2f} fps")
            self.query_one("#fps", Input).value = str(int(round(self.src_fps)))
        except Exception:
            pass

    def _apply_decode_options(self):
        if not self._decode_backends:
            return
        sel = self.query_one("#decode_mode", PlainSelect)
        options = [(label, i) for i, (label, _) in enumerate(self._decode_backends)]
        sel.set_options(options)
        default = 0
        for i, (label, _args) in enumerate(self._decode_backends):
            if "CUDA" in label.upper():
                default = i
                break
        else:
            default = len(self._decode_backends) - 1
        if options:
            sel.value = default

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "cancel":
            self.app.pop_screen()
        elif bid == "reselect":
            self._select_video()
        elif bid == "ok":
            self._do_play()

    def _shortcut(self, widget_id: str) -> Static:
        text = _PLAY_INLINE.get(widget_id, "")
        return Static(f" {text} ", classes="shortcut") if text else Static("")

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScrollableContainer(
            Vertical(
                Horizontal(
                    Static("尚未选择视频", id="srcinfo"),
                    Button("重新选择", id="reselect", variant="default"),
                    self._shortcut("reselect"),
                ),
                Horizontal(
                    Label("帧率:"), self._shortcut("fps"),
                    Input(value="", id="fps"),
                ),
                Static("目标帧率，不为实际播放帧率，实际帧率受CPU性能限制", id="hint"),
                Horizontal(
                    Label("ffmpeg最高占用(%):"), self._shortcut("usage"),
                    Input(value="35", id="usage"),
                ),
                Horizontal(
                    Label("解码模式:"), self._shortcut("decode_mode"),
                    PlainSelect(
                        [("检测中...", -1)], value=-1, allow_blank=False, id="decode_mode",
                    ),
                ),
                Horizontal(Checkbox("彩色模式", id="color"), self._shortcut("color")),
                Static("", id="err"),
                Horizontal(
                    Button("开始播放", id="ok", variant="primary"),
                    Button("取消", id="cancel"),
                    self._shortcut("ok"),
                    id="btn_row",
                ),
                id="panel",
            ),
            id="scroller",
        )
        yield Footer()
        yield KeyBar()