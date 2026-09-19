
# ── VideoFileBrowser 配置 ──

FB_ID_TO_ZONE = {
    "file-list": "file_list",
    "sidebar-list": "sidebar",
    "path-input": "path_input",
    "select-btn": "bottom_buttons",
    "cancel-btn": "bottom_buttons",
    "go-up-btn": "path_buttons",
    "go-btn": "path_buttons",
}

FB_ZONE_HINTS = {
    "file_list": (
        "Esc 返回菜单 | Enter 进入目录/选定文件 | "
        "Backspace/Delete 返回上一级 | \u2190 聚焦快速访问 | "
        "Ctrl+L 路径栏 | Ctrl+B 选择按钮 | Ctrl+U 路径按钮 | "
        "Ctrl+A 全部/视频"
    ),
    "sidebar": (
        "Esc 返回菜单 | Enter 跳转至指定路径 | "
        "Backspace/Delete 返回上一级 | \u2190/\u2192 切换文件列表 | "
        "Ctrl+L 路径栏 | Ctrl+B 选择按钮 | Ctrl+U 路径按钮 | "
        "Ctrl+A 全部/视频"
    ),
    "path_input": (
        "Esc 返回菜单 | Enter 跳转至路径并聚焦文件列表 | "
        "Ctrl+L 返回文件列表 | Ctrl+B 选择按钮 | Ctrl+U 路径按钮 | "
        "Ctrl+A 全部/视频"
    ),
    "bottom_buttons": (
        "Esc 返回菜单 | Enter 执行选定操作 | "
        "\u2190/\u2192 切换按钮 | \u2191 聚焦文件列表 | "
        "Ctrl+B 返回文件列表 | Ctrl+U 路径按钮 | "
        "Ctrl+A 全部/视频"
    ),
    "path_buttons": (
        "Esc 返回菜单 | Enter 执行选定操作 | "
        "\u2190/\u2192 切换按钮 | \u2193 聚焦文件列表 | "
        "Ctrl+L 路径栏 | Ctrl+B 选择按钮 | Ctrl+U 返回文件列表 | "
        "Ctrl+A 全部/视频"
    ),
}

FB_CSS = """
VideoFileBrowser {
    align: center middle;
}

#browser-container {
    width: 90%;
    height: 90%;
    border: round $accent;
    background: $surface;
}

/* --- 路径栏 --- */
#path-bar {
    height: 4;
    padding: 0 1;
    border-bottom: solid $border;
    align: center middle;
}
#path-input {
    width: 1fr;
}
/* 默认边框使按钮视觉可辨；min-height:4 让内容区变成 2 行，
   文字居中在第 1 行，配合终端基线偏移抵消后视觉上正好居中 */
#path-bar Button {
    min-height: 4;
    margin: 0 1;
}
#go-up-btn {
    width: 8;
}
#go-btn {
    width: 6;
}

/* --- 主区域：快捷访问 + 文件列表 --- */
#main-area {
    height: 1fr;
}

/* 左侧快捷访问 */
#sidebar {
    width: 18;
    height: 100%;
    border-right: solid $border;
    background: $panel;
}
#sidebar-title {
    text-style: bold;
    padding: 0 0 0 1;
    height: 1;
}
#sidebar-list {
    height: 1fr;
}
.sidebar-item {
    padding: 0 0 0 1;
}
.sidebar-item:hover {
    background: $accent 20%;
}
.sidebar-item > Label {
    width: 100%;
}
/* 侧栏分隔线（不可交互） */
#sidebar-list > ListItem#sep {
    color: $border;
    background: transparent;
    padding: 0 0 0 1;
}
#sidebar-list > ListItem#sep:hover {
    background: transparent;
}
#sidebar-list > ListItem#sep > Label {
    color: $border;
}

/* 右侧文件列表 */
#file-area {
    height: 100%;
    width: 1fr;
}
#file-detail-row {
    height: 1fr;
}
#file-list-col {
    width: auto;
    min-width: 25;
}
#detail-panel {
    width: 1fr;
    min-width: 36;
    border-left: solid $border;
    background: $panel;
    display: block;
}
#detail-header {
    height: 1;
    padding: 0 1;
    text-style: bold;
    background: $boost;
}
#detail-content {
    height: 1fr;
    padding: 0 1;
    overflow-y: auto;
}
#file-header {
    height: 1;
    padding: 0 1;
    text-style: bold;
    background: $boost;
}
#file-list {
    height: 1fr;
}
/* 当前路径显示 */
#current-path {
    height: 1;
    padding: 0 1;
    color: $text-muted;
    border-bottom: solid $border;
}

/* 文件列表项样式 */
.dir-item {
    padding: 0 1;
}
.dir-item:hover {
    background: $accent 20%;
}
.dir-item > Label {
    width: 100%;
    color: $warning;
}

.file-item {
    padding: 0 1;
}
.file-item:hover {
    background: $accent 20%;
}
.file-item > Label {
    width: 100%;
}

/* --- 底部按钮栏 --- */
#action-bar {
    height: 4;
    padding: 0 1;
    border-top: solid $border;
    align: center middle;
}
#action-bar Button {
    min-height: 4;
}
#selected-label {
    width: 1fr;
    color: $text-muted;
}
#show-all-indicator {
    width: auto;
    padding: 0 1;
    color: $success;
    text-style: bold;
}
#select-btn {
    width: 12;
}
#cancel-btn {
    width: 12;
}

KeyBar {
    height: 1;
    background: $primary 10%;
    color: $text;
    padding: 0 1;
    text-style: bold;
    dock: bottom;
}
"""

