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
from dialogs import SelectingScreen, select_output_path


_EXPORTER = None


def _exporter():
    # 惰性加载导出模块
    global _EXPORTER
    if _EXPORTER is None:
        from exporter import export_video, _load_mono_font, _MAX_FRAME_BYTES
        _EXPORTER = (export_video, _load_mono_font, _MAX_FRAME_BYTES)
    return _EXPORTER


# ---------------------------------------------------------------------------
# 主菜单
# ---------------------------------------------------------------------------

class MenuApp(App):
    # 主菜单界面

    CSS = """
    Screen { align: center middle; }
    ListView { width: 60; height: auto; border: round $accent; padding: 1 2; }
    ListItem { padding: 0 1; }
    """

    BINDINGS = [("q", "quit", "退出")]

    def on_mount(self) -> None:
        # 挂载时设置窗口标题并聚焦列表
        self.title = "PyAsciiFilm"
        self.query_one(ListView).focus()

    def compose(self) -> ComposeResult:
        # 构建主菜单列表
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
        # 处理菜单项选择
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
            self.notify(f"配置已刷新，字符集已重新加载：{chars}")
        else:
            _log("菜单：退出")
            self.app.exit(result="quit")

    def _after_export_pick(self, path):
        # 导出前先选片：未选择则报错并返回主菜单，否则进入设置面板
        self.pop_screen()
        if path:
            self.push_screen(ExportSettingsScreen(video_path=path))
        else:
            self.notify("未选择视频，已返回主菜单", severity="error")

    def _pick_and_play(self, color):
        self.push_screen(SelectingScreen(
            initial=None, on_done=lambda p: self._after_pick_play(p, color)))

    def _after_pick_play(self, path, color):
        # 选片结束后返回菜单或进入播放
        self.pop_screen()
        if path:
            self.app.exit(result=("play", color, path))


# ---------------------------------------------------------------------------
# 导出设置面板
# ---------------------------------------------------------------------------

