# 视频文件浏览器
import os
import asyncio

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Static, Input, Button, ListView, ListItem, Label,
)
from textual.containers import Horizontal, Vertical
from textual.events import Key

from utils.helpers import (
    _log_error,
    _write_config_value,
    user_dirs, list_drives, sorted_entries,
    format_file_size, format_datetime_ts,
    LAST_VIDEO_DIR_KEY, VIDEO_EXTS,
)
from ..widgets import KeyBar, safe_notify
from .browser_nav import BrowserNav
from .browser_config import FB_CSS, FB_ID_TO_ZONE, FB_ZONE_HINTS
from ..screens._helpers import _format_duration, _probe_video_metadata, _load_last_dir


def _safe_id(name: str) -> str:
    """将任意字符串转为合法的 Textual id"""
    import re as _re, hashlib
    clean = _re.sub(r"[^a-zA-Z0-9]", "-", name).strip("-")
    if not clean:
        clean = "x"
    if clean[0].isdigit():
        clean = "i" + clean
    # 短哈希避免冲突
    h = hashlib.md5(name.encode("utf-8")).hexdigest()[:6]
    return f"{clean}-{h}"


class VideoFileBrowser(Screen, BrowserNav):
    """Textual 视频文件浏览器"""

    BINDINGS: list = []
    CSS = FB_CSS

    def __init__(self, initial: str | None = None) -> None:
        super().__init__()
        if initial and os.path.isfile(initial):
            self._current_path = os.path.dirname(initial)
        elif initial and os.path.isdir(initial):
            self._current_path = initial
        else:
            last = _load_last_dir()
            try:
                self._current_path = last if last and os.path.isdir(last) else os.path.expanduser("~")
            except Exception:
                self._current_path = os.path.expanduser("~")
        self._active_zone = "file_list"

    _ID_TO_ZONE = FB_ID_TO_ZONE
    _ZONE_HINTS = FB_ZONE_HINTS

    def compose(self) -> ComposeResult:
        with Vertical(id="browser-container"):
            with Horizontal(id="path-bar"):
                yield Input(value=self._current_path, id="path-input", placeholder="路径...")
                yield Button("转到", id="go-btn", variant="default")
                yield Button("上一级", id="go-up-btn", variant="default")
            with Horizontal(id="main-area"):
                with Vertical(id="sidebar"):
                    yield Static("快捷访问", id="sidebar-title")
                    yield ListView(id="sidebar-list")
                with Vertical(id="file-area"):
                    yield Static("当前目录", id="current-path")
                    with Horizontal(id="file-detail-row"):
                        with Vertical(id="file-list-col"):
                            yield Static("文件列表", id="file-header")
                            yield ListView(id="file-list")
                        with Vertical(id="detail-panel"):
                            yield Static("详细信息", id="detail-header")
                            yield Static("", id="detail-content")
            with Horizontal(id="action-bar"):
                yield Static("", id="selected-label")
                yield Static("过滤: 仅视频", id="show-all-indicator", markup=False)
                yield Button("选择当前文件", id="select-btn", variant="primary")
                yield Button("取消", id="cancel-btn")
        yield KeyBar()

    async def on_mount(self) -> None:
        self._update_keybar()
        self._update_show_all_indicator()
        self._deferred_refresh()

    def _deferred_refresh(self) -> None:
        asyncio.create_task(self._refresh_files(and_focus=True))
        asyncio.create_task(self._populate_sidebar())

    def on_unmount(self) -> None:
        pass

    def on_resize(self, event) -> None:
        self._toggle_detail_panel()

    def _toggle_detail_panel(self) -> None:
        try:
            detail = self.query_one("#detail-panel", Vertical)
            width = self.size.width
            detail.styles.display = "none" if width < 100 else "block"
        except Exception:
            pass

    async def on_key(self, event: Key) -> None:
        await self._browser_on_key(event, self._active_zone)

    def _browser_nav_map(self):
        return {
            "left": (self._focus_sidebar, "sidebar"),
            "h": (self._focus_sidebar, "sidebar"),
            "right": (self._focus_file_list, "file_list"),
            "l": (self._focus_file_list, "file_list"),
        }

    async def _browser_on_enter(self, event, zone):
        await self._on_enter(zone)

    async def _on_enter(self, zone: str) -> None:
        if zone == "path_input":
            await self._on_path_go(self.query_one("#path-input", Input).value)
            self._focus_file_list()
            self._active_zone = "file_list"
            self._update_keybar()
        elif zone == "bottom_buttons":
            await self._confirm()
        elif zone == "path_buttons":
            foc = self.app.focused
            if foc is not None and hasattr(foc, "id"):
                if foc.id == "go-up-btn":
                    await self._go_up()
                elif foc.id == "go-btn":
                    await self._on_path_go(self.query_one("#path-input", Input).value)
                    self._focus_file_list()
                    self._active_zone = "file_list"
                    self._update_keybar()

    async def _select_current_file_item(self) -> None:
        """选中文件列表中的当前项"""
        file_list = self.query_one("#file-list", ListView)
        if file_list.index is None or file_list.index >= len(file_list):
            return
        item = file_list.children[file_list.index]
        item_class = getattr(item, "classes", "")
        if "dir-item" in item_class:
            entry_name = getattr(item, "_entry_name", None)
            if entry_name:
                await self._navigate_to(entry_name)
        else:
            await self._confirm()

    async def _select_current_sidebar_item(self):
        """选中侧栏中的当前项"""
        sidebar = self.query_one("#sidebar-list", ListView)
        if sidebar.index is None:
            return
        item = sidebar.children[sidebar.index]
        nav_path = getattr(item, "_nav_path", None)
        if nav_path is None:
            return  # 跳过分隔线
        await self._navigate_to(nav_path)
        self._focus_file_list()
        self._active_zone = "file_list"
        self._update_keybar()

    def on_focus(self, event) -> None:
        self._browser_on_focus(event)

    def on_click(self, event) -> None:
        self._browser_on_click(event)

    def _focus_sidebar(self) -> None:
        try:
            sidebar = self.query_one("#sidebar-list", ListView)
            if sidebar:
                if sidebar.index is None and len(sidebar) > 0:
                    sidebar.index = 0
                sidebar.focus()
        except Exception:
            pass

    def _focus_file_list(self) -> None:
        try:
            fl = self.query_one("#file-list", ListView)
            if fl:
                if fl.index is None and len(fl) > 0:
                    fl.index = 0
                fl.focus()
        except Exception:
            pass

    def _focus_path(self) -> None:
        try:
            inp = self.query_one("#path-input", Input)
            if inp:
                inp.focus()
        except Exception:
            pass

    def _focus_bottom_buttons(self) -> None:
        try:
            btn = self.query_one("#select-btn", Button)
            if btn:
                btn.focus()
        except Exception:
            pass

    def _focus_select_btn(self) -> None:
        try:
            self.query_one("#select-btn", Button).focus()
        except Exception:
            pass

    def _focus_cancel_btn(self) -> None:
        try:
            self.query_one("#cancel-btn", Button).focus()
        except Exception:
            pass

    def _focus_path_buttons(self) -> None:
        try:
            btn = self.query_one("#go-up-btn", Button)
            if btn:
                btn.focus()
        except Exception:
            pass

    def _focus_path_go_btn(self) -> None:
        try:
            btn = self.query_one("#go-btn", Button)
            if btn:
                btn.focus()
        except Exception:
            pass

    def _focus_path_up_btn(self) -> None:
        try:
            btn = self.query_one("#go-up-btn", Button)
            if btn:
                btn.focus()
        except Exception:
            pass

    async def _populate_sidebar(self):
        sidebar = self.query_one("#sidebar-list", ListView)
        await sidebar.clear()
        try:
            for label, path in user_dirs():
                safe_id = "dir-" + path.replace("\\", "-").replace(":", "-").replace(" ", "-").replace("/", "-")
                sidebar.append(ListItem(Label(f"📁 {label}"), id=safe_id, classes="sidebar-item"))
                sidebar.children[-1]._nav_path = path
            sep = ListItem(Label("─────────────"), id="sep", classes="sidebar-sep")
            sep._nav_path = None
            sep.disabled = True
            sidebar.append(sep)
            for drive_name, drive_path in list_drives():
                safe_id = "drv-" + drive_path.replace("\\", "-").replace(":", "-").replace(" ", "-").replace("/", "-")
                sidebar.append(ListItem(Label(f"{drive_name}"), id=safe_id, classes="sidebar-item"))
                sidebar.children[-1]._nav_path = drive_path
        except Exception as e:
            _log_error(f"加载侧栏失败: {e}")

    # ── 文件列表事件 ──

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "file-list":
            await self._select_current_file_item()
        elif event.list_view.id == "sidebar-list":
            await self._select_current_sidebar_item()

    async def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id == "file-list" and event.item is not None:
            entry_name = getattr(event.item, "_entry_name", None)
            self._update_detail_panel(entry_name)

    # ── 详细信息面板 ──

    def _update_detail_panel(self, item_id: str) -> None:
        """更新右侧详细信息面板（标题固定为"详细信息"）"""
        try:
            detail = self.query_one("#detail-content", Static)
            header = self.query_one("#detail-header", Static)
        except Exception:
            return
        # 标题始终固定
        header.update("详细信息")

        if not item_id:
            detail.update("")
            return

        # ".." 表示返回上一级
        if item_id == "..":
            parent = os.path.dirname(self._current_path)
            parent_name = os.path.basename(parent) or parent
            mtime = format_datetime_ts(os.path.getmtime(parent)) if os.path.exists(parent) else "未知"
            detail.update(
                f"文件夹名: {parent_name}\n"
                f"路径: {parent}\n"
                f"修改时间: {mtime}"
            )
            return

        full_path = os.path.join(self._current_path, item_id)
        is_dir = os.path.isdir(full_path)
        is_video = not is_dir and os.path.splitext(item_id)[1].lower() in VIDEO_EXTS

        if is_video:
            meta = _probe_video_metadata(full_path)
            fs = os.path.getsize(full_path) if os.path.isfile(full_path) else 0
            mtime = format_datetime_ts(os.path.getmtime(full_path)) if os.path.exists(full_path) else "未知"
            lines = [
                f"文件名: {item_id}",
                f"路径: {full_path}",
            ]
            if meta:
                lines += [
                    f"帧率: {meta.get('fps', 0):.2f} fps",
                    f"宽度: {meta['width']}",
                    f"高度: {meta['height']}",
                    f"总帧数: {meta.get('frame_count', 0)}",
                    f"时长: {_format_duration(meta.get('duration', 0) or 0)}",
                ]
            lines += [
                f"修改时间: {mtime}",
                f"大小: {format_file_size(fs)}",
            ]
            detail.update("\n".join(lines))
        elif is_dir:
            mtime = format_datetime_ts(os.path.getmtime(full_path)) if os.path.exists(full_path) else "未知"
            detail.update(
                f"文件夹名: {item_id}\n"
                f"路径: {full_path}\n"
                f"修改时间: {mtime}"
            )
        else:
            fs = os.path.getsize(full_path)
            mtime = format_datetime_ts(os.path.getmtime(full_path)) if os.path.exists(full_path) else "未知"
            detail.update(
                f"文件名: {item_id}\n"
                f"路径: {full_path}\n"
                f"修改时间: {mtime}\n"
                f"大小: {format_file_size(fs)}"
            )

    # ── 文件列表刷新 ──

    # 驱动器列表视图的哨兵路径
    _DRIVES_SENTINEL = "Drives:\\"

    async def _refresh_files(self, and_focus: bool = False):
        file_list = self.query_one("#file-list", ListView)
        await file_list.clear()

        # 驱动器列表视图
        if self._current_path == self._DRIVES_SENTINEL:
            self.query_one("#current-path", Static).update("当前目录: 驱动器")
            self.query_one("#path-input", Input).value = self._DRIVES_SENTINEL
            for drive_name, drive_path in list_drives():
                item = ListItem(
                    Label(f"📁 {drive_name}"),
                    id=_safe_id(drive_name),
                    classes="dir-item",
                )
                item._entry_name = drive_path
                file_list.append(item)
            if and_focus and file_list:
                file_list.index = 0
                file_list.focus()
            return

        try:
            self.query_one("#current-path", Static).update(
                f"当前目录: {self._current_path}"
            )
        except Exception:
            pass
        try:
            dirs, files = sorted_entries(self._current_path, video_only=not self._show_all)
        except PermissionError:
            safe_notify(self,"没有访问此目录的权限", severity="error")
            return
        except Exception as e:
            safe_notify(self,f"无法读取目录: {e}", severity="error")
            return

        has_parent = self._current_path != self._DRIVES_SENTINEL
        if has_parent:
            parent_item = ListItem(Label("📁 .."), id="parent-dir", classes="dir-item")
            parent_item._entry_name = ".."
            file_list.append(parent_item)
        for _sort_key, display_name, _is_dir in dirs:
            item = ListItem(
                Label(f"📁 {display_name}"),
                id=_safe_id(display_name),
                classes="dir-item",
            )
            item._entry_name = display_name
            file_list.append(item)
        for _sort_key, display_name, _is_dir in files:
            ext = os.path.splitext(display_name)[1].lower()
            icon = "🎞️" if ext in VIDEO_EXTS else "📄"
            item = ListItem(
                Label(f"{icon} {display_name}"),
                id=_safe_id(display_name),
                classes="file-item",
            )
            item._entry_name = display_name
            file_list.append(item)

        if and_focus and file_list:
            file_list.index = 0
            file_list.focus()

    # ── 导航 ──

    async def _navigate_to(self, target: str):
        if target == "..":
            if self._current_path == self._DRIVES_SENTINEL:
                return  # 已在驱动器列表，不能再返回
            parent = os.path.dirname(self._current_path)
            if parent == self._current_path:
                # 已在驱动器根目录，返回驱动器列表
                self._current_path = self._DRIVES_SENTINEL
            elif os.path.isdir(parent):
                self._current_path = parent
            else:
                return
        else:
            full = target if os.path.isabs(target) else os.path.join(self._current_path, target)
            if os.path.isdir(full):
                self._current_path = full
            else:
                return
        self.query_one("#path-input", Input).value = self._current_path
        await self._refresh_files(and_focus=True)

    async def _go_up(self):
        parent = os.path.dirname(self._current_path)
        if os.path.isdir(parent):
            await self._navigate_to(parent)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "select-btn":
            await self._confirm()
        elif bid == "cancel-btn":
            self._cancel()
        elif bid == "go-up-btn":
            await self._go_up()
        elif bid == "go-btn":
            await self._on_path_go(self.query_one("#path-input", Input).value)
            self._focus_file_list()
            self._active_zone = "file_list"
            self._update_keybar()

    async def _on_path_go(self, path: str):
        path = path.strip()
        if not path:
            return
        expanded = os.path.expanduser(path)
        abs_path = os.path.abspath(expanded)
        if os.path.isdir(abs_path):
            await self._navigate_to(abs_path)
        elif os.path.isfile(abs_path):
            self._current_path = os.path.dirname(abs_path)
            await self._refresh_files(and_focus=True)
        else:
            safe_notify(self,"路径不存在", severity="error")

    async def _confirm(self):
        file_list = self.query_one("#file-list", ListView)
        if file_list.index is not None and file_list.index < len(file_list):
            item = file_list.children[file_list.index]
            item_class = getattr(item, "classes", "")
            if "dir-item" in item_class:
                return
            entry_name = getattr(item, "_entry_name", None)
            sel = os.path.join(self._current_path, entry_name) if entry_name else ""

            if sel and os.path.isfile(sel):
                meta = _probe_video_metadata(sel)
                if meta is None or meta.get("duration", 0) <= 0:
                    safe_notify(self,"无法读取有效视频时长，请选择有效的视频文件", severity="warning")
                    return

            self._save_last_dir()
            self.dismiss(sel)
        else:
            self._cancel()

    def _cancel(self):
        self.dismiss(None)

    def _save_last_dir(self):
        path = self._current_path
        try:
            if path and os.path.isdir(path):
                _write_config_value(LAST_VIDEO_DIR_KEY, path)
        except Exception:
            pass