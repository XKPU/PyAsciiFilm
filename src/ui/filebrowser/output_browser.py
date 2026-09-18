# TUI 输出目录选择器
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
    sorted_entries,
    format_datetime_ts as _format_datetime_ts,
    user_dirs as _user_dirs, list_drives as _list_drives,
    VIDEO_EXTS,
    LAST_EXPORT_DIR_KEY,
)
from ..widgets import KeyBar, safe_notify
from .browser_nav import BrowserNav
from .browser_config import ODB_CSS, ODB_ID_TO_ZONE, ODB_ZONE_HINTS
from ..screens._helpers import _load_last_export_dir


def _safe_id(name: str) -> str:
    """将任意字符串转为合法的 Textual id"""
    import re as _re, hashlib
    clean = _re.sub(r"[^a-zA-Z0-9]", "-", name).strip("-")
    if not clean:
        clean = "x"
    if clean[0].isdigit():
        clean = "i" + clean
    h = hashlib.md5(name.encode("utf-8")).hexdigest()[:6]
    return f"{clean}-{h}"


def _save_last_export_dir(path):
    try:
        if path and os.path.isdir(path):
            _write_config_value(LAST_EXPORT_DIR_KEY, path)
    except Exception:
        pass


def _sorted_entries(path, video_only=True):
    dirs, files = sorted_entries(path, video_only=video_only, hide_hidden=True)
    return [(k, n) for k, n, _ in dirs], [(k, n) for k, n, _ in files]


