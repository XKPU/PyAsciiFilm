# TUI 界面模块
import os
import threading

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import (
    ListView, ListItem, Label, Header, Footer, Input, Button, Static, Checkbox, Select, ProgressBar, RichLog,
)
from textual.containers import Vertical, Horizontal, ScrollableContainer

from utils import _list_verified_decode_backends, _log
from ascii_art import reload_charset, ASCII_CHARS
from dialogs import SelectingScreen, select_output_path, _gui_available


_EXPORTER = None


def _exporter():
    # 惰性加载导出模块
    global _EXPORTER
    if _EXPORTER is None:
        from exporter import export_video, _load_mono_font, _MAX_CANVAS_W, _MAX_CANVAS_H, _ENCODER_MAX_SIZE
        _EXPORTER = (export_video, _load_mono_font, _MAX_CANVAS_W, _MAX_CANVAS_H, _ENCODER_MAX_SIZE)
    return _EXPORTER


# ---------------------------------------------------------------------------
# 主菜单
# ---------------------------------------------------------------------------

class MenuApp(App):

    CSS = """
    Screen { align: center middle; }
    ListView { width: 60; height: auto; border: round $accent; padding: 1 2; }
    ListItem { padding: 0 1; }
    """

    BINDINGS = [("q", "quit", "退出")]

    def on_mount(self) -> None:
        # 设标题并聚焦列表
        self.title = "PyAsciiFilm"
        self.query_one(ListView).focus()

    def compose(self) -> ComposeResult:
        # 主菜单列表
        yield Header()
        yield ListView(
            ListItem(Label("导出为视频"), id="export"),
            ListItem(Label("以灰度模式播放视频"), id="play_gray_audio"),
            ListItem(Label("以全彩模式播放视频"), id="play_color_audio"),
            ListItem(Label("刷新配置文件"), id="reload_config"),
            ListItem(Label("退出"), id="quit"),
        )
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # 菜单项选择
        if event.item.id == "export":
            _log("菜单：选择导出为视频")
            self.push_screen(SelectingScreen(
                initial=None, on_done=self._after_export_pick))
        elif event.item.id == "play_gray_audio":
            _log("菜单：播放灰度视频（带音频）")
            self._pick_and_play(False)
        elif event.item.id == "play_color_audio":
            _log("菜单：播放全彩色视频（带音频）")
            self._pick_and_play(True)
        elif event.item.id == "reload_config":
            chars = reload_charset()
            _log("菜单：刷新配置文件")
            self.notify(
                f"配置已刷新，字符集已重新加载：{chars}",
                markup=False,
            )
        else:
            _log("菜单：退出")
            self.app.exit(result="quit")

    def _after_export_pick(self, path):
        # 选片后：无则回菜单，有则进入设置面板
        self.pop_screen()
        if path:
            self.push_screen(ExportSettingsScreen(video_path=path))
        else:
            self.notify("未选择视频，已返回主菜单", severity="error")

    def _pick_and_play(self, color):
        self.push_screen(SelectingScreen(
            initial=None, on_done=lambda p: self._after_pick_play(p, color)))

    def _after_pick_play(self, path, color):
        # 选片后回菜单或进入播放
        self.pop_screen()
        if path:
            self.app.exit(result=("play", color, path))


# ---------------------------------------------------------------------------
# 导出设置面板
# ---------------------------------------------------------------------------