class ExportSettingsScreen(Screen):
    # 导出设置面板

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
        # 在 Textual 内提示“请选择视频”，随后弹出 tkinter 原生对话框选片
        self.app.push_screen(SelectingScreen(
            initial=self.video_path, on_done=self._on_video_picked))

    def _select_output(self):
        # 弹出 tkinter 保存对话框选择导出输出路径
        path = select_output_path(self.out_path, self.fmt)
        if path:
            self._set_out_path(path)

    def _on_video_picked(self, path):
        # 文件浏览器回调：选定后刷新界面并关闭浏览器，取消则仅关闭浏览器
        if path:
            self._set_video(path)
        self.app.pop_screen()

    def _set_video(self, video_path):
        # 设置视频并刷新源信息、推荐尺寸与输出路径
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
        # 根据字符宽度和原视频比例计算对应的字符高度
        if self.src_w <= 0 or self.src_h <= 0:
            return max(1, round(char_w * 3 / 4))
        h = char_w * (self.src_h / self.src_w) * (self.cell_w / self.cell_h)
        return max(1, round(h))

    def _canvas_bytes(self, char_w, char_h):
        # 计算给定字符网格对应的画布像素尺寸和单帧字节大小
        import math
        cw = int(math.ceil(char_w * self.cell_w))
        ch = int(math.ceil(char_h * self.cell_h))
        cw += cw % 2
        ch += ch % 2
        return cw * ch * 3, cw, ch

    def _recommended_char_size(self):
        # 根据视频分辨率和字体尺寸计算推荐的字符网格宽高
        if self.src_w <= 0 or self.src_h <= 0:
            return 160, 120
        char_w = min(self._MAX_REC_CHAR_W, max(1, round(self.src_w / self.cell_w)))
        char_h = self._char_h_for_w(char_w)
        frame_bytes, _, _ = self._canvas_bytes(char_w, char_h)
        _MAX_FRAME_BYTES = _exporter()[2]
        if frame_bytes > _MAX_FRAME_BYTES:
            scale = (_MAX_FRAME_BYTES / frame_bytes) ** 0.5
            char_w = max(1, int(char_w * scale))
            char_h = self._char_h_for_w(char_w)
        return char_w, char_h

    def _size_hint_text(self, char_w=None, char_h=None):
        # 生成画布尺寸提示文案
        _, rcw, rch = self._canvas_bytes(self.rec_w, self.rec_h)
        base = (f"宽/高为字符数，推荐 {self.rec_w}x{self.rec_h} "
                f"字符（对应画布 {rcw}x{rch}px ≈ 原视频比例）")
        if char_w and char_h and char_w > 0 and char_h > 0:
            fb, cw, ch = self._canvas_bytes(char_w, char_h)
            over = " 单帧过大" if fb > _exporter()[2] else ""
            base += f"\n当前 {char_w}x{char_h} → 画布 {cw}x{ch}px（单帧约 {fb / 1048576:.1f}MB{over}）"
        return base

    def _refresh_size_hint(self):
        # 读取当前宽高输入框的值，更新画布尺寸提示文案
        w = self._safe_int(self.query_one("#w", Input).value)
        h = self._safe_int(self.query_one("#h", Input).value)
        self.query_one("#sizhint", Static).update(self._size_hint_text(w, h))

    def compose(self) -> ComposeResult:
        # 构建导出设置面板布局
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
                Horizontal(Button("确认导出", id="ok"), Button("取消", id="cancel")),
                id="panel",
            ),
            id="scroller",
        )
        yield Footer()

    def on_mount(self) -> None:
        # 进入设置前视频已在菜单选好；未选（理论上不会）则退回选片
        if self.video_path:
            self._set_video(self.video_path)
        else:
            self.call_after_refresh(self._select_video)
        self.run_worker(self._init_hw_accel, thread=True)

    def action_back_to_menu(self):
        # Esc 快捷键：放弃设置直接返回主菜单
        self.app.pop_screen()

    def _init_hw_accel(self):
        # 后台线程：探测所有经验证可用的解码后端
        self._decode_backends = _list_verified_decode_backends()
        self.app.call_from_thread(self._apply_hw_accel)

    def _apply_hw_accel(self):
        # 主线程回调：用探测结果填充解码模式下拉框
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
        # 输入框内容变化时按比例同步宽高
        if event.input.id == "w":
            self._sync_from_width()
        elif event.input.id == "h":
            self._sync_from_height()
        if event.input.id in ("w", "h"):
            self._refresh_size_hint()

    def _safe_int(self, val):
        # 安全转换字符串为 int
        try:
            return int(val)
        except ValueError:
            return None

    def _sync_from_width(self):
        # 根据当前宽度值按比例同步更新高度值
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
        # 根据当前高度值按比例同步更新宽度值
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
        # 比例锁定复选框切换时更新锁定状态
        if event.checkbox.id == "lock":
            self.lock_ratio = event.value
            if self.lock_ratio:
                self._sync_from_width()

    def on_select_changed(self, event: Select.Changed) -> None:
        # 输出格式切换时更新输出路径的文件扩展名
        if event.select.id == "fmt" and event.value:
            self.fmt = event.value
            base, _ = os.path.splitext(self.out_path)
            self.out_path = base + "." + self.fmt
            self.query_one("#out_disp", Input).value = self.out_path

    # ---- 帧率步进调整 ----

    def on_button_pressed(self, event: Button.Pressed) -> None:
        # 处理所有按钮点击事件
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

        # ---- 校验导出参数 ----
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
        frame_bytes, cw, ch = self._canvas_bytes(w, h)
        if frame_bytes > _exporter()[2]:
            self.query_one("#err", Static).update(
                f"字符网格过大：{w}x{h} → 画布 {cw}x{ch}px（单帧 {frame_bytes / 1048576:.0f}MB）。"
                f"减小字符数，推荐 {self.rec_w}x{self.rec_h}")
            return
        if fps > self.src_fps + 1e-6:
            self.query_one("#err", Static).update(
                f"目标帧率不能超过原视频 {self.src_fps:.2f} fps")
            return
        if not self.out_path:
            self.query_one("#err", Static).update("请填写输出文件路径")
            return

        # ---- 组装导出参数并跳转进度界面 ----
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
        # 帧率步进调整 ±1
        try:
            fps = float(self.query_one("#fps", Input).value)
        except ValueError:
            fps = int(self.src_fps)
        fps = max(1.0, min(fps + delta, self.src_fps))
        self.query_one("#fps", Input).value = str(int(round(fps)))

    def _set_out_path(self, val):
        # 设置输出路径
        base, _ = os.path.splitext(val)
        self.out_path = base + "." + self.fmt
        self.query_one("#out_disp", Input).value = self.out_path


# ---------------------------------------------------------------------------
# 导出进度界面
# ---------------------------------------------------------------------------

class ExportProgressScreen(Screen):
    # 导出进度界面

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
        # 构建布局
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
        # 挂载即启动后台导出线程；返回按钮始终可用，用于中断导出
        threading.Thread(target=self._worker, daemon=True).start()

    def _request_exit(self):
        # 中断导出并清理相关进程后返回主菜单
        self._cancel.set()
        self.app.pop_screen()

    def _worker(self):
        # 后台线程：调用 export_video 执行实际导出
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
        # 返回按钮：中断导出并返回主菜单
        if event.button.id == "back":
            self._request_exit()

    def action_back_to_menu(self):
        # Esc 快捷键：随时中断导出并返回主菜单
        self._request_exit()


# ---------------------------------------------------------------------------
# 视频元信息探测
# ---------------------------------------------------------------------------

def _probe_video(path):
    # 探测视频文件的宽、高、帧率
    from decoder import FrameReader
    cap = FrameReader(path, log=lambda msg: None)
    w, h, fps = cap.width, cap.height, cap.fps
    cap.release()
    return w, h, fps
