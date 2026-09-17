import os

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Header, Footer, Input, Button, Static, Checkbox, Label,
)
from textual.containers import Vertical, Horizontal, ScrollableContainer

from core.main import ASCII_CHARS
from ..dialogs import SelectingScreen
from ..widgets import KeyBar, PlainSelect
from ..filebrowser.main import OutputDirBrowser
from .._shared import _probe_video, _exporter
from ._helpers import char_h_for_w, char_w_for_h, canvas_bytes, recommended_char_size
from .file_conflict import FileConflictScreen
from ._screen_config import EXPORT_ID_TO_ZONE, EXPORT_ZONE_HINTS, EXPORT_CSS, _EXPORT_INLINE


_EXPORT_TAB_ORDER = [
    "reselect", "char_w", "char_h", "lock", "fps", "fmt",
    "usage", "decode_mode", "out_path", "browse_dir", "color",
    "ok", "cancel",
]


class ExportSettingsScreen(Screen):

    BINDINGS = [
    ]

    _ID_TO_ZONE = EXPORT_ID_TO_ZONE
    _ZONE_HINTS = EXPORT_ZONE_HINTS

    FMT_OPTIONS = [
        ("MP4 (.mp4)", "mp4"),
        ("AVI (.avi)", "avi"),
        ("MKV (.mkv)", "mkv"),
        ("MOV (.mov)", "mov"),
        ("WebM (.webm)", "webm"),
    ]

    _MAX_REC_CHAR_W = 200

    CSS = EXPORT_CSS

    def __init__(self, video_path=None):
        super().__init__()
        self.video_path = video_path
        self.src_w, self.src_h, self.src_fps = 0, 0, 0.0
        try:
            _, self.cell_w, self.cell_h = _exporter()[1](ASCII_CHARS)
        except Exception:
            self.cell_w, self.cell_h = 10, 20
        self.rec_w, self.rec_h = 160, 120
        self.def_w, self.def_h = self.rec_w, self.rec_h
        self.out_dir = ""
        self.out_filename = ""
        self.fmt = "mp4"
        self.lock_ratio = True
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
        order = _EXPORT_TAB_ORDER
        focused = self.app.focused
        fid = getattr(focused, "id", "") if focused else None
        if fid in order:
            idx = order.index(fid)
            idx = (idx + (1 if forward else -1)) % len(order)
            self._focus_with_zone(order[idx])
        else:
            self._focus_with_zone(order[0])

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
        self.rec_w, self.rec_h = recommended_char_size(
            self.src_w, self.src_h, self.cell_w, self.cell_h,
            self._MAX_REC_CHAR_W, _exporter()[2], _exporter()[3])
        self.def_w, self.def_h = self.rec_w, self.rec_h
        self.out_dir = os.path.dirname(video_path) or os.getcwd()
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        self.out_filename = base_name + "_ascii"
        try:
            self.query_one("#srcinfo", Static).update(
                f"视频: {os.path.basename(video_path)}  "
                f"{self.src_w}x{self.src_h}  帧率: {self.src_fps:.2f} fps")
            self.query_one("#char_w", Input).value = str(self.def_w)
            self.query_one("#char_h", Input).value = str(self.def_h)
            self.query_one("#fps", Input).value = str(int(round(self.src_fps)))
            self.query_one("#out_path", Input).value = self._get_full_output_path()
            self._refresh_size_hint()
        except Exception:
            pass

    def _get_full_output_path(self):
        fname = self.out_filename.strip()
        if not fname:
            return ""
        fname_base = os.path.splitext(fname)[0]
        return os.path.join(self.out_dir, fname_base + "." + self.fmt)

    def _refresh_full_path(self):
        full = self._get_full_output_path()
        try:
            self.query_one("#out_path", Input).value = full
        except Exception:
            pass

    def _my_char_h_for_w(self, char_w):
        return char_h_for_w(char_w, self.src_w, self.src_h, self.cell_w, self.cell_h)

    def _my_char_w_for_h(self, char_h):
        return char_w_for_h(char_h, self.src_w, self.src_h, self.cell_w, self.cell_h)

    def _canvas_bytes(self, char_w, char_h):
        return canvas_bytes(char_w, char_h, self.cell_w, self.cell_h)

    def _safe_int(self, val):
        try:
            return int(val)
        except ValueError:
            return None

    def _size_hint_text(self):
        _, rcw, rch = self._canvas_bytes(self.rec_w, self.rec_h)
        return (f"推荐 {self.rec_w}x{self.rec_h} 字符"
                f"（对应画布 {rcw}x{rch}px ≈ 原视频比例）")

    def _refresh_size_hint(self):
        cw_val = self._safe_int(self.query_one("#char_w", Input).value)
        ch_val = self._safe_int(self.query_one("#char_h", Input).value)
        hint = self._size_hint_text()
        if cw_val and ch_val and cw_val > 0 and ch_val > 0:
            fb, cw, ch = self._canvas_bytes(cw_val, ch_val)
            _MAX_W, _MAX_H = _exporter()[2], _exporter()[3]
            over = " [超出上限]" if cw > _MAX_W or ch > _MAX_H else ""
            hint += (f"\n字符 {cw_val}x{ch_val} -> 画布 {cw}x{ch}px"
                     f"（单帧约{fb / 1048576:.1f}MB{over}）")
        self.query_one("#size_hint", Static).update(hint)
        warn = ""
        if cw_val and ch_val and cw_val > 0 and ch_val > 0:
            _, cw2, ch2 = self._canvas_bytes(cw_val, ch_val)
            _ENCODER_MAX_SIZE = _exporter()[4]
            for name, (mw, mh) in _ENCODER_MAX_SIZE.items():
                if cw2 > mw or ch2 > mh:
                    warn = f"画布 {cw2}x{ch2}px 超出 {name} 限制，将使用软件编码"
                    break
        self.query_one("#warn", Static).update(warn)

    def _step_fps(self, delta):
        try:
            fps = float(self.query_one("#fps", Input).value)
        except ValueError:
            fps = int(self.src_fps)
        fps = max(1.0, min(fps + delta, self.src_fps))
        self.query_one("#fps", Input).value = str(int(round(fps)))

    def _select_output_dir(self):
        def _on_dir_picked(result):
            if result:
                dir_path, fname = result
                self.out_dir = dir_path
                self.out_filename = fname
                self._refresh_full_path()

        self.app.push_screen(
            OutputDirBrowser(initial=self.out_dir,
                             filename_hint=self.out_filename,
                             ext=self.fmt),
            callback=_on_dir_picked,
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        iid = event.input.id
        if iid == "char_w":
            focused = self.app.focused
            if focused and focused.id == "char_w":
                self._sync_from_char_w()
        elif iid == "char_h":
            focused = self.app.focused
            if focused and focused.id == "char_h":
                self._sync_from_char_h()
        elif iid == "out_path":
            self._parse_full_path(event.value)
            return
        self._refresh_size_hint()

    def _parse_full_path(self, full_path: str):
        full_path = full_path.strip()
        if not full_path:
            return
        dir_part = os.path.dirname(full_path)
        name_part = os.path.basename(full_path)
        if dir_part and name_part:
            self.out_dir = dir_part
            self.out_filename = os.path.splitext(name_part)[0]

    def _sync_from_char_w(self):
        w = self._safe_int(self.query_one("#char_w", Input).value)
        if w is None or w <= 0:
            return
        if self.lock_ratio:
            new_h = self._my_char_h_for_w(w)
            h_input = self.query_one("#char_h", Input)
            if self._safe_int(h_input.value) != new_h:
                h_input.value = str(new_h)

    def _sync_from_char_h(self):
        h = self._safe_int(self.query_one("#char_h", Input).value)
        if h is None or h <= 0:
            return
        if self.lock_ratio:
            new_w = self._my_char_w_for_h(h)
            w_input = self.query_one("#char_w", Input)
            if self._safe_int(w_input.value) != new_w:
                w_input.value = str(new_w)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "lock":
            self.lock_ratio = event.value
            if self.lock_ratio:
                w = self._safe_int(self.query_one("#char_w", Input).value)
                if w and w > 0:
                    new_h = self._my_char_h_for_w(w)
                    self.query_one("#char_h", Input).value = str(new_h)
                self._refresh_size_hint()

    def on_select_changed(self, event: PlainSelect.Changed) -> None:
        if event.select.id == "fmt" and event.value:
            self.fmt = event.value
            self._refresh_full_path()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "fps_up":
            self._step_fps(1)
        elif bid == "fps_down":
            self._step_fps(-1)
        elif bid == "cancel":
            self.app.pop_screen()
        elif bid == "browse_dir":
            self._select_output_dir()
        elif bid == "reselect":
            self._select_video()
        elif bid == "ok":
            self._do_export()

    def _do_export(self):
        if not self.video_path:
            self.query_one("#err", Static).update("请先选择视频文件")
            return
        try:
            cw = int(self.query_one("#char_w", Input).value)
            ch = int(self.query_one("#char_h", Input).value)
            fps = float(self.query_one("#fps", Input).value)
        except ValueError:
            self.query_one("#err", Static).update("所有数值字段必须为整数/数字")
            return
        if cw <= 0 or ch <= 0 or fps <= 0:
            self.query_one("#err", Static).update("所有数值必须大于 0")
            return
        _, rcw, rch = self._canvas_bytes(cw, ch)
        _MAX_W, _MAX_H = _exporter()[2], _exporter()[3]
        if rcw > _MAX_W or rch > _MAX_H:
            self.query_one("#err", Static).update(
                f"画布超出上限: {rcw}x{rch}px（上限 {_MAX_W}x{_MAX_H}px）")
            return
        if fps > self.src_fps + 1e-6:
            self.query_one("#err", Static).update(
                f"目标帧率不能超过原视频 {self.src_fps:.2f} fps")
            return

        out_path = self._get_full_output_path()
        if not out_path:
            self.query_one("#err", Static).update("请填写文件名")
            return
        if not self.out_dir or not os.path.isdir(self.out_dir):
            self.query_one("#err", Static).update("输出目录不存在")
            return

        if os.path.exists(out_path):
            fname = os.path.basename(out_path)

            def _on_conflict(result):
                if result == "replace":
                    self._start_export(cw, ch, fps, out_path)
                elif result == "rename":
                    self.query_one("#out_path", Input).focus()
                    self.query_one("#err", Static).update(
                        "文件已存在，请修改输出路径后重新导出")

            self.app.push_screen(
                FileConflictScreen(fname), callback=_on_conflict)
            return

        self._start_export(cw, ch, fps, out_path)

    def _start_export(self, cw, ch, fps, out_path):
        color = self.query_one("#color", Checkbox).value
        sel_val = self.query_one("#decode_mode", PlainSelect).value
        if self._decode_backends and isinstance(sel_val, int) and sel_val < len(self._decode_backends):
            _label, decode_args = self._decode_backends[sel_val]
        else:
            decode_args = None
        hwaccel = {"decode_args": decode_args} if decode_args else False
        try:
            usage = int(self.query_one("#usage", Input).value)
        except ValueError:
            usage = 35
        usage = max(1, min(100, usage))

        from .export_progress import ExportProgressScreen
        self.app.push_screen(ExportProgressScreen(self.video_path, {
            "w": cw, "h": ch, "fps": fps, "out": out_path,
            "color": color, "fmt": self.fmt, "hwaccel": hwaccel,
            "ffmpeg_usage": usage,
        }), callback=lambda _: self.app.pop_screen())

    def _shortcut(self, widget_id: str) -> Static:
        text = _EXPORT_INLINE.get(widget_id, "")
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
                Horizontal(Label("横向字符数:"), self._shortcut("char_w"), Input(value=str(self.def_w), id="char_w")),
                Horizontal(Label("竖向字符数:"), self._shortcut("char_h"), Input(value=str(self.def_h), id="char_h")),
                Static(self._size_hint_text(), id="size_hint", classes="hint", markup=False),
                Horizontal(Checkbox("锁定比例（按原视频比例）", value=True, id="lock"), self._shortcut("lock")),
                Static("锁定比例时修改横向字符数会自动同步竖向，反之亦然",
                       classes="hint"),
                Static("[!] 过大的字符数/分辨率会导致导出缓慢", classes="hint", markup=False),
                Horizontal(
                    Label("帧率:"), self._shortcut("fps"),
                    Input(value=str(int(round(self.src_fps))), id="fps"),
                    Button("^", id="fps_up"),
                    Button("v", id="fps_down"),
                ),
                Static("目标帧率，若CPU性能不足将会导致导出缓慢", classes="hint"),
                Horizontal(Label("导出格式:"), self._shortcut("fmt"), PlainSelect(self.FMT_OPTIONS, value="mp4",
                                                      allow_blank=False, id="fmt")),
                Horizontal(Label("ffmpeg最高占用(%):"), self._shortcut("usage"), Input(value="35", id="usage")),
                Horizontal(
                    Label("解码模式:"), self._shortcut("decode_mode"),
                    PlainSelect(
                        [("检测中...", -1)], value=-1, allow_blank=False, id="decode_mode",
                    ),
                ),
                Horizontal(
                    Label("输出目录:"), self._shortcut("out_path"),
                    Input(value=self._get_full_output_path(), id="out_path",
                          placeholder="完整输出路径（含文件名）"),
                    Button("浏览", id="browse_dir", variant="default"),
                    self._shortcut("browse_dir"),
                ),
                Horizontal(Checkbox("彩色模式", id="color"), self._shortcut("color")),
                Static("", id="err"),
                Static("", id="warn"),
                Horizontal(
                    Button("导出", id="ok", variant="primary"),
                    Button("取消", id="cancel"),
                    self._shortcut("ok"),
                ),
                id="panel",
            ),
            id="scroller",
        )
        yield Footer()
        yield KeyBar()

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

        # Escape
        if key == "escape":
            event.stop()
            self.app.pop_screen()
            return

        # Ctrl+ 快捷键
        _MAP = {
            "ctrl+w": "char_w",
            "ctrl+k": "char_h",
            "ctrl+l": "lock",
            "ctrl+f": "fps",
            "ctrl+g": "fmt",
            "ctrl+u": "usage",
            "ctrl+d": "decode_mode",
            "ctrl+o": "out_path",
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
        if key == "ctrl+b":
            event.stop()
            self._select_output_dir()
            return
        if key == "ctrl+s":
            event.stop()
            self.query_one("#ok", Button).action_press()
            return

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