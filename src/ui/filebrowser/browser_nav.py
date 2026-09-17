# 浏览器通用键盘导航
import asyncio

from textual.events import Key
from textual.widgets import Static

from ..widgets import KeyBar


class BrowserNav:
    """浏览器通用键盘导航"""

    _show_all = False

    async def _browser_on_key(self, event: Key, zone_info: dict):  # noqa: C901
        key = event.key
        zone = zone_info
        if key == "ctrl+a":
            event.stop()
            self._toggle_show_all()
            return

        if zone in ("path_input", "filename_input"):
            if key in ("ctrl+l",):
                event.stop()
                if zone == "path_input":
                    self._focus_file_list()
                    self._active_zone = "file_list"
                else:
                    self._focus_path()
                    self._active_zone = "path_input"
                self._update_keybar()
                return
            if key in ("ctrl+n",):
                event.stop()
                if zone == "filename_input":
                    self._focus_file_list()
                    self._active_zone = "file_list"
                elif hasattr(self, "_focus_filename_input"):
                    self._focus_filename_input()
                    self._active_zone = "filename_input"
                self._update_keybar()
                return
            if key in ("ctrl+b",):
                event.stop()
                self._focus_bottom_buttons()
                self._active_zone = "bottom_buttons"
                self._update_keybar()
                return
            if key in ("ctrl+u",):
                event.stop()
                self._focus_path_buttons()
                self._active_zone = "path_buttons"
                self._update_keybar()
                return
            return

        if zone == "path_buttons":
            if key in ("left", "h"):
                event.stop()
                foc = self.app.focused
                if foc and foc.id == "go-btn":
                    self._focus_path_up_btn()
                else:
                    self._focus_path_go_btn()
                return
            if key in ("right", "l"):
                event.stop()
                foc = self.app.focused
                if foc and foc.id == "go-up-btn":
                    self._focus_path_go_btn()
                else:
                    self._focus_path_up_btn()
                return
            if key in ("up", "down", "k", "j"):
                event.stop()
                self._focus_file_list()
                self._active_zone = "file_list"
                self._update_keybar()
                return
            if key in ("ctrl+u",):
                event.stop()
                self._focus_file_list()
                self._active_zone = "file_list"
                self._update_keybar()
                return

        if zone == "bottom_buttons":
            if key in ("left", "h"):
                event.stop()
                foc = self.app.focused
                if foc and foc.id == "cancel-btn":
                    self._focus_select_btn()
                else:
                    self._focus_cancel_btn()
                return
            if key in ("right", "l"):
                event.stop()
                foc = self.app.focused
                if foc and foc.id == "select-btn":
                    self._focus_cancel_btn()
                else:
                    self._focus_select_btn()
                return
            if key in ("ctrl+b",):
                event.stop()
                self._focus_file_list()
                self._active_zone = "file_list"
                self._update_keybar()
                return

        if zone in ("file_list", "sidebar") and key in ("up", "down", "k", "j"):
            return

        if key in ("shift+tab", "tab"):
            event.stop()
            if key == "shift+tab":
                self._focus_file_list()
                self._active_zone = zone
                return
            if zone == "file_list":
                self._focus_path()
                self._active_zone = "path_input"
            elif zone == "sidebar":
                self._focus_file_list()
                self._active_zone = "file_list"
            elif zone == "path_input":
                self._focus_bottom_buttons()
                self._active_zone = "bottom_buttons"
            elif zone == "bottom_buttons":
                self._focus_path_buttons()
                self._active_zone = "path_buttons"
            elif zone == "path_buttons":
                self._focus_file_list()
                self._active_zone = "file_list"
            else:
                self._focus_file_list()
                self._active_zone = "file_list"
            self._update_keybar()
            return

        if key in ("ctrl+b",):
            event.stop()
            self._focus_bottom_buttons()
            self._active_zone = "bottom_buttons"
            self._update_keybar()
            return

        if key in ("ctrl+u",):
            event.stop()
            self._focus_path_buttons()
            self._active_zone = "path_buttons"
            self._update_keybar()
            return

        if key in ("ctrl+l",):
            event.stop()
            self._focus_path()
            self._active_zone = "path_input"
            self._update_keybar()
            return

        if key in ("escape",):
            event.stop()
            self._cancel()
            return

        if key in ("backspace", "delete"):
            event.stop()
            if zone in ("file_list", "sidebar", "path_buttons"):
                asyncio.create_task(self._go_up())
            return

        if key == "enter":
            await self._browser_on_enter(event, zone)
            return

        nav_map = self._browser_nav_map()
        if key in nav_map:
            target, target_zone = nav_map[key]
            event.stop()
            target()
            self._active_zone = target_zone
            self._update_keybar()
            return

    def _browser_on_focus(self, event):
        widget = event.widget
        if widget is None:
            return
        fid = getattr(widget, "id", "") or ""
        zone = self._ID_TO_ZONE.get(fid)
        if zone:
            self._active_zone = zone
            self._update_keybar()

    def _browser_on_click(self, event):
        widget = self.app.focused
        if widget is None:
            return
        fid = getattr(widget, "id", "") or ""
        zone = self._ID_TO_ZONE.get(fid)
        if zone:
            self._active_zone = zone
            self._update_keybar()

    def _update_keybar(self):
        hints = self._ZONE_HINTS.get(self._active_zone, "")
        try:
            self.query_one(KeyBar).set_hint(hints)
        except Exception:
            pass

    def _update_show_all_indicator(self) -> None:
        try:
            label = "全部" if self._show_all else "仅视频"
            self.query_one("#show-all-indicator", Static).update(f"过滤: {label}")
        except Exception:
            pass

    def _toggle_show_all(self) -> None:
        self._show_all = not self._show_all
        self._update_show_all_indicator()
        asyncio.create_task(self._refresh_files(and_focus=True))