class ExportSettingsScreen(Screen):

    BINDINGS = [("escape", "back_to_menu", "返回主菜单")]

    CSS = """
    Screen { align: center top; }
    #scroller { width: 100%; height: 1fr; }
    #panel { width: 100%; height: auto; padding: 1 2; }
    #panel > Horizontal { height: auto; margin: 1 0; }
    Label { width: auto; }
    Input { width: 1fr; }
    Select { width: 1fr; }
    #out_disp { width: 1fr; height: 3; border: round $accent; padding: 0 1; }
    #browse { width: 12; }
    #outhint { color: $text-muted; }
    #sizhint { color: $text-muted; }
    #err { color: $error; height: auto; }
    #warn { color: $warning; height: auto; }
    """

    FMT_OPTIONS = [
        ("MP4 (.mp4)", "mp4"),
        ("AVI (.avi)", "avi"),
        ("MKV (.mkv)", "mkv"),
        ("MOV (.mov)", "mov"),
        ("WebM (.webm)", "webm"),
    ]

    _MAX_REC_CHAR_W = 200

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
        self.out_path = ""
        self.fmt = "mp4"
        self.lock_ratio = True
        self._expect_w = None
        self._expect_h = None
        self._decode_backends = None

    def _select_video(self):
        # 提示后弹原生对话框选片
        self.app.push_screen(SelectingScreen(
            initial=self.video_path, on_done=self._on_video_picked))

    def _select_output(self):
        # 弹保存对话框选输出路径
        if not _gui_available():
            self.notify("当前环境无图形界面，请直接在输出路径框中输入路径",
                        severity="warning")
            return
        path = select_output_path(self.out_path, self.fmt)
        if path:
            self._set_out_path(path)

    def _on_video_picked(self, path):
        # 选片回调：有则刷新界面，最后关闭浏览器
        if path:
            self._set_video(path)
        self.app.pop_screen()

    def _set_video(self, video_path):
        # 设视频并刷新源信息、推荐尺寸、输出路径
        self.video_path = video_path
        self.src_w, self.src_h, self.src_fps = _probe_video(video_path)
        self.rec_w, self.rec_h = self._recommended_char_size()
        self.def_w, self.def_h = self.rec_w, self.rec_h
        base, _ = os.path.splitext(video_path)
        self.out_path = base + "_ascii.mp4"
        try:
            self.query_one("#srcinfo", Static).update(
                f"原视频: {self.src_w}x{self.src_h}  帧率: {self.src_fps:.2f} fps")
        except Exception:
            pass
        try:
            self.query_one("#w", Input).value = str(self.def_w)
            self.query_one("#h", Input).value = str(self.def_h)
            self.query_one("#fps", Input).value = str(int(round(self.src_fps)))
        except Exception:
            pass
        try:
            self.query_one("#out_disp", Input).value = self.out_path
        except Exception:
            pass
        try:
            self.query_one("#sizhint", Static).update(self._size_hint_text())
        except Exception:
            pass

    def _char_h_for_w(self, char_w):
        # 按原视频比例算字符高度
        if self.src_w <= 0 or self.src_h <= 0:
            return max(1, round(char_w * 3 / 4))
        h = char_w * (self.src_h / self.src_w) * (self.cell_w / self.cell_h)
        return max(1, round(h))

    def _canvas_bytes(self, char_w, char_h):
        # 字符网格 -> 画布像素尺寸与单帧字节数
        import math
        cw = int(math.ceil(char_w * self.cell_w))
        ch = int(math.ceil(char_h * self.cell_h))
        cw += cw % 2
        ch += ch % 2
        return cw * ch * 3, cw, ch

    def _recommended_char_size(self):
        # 按分辨率与字体算推荐字符网格宽高
        if self.src_w <= 0 or self.src_h <= 0:
            return 160, 120
        char_w = min(self._MAX_REC_CHAR_W, max(1, round(self.src_w / self.cell_w)))
        char_h = self._char_h_for_w(char_w)
        _, cw, ch = self._canvas_bytes(char_w, char_h)
        _MAX_W, _MAX_H = _exporter()[2], _exporter()[3]
        if cw > _MAX_W or ch > _MAX_H:
            scale = min(_MAX_W / cw, _MAX_H / ch)
            char_w = max(1, int(char_w * scale))
            char_h = self._char_h_for_w(char_w)
        return char_w, char_h

    def _size_hint_text(self, char_w=None, char_h=None):
        # 画布尺寸提示文案
        _, rcw, rch = self._canvas_bytes(self.rec_w, self.rec_h)
        base = (f"宽/高为字符数，推荐 {self.rec_w}x{self.rec_h} "
                f"字符（对应画布 {rcw}x{rch}px ≈ 原视频比例）")
        if char_w and char_h and char_w > 0 and char_h > 0:
            fb, cw, ch = self._canvas_bytes(char_w, char_h)
            _MAX_W, _MAX_H = _exporter()[2], _exporter()[3]
            over = " 超出上限" if cw > _MAX_W or ch > _MAX_H else ""
            base += f"\n当前 {char_w}x{char_h} → 画布 {cw}x{ch}px（单帧约 {fb / 1048576:.1f}MB{over}）"
        return base

    def _refresh_size_hint(self):
        # 刷新画布尺寸提示与硬件编码警告
        w = self._safe_int(self.query_one("#w", Input).value)
        h = self._safe_int(self.query_one("#h", Input).value)
        self.query_one("#sizhint", Static).update(self._size_hint_text(w, h))
        warn = ""
        if w and h and w > 0 and h > 0:
            _, cw, ch = self._canvas_bytes(w, h)
            _ENCODER_MAX_SIZE = _exporter()[4]
            for name, (mw, mh) in _ENCODER_MAX_SIZE.items():
                if cw > mw or ch > mh:
                    warn = f"画布 {cw}x{ch}px 超出 {name} 限制，将使用软件编码"
                    break
        self.query_one("#warn", Static).update(warn)

    def compose(self) -> ComposeResult:
        # 导出设置面板布局
        yield Header()
        yield ScrollableContainer(
            Vertical(
                Static("原视频: 尚未选择", id="srcinfo"),
                Horizontal(Label("宽度 :"), Input(value=str(self.def_w), id="w")),
                Horizontal(Label("高度 :"), Input(value=str(self.def_h), id="h")),
                Static(self._size_hint_text(), id="sizhint"),
                Horizontal(
                    Label("帧率 :"),
                    Input(value="30", id="fps"),
                    Button("▲", id="fps_up"),
                    Button("▼", id="fps_down"),
                ),
                Horizontal(Label("格式 :"), Select(self.FMT_OPTIONS, value="mp4", allow_blank=False, id="fmt")),
                Horizontal(Label("ffmpeg 最高占用(%):"), Input(value="35", id="usage")),
                Horizontal(Checkbox("锁定比例（按原视频比例）", value=True, id="lock")),
                Horizontal(Checkbox("彩色模式", id="color")),
                Horizontal(
                    Label("解码模式:"),
                    Select(
                        [("检测中...", -1)], value=-1, allow_blank=False, id="decode_mode",
                    ),
                    id="decode_mode_row",
                ),
                Horizontal(Label("输出 :"), Input(value=self.out_path, id="out_disp"), Button("浏览…", id="browse")),
                Static("（点击「浏览…」选择图形对话框，或直接输入路径）", id="outhint"),
                Static("", id="err"),
                Static("", id="warn"),
                Horizontal(Button("确认导出", id="ok"), Button("取消", id="cancel")),
                id="panel",
            ),
            id="scroller",
        )
        yield Footer()

    def on_mount(self) -> None:
        # 视频通常已在菜单选好；未选则退回选片
        if self.video_path:
            self._set_video(self.video_path)
        else:
            self.call_after_refresh(self._select_video)
        self.run_worker(self._init_hw_accel, thread=True)

    def action_back_to_menu(self):
        # Esc：返回主菜单
        self.app.pop_screen()

    def _init_hw_accel(self):
        # 后台线程：探测可用解码后端
        self._decode_backends = _list_verified_decode_backends()
        self.app.call_from_thread(self._apply_hw_accel)

    def _apply_hw_accel(self):
        # 主线程回调：填充解码模式下拉框
        sel = self.query_one("#decode_mode", Select)
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

    # ---- 宽高比例锁定 ----

    def on_input_changed(self, event: Input.Changed) -> None:
        # 输入变化时按比例同步宽高
        if event.input.id == "w":
            self._sync_from_width()
        elif event.input.id == "h":
            self._sync_from_height()
        if event.input.id in ("w", "h"):
            self._refresh_size_hint()

    def _safe_int(self, val):
        # 字符串转 int，失败返回 None
        try:
            return int(val)
        except ValueError:
            return None

    def _sync_from_width(self):
        # 按宽度比例同步高度
        if not self.lock_ratio:
            return
        if self._expect_w is not None:
            self._expect_w = None
            return
        w = self._safe_int(self.query_one("#w", Input).value)
        if w is None or w <= 0:
            return
        new_h = self._char_h_for_w(w)
        h_input = self.query_one("#h", Input)
        if self._safe_int(h_input.value) != new_h:
            self._expect_h = new_h
            h_input.value = str(new_h)

    def _sync_from_height(self):
        # 按高度比例同步宽度
        if not self.lock_ratio:
            return
        if self._expect_h is not None:
            self._expect_h = None
            return
        h = self._safe_int(self.query_one("#h", Input).value)
        if h is None or h <= 0:
            return
        if self.src_w <= 0 or self.src_h <= 0:
            new_w = max(1, round(h * 4 / 3))
        else:
            new_w = max(1, round(h * (self.src_w / self.src_h) * (self.cell_h / self.cell_w)))
        w_input = self.query_one("#w", Input)
        if self._safe_int(w_input.value) != new_w:
            self._expect_w = new_w
            w_input.value = str(new_w)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        # 比例锁定切换
        if event.checkbox.id == "lock":
            self.lock_ratio = event.value
            if self.lock_ratio:
                self._sync_from_width()

    def on_select_changed(self, event: Select.Changed) -> None:
        # 格式切换时更新输出扩展名
        if event.select.id == "fmt" and event.value:
            self.fmt = event.value
            base, _ = os.path.splitext(self.out_path)
            self.out_path = base + "." + self.fmt
            self.query_one("#out_disp", Input).value = self.out_path

    # ---- 帧率步进调整 ----

    def on_button_pressed(self, event: Button.Pressed) -> None:
        # 按钮点击分发
        bid = event.button.id
        if bid == "fps_up":
            self._step_fps(1)
            return
        if bid == "fps_down":
            self._step_fps(-1)
            return
        if bid == "cancel":
            self.app.pop_screen()
            return
        if bid == "browse":
            self._select_output()
            return
        if bid != "ok":
            return

        # 校验导出参数
        if not self.video_path:
            self.query_one("#err", Static).update("请先选择视频文件")
            return
        try:
            w = int(self.query_one("#w", Input).value)
            h = int(self.query_one("#h", Input).value)
            fps = float(self.query_one("#fps", Input).value)
        except ValueError:
            self.query_one("#err", Static).update("宽度/高度/帧率必须为数字")
            return

        if w <= 0 or h <= 0 or fps <= 0:
            self.query_one("#err", Static).update("宽度/高度/帧率必须大于 0")
            return
        _, cw, ch = self._canvas_bytes(w, h)
        _MAX_W, _MAX_H = _exporter()[2], _exporter()[3]
        if cw > _MAX_W or ch > _MAX_H:
            self.query_one("#err", Static).update(
                f"画布超出上限：{cw}x{ch}px（上限 {_MAX_W}x{_MAX_H}px）")
            return
        if fps > self.src_fps + 1e-6:
            self.query_one("#err", Static).update(
                f"目标帧率不能超过原视频 {self.src_fps:.2f} fps")
            return
        if not self.out_path:
            self.query_one("#err", Static).update("请填写输出文件路径")
            return

        # 组装参数并跳转进度界面
        color = self.query_one("#color", Checkbox).value
        sel_val = self.query_one("#decode_mode", Select).value
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
        self.app.push_screen(ExportProgressScreen(self.video_path, {
            "w": w, "h": h, "fps": fps, "out": self.out_path,
            "color": color, "fmt": self.fmt, "hwaccel": hwaccel,
            "ffmpeg_usage": usage,
        }))

    def _step_fps(self, delta):
        # 帧率步进 ±1
        try:
            fps = float(self.query_one("#fps", Input).value)
        except ValueError:
            fps = int(self.src_fps)
        fps = max(1.0, min(fps + delta, self.src_fps))
        self.query_one("#fps", Input).value = str(int(round(fps)))

    def _set_out_path(self, val):
        # 设输出路径（套用当前格式扩展名）
        base, _ = os.path.splitext(val)
        self.out_path = base + "." + self.fmt
        self.query_one("#out_disp", Input).value = self.out_path