# ── OutputDirBrowser 配置 ──

ODB_ID_TO_ZONE = {
    "file-list": "file_list",
    "sidebar-list": "sidebar",
    "path-input": "path_input",
    "filename-input": "filename_input",
    "select-btn": "bottom_buttons",
    "cancel-btn": "bottom_buttons",
    "go-up-btn": "path_buttons",
    "go-btn": "path_buttons",
}

ODB_ZONE_HINTS = {
    "file_list": (
        "Esc 取消 | Enter 进入目录/选择文件名 | "
        "Backspace/Delete 返回上级 | \u2190 聚焦快速访问 | "
        "Ctrl+L 路径栏 | Ctrl+N 文件名 | Ctrl+B 选择按钮 | Ctrl+U 路径按钮 | "
        "Ctrl+A 全部/视频"
    ),
    "sidebar": (
        "Esc 取消 | Enter 跳转 | "
        "Backspace/Delete 返回上级 | \u2192 聚焦文件列表 | "
        "Ctrl+L 路径栏 | Ctrl+N 文件名 | Ctrl+B 选择按钮 | "
        "Ctrl+A 全部/视频"
    ),
    "path_input": (
        "Esc 取消 | Enter 跳转至路径 | "
        "Ctrl+L 返回文件列表 | Ctrl+N 文件名 | Ctrl+B 选择按钮 | "
        "Ctrl+A 全部/视频"
    ),
    "filename_input": (
        "Esc 取消 | Enter 确认选择 | "
        "Ctrl+N 返回文件列表 | Ctrl+B 选择按钮 | "
        "Ctrl+A 全部/视频"
    ),
    "bottom_buttons": (
        "Esc 取消 | Enter 执行选定操作 | "
        "\u2190/\u2192 切换按钮 | \u2191 聚焦文件列表 | "
        "Ctrl+N 文件名 | Ctrl+B 返回文件列表 | "
        "Ctrl+A 全部/视频"
    ),
    "path_buttons": (
        "Esc 取消 | Enter 执行选定操作 | "
        "\u2190/\u2192 切换按钮 | \u2193 聚焦文件列表 | "
        "Ctrl+L 路径栏 | Ctrl+N 文件名 | "
        "Ctrl+A 全部/视频"
    ),
}

ODB_CSS = """
OutputDirBrowser {
    align: center middle;
}
#browser-container {
    width: 90%;
    height: 90%;
    border: round $accent;
    background: $surface;
}

/* --- 路径栏 --- */
#path-bar {
    height: 4;
    padding: 0 1;
    border-bottom: solid $border;
    align: center middle;
}
#path-input { width: 1fr; }
#path-bar Button {
    min-height: 4;
    margin: 0 1;
}
#go-up-btn { width: 8; }
#go-btn { width: 6; }

/* --- 主区域 --- */
#main-area { height: 1fr; }

#sidebar {
    width: 18;
    height: 100%;
    border-right: solid $border;
    background: $panel;
}
#sidebar-title {
    text-style: bold;
    padding: 0 0 0 1;
    height: 1;
}
#sidebar-list { height: 1fr; }
.sidebar-item { padding: 0 0 0 1; }
.sidebar-item:hover { background: $accent 20%; }
.sidebar-item > Label { width: 100%; }
#sidebar-list > ListItem#sep {
    color: $border;
    background: transparent;
    padding: 0 0 0 1;
}
#sidebar-list > ListItem#sep:hover { background: transparent; }
#sidebar-list > ListItem#sep > Label { color: $border; }

#file-area { height: 100%; width: 1fr; }
#file-detail-row { height: 1fr; }
#file-list-col { width: auto; min-width: 25; }
#detail-panel {
    width: 1fr;
    min-width: 36;
    border-left: solid $border;
    background: $panel;
    display: block;
}
#detail-header {
    height: 1;
    padding: 0 1;
    text-style: bold;
    background: $boost;
}
#detail-content {
    height: 1fr;
    padding: 0 1;
    overflow-y: auto;
}
#file-header {
    height: 1;
    padding: 0 1;
    text-style: bold;
    background: $boost;
}
#file-list { height: 1fr; }
#current-path {
    height: 1;
    padding: 0 1;
    color: $text-muted;
    border-bottom: solid $border;
}

/* 文件列表项样式 */
.dir-item { padding: 0 1; }
.dir-item:hover { background: $accent 20%; }
.dir-item > Label { width: 100%; color: $warning; }
.file-item { padding: 0 1; }
.file-item:hover { background: $accent 20%; }
.file-item > Label { width: 100%; }

/* 底部输入栏 */
#filename-bar {
    height: 4;
    padding: 0 1;
    border-bottom: solid $border;
    align: center middle;
}
#filename-bar > Label { width: 8; }
#filename-input { width: 1fr; }

/* 底部按钮栏 */
#action-bar {
    height: 4;
    padding: 0 1;
    border-top: solid $border;
    align: center middle;
}
#action-bar Button { min-height: 4; }
#selected-label { width: 1fr; color: $text-muted; }
#filter-info {
    width: auto;
    height: auto;
    align: center middle;
}
#show-all-indicator {
    width: auto;
    padding: 0 1;
    color: $success;
    text-style: bold;
}
#ext-hint {
    width: auto;
    padding: 0 1;
    color: $warning;
    text-style: bold;
}
#select-btn { width: 12; }
#cancel-btn { width: 12; }

KeyBar {
    height: 1;
    background: $primary 10%;
    color: $text;
    padding: 0 1;
    text-style: bold;
    dock: bottom;
}
"""