class OutputDirBrowser(Screen, BrowserNav):
    """TUI 输出目录浏览器"""

    BINDINGS: list = []
    CSS = ODB_CSS
    _ID_TO_ZONE = ODB_ID_TO_ZONE
    _ZONE_HINTS = ODB_ZONE_HINTS

    def __init__(self, initial=None, filename_hint="", ext="mp4"):
        super().__init__()
        if initial and os.path.isdir(initial):
            self._current_path = initial
        elif initial and os.path.isfile(initial):
            self._current_path = os.path.dirname(initial)
        else:
            saved = _load_last_export_dir()
            self._current_path = saved or os.getcwd()
        self._filename_hint = filename_hint
        self._ext = ext
        self._dir_names: list[str] = []
        self._file_names: list[str] = []
        self._sidebar_paths: list[str] = []
        self._active_zone = "file_list"
        self._destroyed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="browser-container"):
            with Horizontal(id="path-bar"):
                yield Input(value=self._current_path, id="path-input",
                            placeholder="输入路径后回车")
                yield Button("转到", id="go-btn", variant="default")
                yield Button("上一级", id="go-up-btn", variant="default")

            with Horizontal(id="main-area"):
                with Vertical(id="sidebar"):
                    yield Static("快捷访问", id="sidebar-title")
                    yield ListView(id="sidebar-list")

                with Vertical(id="file-area"):
                    yield Static("", id="current-path")
                    with Horizontal(id="file-detail-row"):
                        with Vertical(id="file-list-col"):
                            yield Static("名称", id="file-header")
                            yield ListView(id="file-list")
                        with Vertical(id="detail-panel"):
                            yield Static("详细信息", id="detail-header")
                            yield Static("", id="detail-content")

            with Horizontal(id="action-bar"):
                yield Input(value=self._filename_hint, id="filename-input",
                            placeholder="导出文件名（不含扩展名）")
                with Vertical(id="filter-info"):
                    yield Static("过滤: 仅视频", id="show-all-indicator", markup=False)
                    yield Static(f".{self._ext}", id="ext-hint", markup=False)
                yield Button("选择", id="select-btn", variant="primary")
                yield Button("取消", id="cancel-btn", variant="default")

        yield KeyBar()

    async def on_mount(self) -> None:
        self._update_keybar()
        self._update_show_all_indicator()
        await self._populate_sidebar()
        self.call_after_refresh(self._deferred_refresh)

    def _deferred_refresh(self):
        if not self._destroyed:
            asyncio.create_task(self._refresh_files(and_focus=True))

    def on_unmount(self) -> None:
        self._destroyed = True

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
        elif zone == "filename_input":
            self._focus_file_list()
            self._active_zone = "file_list"
            self._update_keybar()
        elif zone == "bottom_buttons":
            self._confirm()
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
        file_list = self.query_one("#file-list", ListView)
        if file_list.index is not None and file_list.index < len(file_list):
            item = file_list.children[file_list.index]
            item_class = getattr(item, "classes", "")
            if "dir-item" in item_class:
                entry_name = getattr(item, "_entry_name", None)
                if entry_name:
                    await self._navigate_to(entry_name)
                return
            self._auto_select_current_file()

    async def _select_current_sidebar_item(self):
        sidebar = self.query_one("#sidebar-list", ListView)
        if sidebar.index is not None:
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

    def _auto_select_current_file(self) -> None:
        file_list = self.query_one("#file-list", ListView)
        if file_list.index is not None and 0 <= file_list.index < len(file_list):
            item = file_list.children[file_list.index]
            item_class = getattr(item, "classes", "")
            if "file-item" in item_class:
                self._fill_filename_from_selected()

    def _fill_filename_from_selected(self):
        file_list = self.query_one("#file-list", ListView)
        if file_list.index is not None and file_list.index < len(file_list):
            item = file_list.children[file_list.index]
            item_class = getattr(item, "classes", "")
            if "file-item" in item_class:
                entry_name = getattr(item, "_entry_name", None)
                name = os.path.splitext(entry_name)[0] if entry_name else ""
                try:
                    self.query_one("#filename-input", Input).value = name
                except Exception:
                    pass

    def _focus_sidebar(self) -> None:
        try:
            lv = self.query_one("#sidebar-list", ListView)
            if lv.index is None and len(lv) > 0:
                lv.index = 0
            lv.focus()
        except Exception:
            pass

    def _focus_file_list(self) -> None:
        try:
            lv = self.query_one("#file-list", ListView)
            if lv.index is None and len(lv) > 0:
                lv.index = 0
            lv.focus()
        except Exception:
            pass

    def _focus_path(self) -> None:
        try:
            self.query_one("#path-input", Input).focus()
        except Exception:
            pass

    def _focus_bottom_buttons(self) -> None:
        try:
            self.query_one("#select-btn", Button).focus()
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
            self.query_one("#go-up-btn", Button).focus()
        except Exception:
            pass

    def _focus_path_go_btn(self) -> None:
        try:
            self.query_one("#go-btn", Button).focus()
        except Exception:
            pass

    def _focus_path_up_btn(self) -> None:
        try:
            self.query_one("#go-up-btn", Button).focus()
        except Exception:
            pass

    def _focus_filename_input(self) -> None:
        try:
            self.query_one("#filename-input", Input).focus()
        except Exception:
            pass

    async def _populate_sidebar(self):
        sidebar = self.query_one("#sidebar-list", ListView)
        await sidebar.clear()
        try:
            for label, path in _user_dirs():
                safe_id = "dir-" + path.replace("\\", "-").replace(":", "-").replace(" ", "-").replace("/", "-")
                sidebar.append(ListItem(Label(f"📁 {label}"), id=safe_id, classes="sidebar-item"))
                sidebar.children[-1]._nav_path = path
            sep = ListItem(Label("─────────────"), id="sep", classes="sidebar-sep")
            sep._nav_path = None
            sep.disabled = True
            sidebar.append(sep)
            for drive_name, drive_path in _list_drives():
                safe_id = "drv-" + drive_path.replace("\\", "-").replace(":", "-").replace(" ", "-").replace("/", "-")
                sidebar.append(ListItem(Label(f"{drive_name}"), id=safe_id, classes="sidebar-item"))
                sidebar.children[-1]._nav_path = drive_path
        except Exception as e:
            _log_error(f"加载侧栏失败: {e}")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "file-list":
            await self._select_current_file_item()
        elif event.list_view.id == "sidebar-list":
            await self._select_current_sidebar_item()

    async def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id == "file-list" and event.item is not None:
            entry_name = getattr(event.item, "_entry_name", None)
            self._update_detail_panel(entry_name)

    def _update_detail_panel(self, item_id: str) -> None:
        try:
            detail = self.query_one("#detail-content", Static)
            header = self.query_one("#detail-header", Static)
        except Exception:
            return
        if not item_id:
            detail.update("")
            header.update("详细信息")
            return

        full_path = os.path.join(self._current_path, item_id)
        is_dir = os.path.isdir(full_path)

        if is_dir:
            mtime = _format_datetime_ts(os.path.getmtime(full_path)) if os.path.exists(full_path) else "未知"
            header.update(f"📁 {item_id}")
            detail.update(
                f"文件夹名: {item_id}\n"
                f"路径: {full_path}\n"
                f"修改时间: {mtime}"
            )
        else:
            header.update(f"�� {item_id}")
            if item_id == "parent-dir":
                parent = os.path.dirname(self._current_path)
                parent_name = os.path.basename(parent) or parent
                mtime = _format_datetime_ts(os.path.getmtime(parent)) if os.path.exists(parent) else "未知"
                detail.update(
                    f"文件夹名: {parent_name}\n"
                    f"路径: {parent}\n"
                    f"修改时间: {mtime}"
                )
            else:
                detail.update("")

    # 驱动器列表视图的哨兵路径
    _DRIVES_SENTINEL = "Drives:\\"

    async def _refresh_files(self, and_focus=False):
        if self._destroyed:
            return
        file_list = self.query_one("#file-list", ListView)
        await file_list.clear()

        # 驱动器列表视图
        if self._current_path == self._DRIVES_SENTINEL:
            self.query_one("#current-path", Static).update("当前：驱动器")
            self.query_one("#path-input", Input).value = self._DRIVES_SENTINEL
            for drive_name, drive_path in _list_drives():
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
                f"当前：{self._current_path}"
            )
        except Exception:
            pass
        try:
            dirs, files = _sorted_entries(self._current_path, video_only=not self._show_all)
        except Exception as e:
            safe_notify(self,f"无法读取目录：{e}", severity="error")
            return

        has_parent = self._current_path != self._DRIVES_SENTINEL
        self._dir_names = [os.path.basename(d) for d, _ in dirs]
        self._file_names = [os.path.basename(f) for f, _ in files]

        if has_parent:
            file_list.append(ListItem(Label("📁 .."), id="parent-dir", classes="dir-item"))

        for _, display_name in dirs:
            item = ListItem(Label(f"📁 {display_name}"), id=_safe_id(display_name), classes="dir-item")
            item._entry_name = display_name
            file_list.append(item)
        for _, display_name in files:
            ext = os.path.splitext(display_name)[1].lower()
            icon = "🎞️" if ext in VIDEO_EXTS else "📄"
            item = ListItem(Label(f"{icon} {display_name}"), id=_safe_id(display_name), classes="file-item")
            item._entry_name = display_name
            file_list.append(item)

        if and_focus and file_list:
            file_list.index = 0
            file_list.focus()

    async def _navigate_to(self, target: str):
        if self._destroyed:
            return
        if target == "..":
            if self._current_path == self._DRIVES_SENTINEL:
                return
            parent = os.path.dirname(self._current_path)
            if parent == self._current_path:
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
            self._confirm()
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
        else:
            safe_notify(self,"路径不存在", severity="error")

    def _confirm(self):
        filename = self.query_one("#filename-input", Input).value.strip()
        if not filename:
            safe_notify(self,"请输入文件名", severity="warning")
            return
        full_filename = f"{filename}.{self._ext}" if self._ext else filename
        target_path = os.path.join(self._current_path, full_filename)
        if os.path.exists(target_path):
            from ..screens.file_conflict import FileConflictScreen
            self.app.push_screen(
                FileConflictScreen(target_path),
                self._on_conflict_resolved
            )
        else:
            _save_last_export_dir(self._current_path)
            self.dismiss((self._current_path, filename))

    def _on_conflict_resolved(self, choice):
        if choice == "replace":
            filename = self.query_one("#filename-input", Input).value.strip()
            _save_last_export_dir(self._current_path)
            self.dismiss((self._current_path, filename))
        elif choice == "rename":
            filename = self.query_one("#filename-input", Input).value.strip()
            target_path = os.path.join(self._current_path, f"{filename}.{self._ext}")
            cnt = 1
            while os.path.exists(target_path):
                target_path = os.path.join(
                    self._current_path,
                    f"{filename}_{cnt}.{self._ext}"
                )
                cnt += 1
            _save_last_export_dir(self._current_path)
            self.dismiss((self._current_path, os.path.splitext(os.path.basename(target_path))[0]))
        else:
            self._cancel()

    def _cancel(self):
        self.dismiss(None)