# ---------------------------------------------------------------------------
# 导出进度界面
# ---------------------------------------------------------------------------

class ExportProgressScreen(Screen):

    BINDINGS = [("escape", "back_to_menu", "返回主菜单")]

    CSS = """
    Screen { align: center middle; }
    #ppanel { width: 70; height: auto; border: round $accent; padding: 1 2; }
    ProgressBar { margin: 1 0; }
    #result { height: 3; }
    #logpath { color: $text-muted; height: auto; }
    RichLog { height: 12; border: round $accent; }
    """

    def __init__(self, video_path, params):
        super().__init__()
        self.video_path = video_path
        self.params = params
        self._cancel = threading.Event()

    def compose(self) -> ComposeResult:
        # 进度界面布局
        yield Vertical(
            Static("正在导出视频…", id="title"),
            ProgressBar(id="bar", total=100),
            Static("", id="status"),
            RichLog(id="log"),
            Static("", id="result"),
            Horizontal(Button("返回菜单", id="back")),
            id="ppanel",
        )

    def on_mount(self) -> None:
        # 启动后台导出线程；返回按钮可随时中断
        threading.Thread(target=self._worker, daemon=True).start()

    def _request_exit(self):
        # 中断导出并返回主菜单
        self._cancel.set()
        self.app.pop_screen()

    def _worker(self):
        # 后台线程：调用 export_video
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
                lambda: done(False, f"导出异常: {e}")
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        # 返回按钮：中断导出
        if event.button.id == "back":
            self._request_exit()

    def action_back_to_menu(self):
        # Esc：中断导出并返回主菜单
        self._request_exit()


# ---------------------------------------------------------------------------
# 视频元信息探测
# ---------------------------------------------------------------------------

def _probe_video(path):
    # 探测视频宽、高、帧率
    from decoder import FrameReader
    cap = FrameReader(path, log=lambda msg: None)
    w, h, fps = cap.width, cap.height, cap.fps
    cap.release()
    return w, h, fps
