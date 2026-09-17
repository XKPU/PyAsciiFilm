# UI 控件

import unicodedata

from textual.binding import Binding
from textual.widgets import Select, Static


class PlainSelect(Select, inherit_bindings=False):
    """普通下拉菜单：不响应↑/↓，仅Enter/Space展开"""

    BINDINGS = [
        Binding("enter,space", "show_overlay", "展开菜单", show=False),
    ]


def _display_width(text: str) -> int:
    """文本终端显示宽度（全角占2列）"""
    w = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ("W", "F") else 1
    return w


def safe_notify(screen, message, **kwargs):
    """显示通知并延迟刷新屏幕，修复 overlay 渲染缺字问题"""
    screen.app.notify(message, **kwargs)
    screen.set_timer(0.15, screen.refresh)


class KeyBar(Static):
    """快捷键提示栏（超宽时自动横向滚动）"""

    SCROLL_INTERVAL = 0.15
    GAP = "     "

    def __init__(self):
        super().__init__()
        self._full_text: str = ""
        self._scroll_pos: int = 0
        self._timer = None
        self._stopped: bool = False

    def set_hint(self, text: str) -> None:
        if self._stopped:
            return
        self._full_text = text
        self._scroll_pos = 0
        self._try_display()

    def _inner_width(self) -> int:
        w = self.size.width if self.size else 0
        return max(1, w) if w > 0 else 0

    def _try_display(self) -> None:
        inner_w = self._inner_width()
        if inner_w <= 0:
            return
        text_w = _display_width(self._full_text)
        if text_w <= inner_w:
            super().update(self._full_text)
            self._stop_timer()
        else:
            self._start_timer()
            self._do_scroll()

    def _start_timer(self) -> None:
        if self._timer is None:
            self._timer = self.set_interval(self.SCROLL_INTERVAL, self._do_scroll)

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _do_scroll(self) -> None:
        if self._stopped:
            return
        inner_w = self._inner_width()
        if inner_w <= 0:
            return
        text_w = _display_width(self._full_text)
        if text_w <= inner_w:
            super().update(self._full_text)
            self._stop_timer()
            return

        ring: list[tuple[str, int]] = []
        for ch in self._full_text:
            cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            ring.append((ch, cw))
        for ch in self.GAP:
            ring.append((ch, 1))
        period_chars = len(ring)
        period_w = sum(cw for _, cw in ring)

        offset_w = self._scroll_pos % period_w

        col = 0
        char_idx = 0
        while char_idx < period_chars and col + ring[char_idx][1] <= offset_w:
            col += ring[char_idx][1]
            char_idx += 1

        result: list[str] = []
        total_w = 0
        first_char_w = 1
        if char_idx < period_chars:
            first_char_w = ring[char_idx][1]
        for i in range(period_chars):
            ch, cw = ring[(char_idx + i) % period_chars]
            if total_w + cw > inner_w:
                break
            result.append(ch)
            total_w += cw

        super().update("".join(result))
        self._scroll_pos += first_char_w

    def on_resize(self, event) -> None:
        self._try_display()

    def on_unmount(self) -> None:
        self._stopped = True
        self._stop_timer()