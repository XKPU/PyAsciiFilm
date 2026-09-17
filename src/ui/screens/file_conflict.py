from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static
from textual.containers import Vertical, Horizontal


class FileConflictScreen(Screen):
    """文件已存在确认：替换 / 更改名称 / 取消"""

    CSS = """
    Screen { align: center middle; }
    #dlg { width: 60; height: auto; border: round $accent; padding: 1 2; }
    #dlg > Static { height: auto; margin: 0 0 1 0; }
    #dlg > Horizontal { height: auto; margin: 1 0 0 0; align: center middle; }
    #dlg > Horizontal > Button { margin: 0 1; }
    #hint { color: $text-muted; text-style: bold; height: 1; margin: 1 0 0 0; }
    """

    def __init__(self, filename):
        super().__init__()
        self._filename = filename

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(f"文件已存在: {self._filename}"),
            Static("请选择操作:", markup=False),
            Horizontal(
                Button("替换", id="replace", variant="primary"),
                Button("更改名称", id="rename", variant="default"),
                Button("取消", id="cancel_conflict", variant="default"),
            ),
            Static("R 替换 | N 改名 | Esc/C 取消", id="hint"),
            id="dlg",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "replace":
            self.dismiss("replace")
        elif event.button.id == "rename":
            self.dismiss("rename")
        else:
            self.dismiss(None)

    async def on_key(self, event) -> None:
        if event.key in ("r", "R"):
            event.stop()
            self.dismiss("replace")
        elif event.key in ("n", "N"):
            event.stop()
            self.dismiss("rename")
        elif event.key in ("c", "C", "escape"):
            event.stop()
            self.dismiss(None)