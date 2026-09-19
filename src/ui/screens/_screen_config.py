# 屏幕共享配置（快捷键提示等）

EXPORT_ID_TO_ZONE = {
    "reselect": "src_area",
    "char_w": "char_size",
    "char_h": "char_size",
    "lock": "lock",
    "fps": "fps",
    "fps_up": "fps",
    "fps_down": "fps",
    "fmt": "fmt",
    "usage": "usage",
    "decode_mode": "decode",
    "encode_mode": "encode",
    "out_path": "out_path",
    "browse_dir": "out_path",
    "color": "color",
    "ok": "buttons",
    "cancel": "buttons",
}

_EXPORT_INLINE = {
    "char_w": "Ctrl+W",
    "char_h": "Ctrl+K",
    "lock": "Ctrl+L",
    "fps": "Ctrl+F",
    "fmt": "Ctrl+G",
    "usage": "Ctrl+U",
    "decode_mode": "Ctrl+D",
    "encode_mode": "Ctrl+E",
    "out_path": "Ctrl+O",
    "color": "Ctrl+T",
    "reselect": "Ctrl+R",
    "browse_dir": "Ctrl+B",
    "ok": "Ctrl+S",
}

EXPORT_ZONE_HINTS = {
    "src_area": "Esc 返回 | Tab 切换",
    "char_size": "Esc 返回 | Tab 切换",
    "lock": "Esc 返回 | Tab 切换",
    "fps": "Esc 返回 | Tab 切换",
    "fmt": "Esc 返回 | Tab 切换 | Enter 选取",
    "usage": "Esc 返回 | Tab 切换",
    "decode": "Esc 返回 | Tab 切换 | Enter 选取",
    "encode": "Esc 返回 | Tab 切换 | Enter 选取",
    "out_path": "Esc 返回 | Tab 切换",
    "color": "Esc 返回 | Tab 切换",
    "buttons": "Esc 返回 | Enter 执行",
}

PLAY_ID_TO_ZONE = {
    "reselect": "src_area",
    "fps": "fps",
    "usage": "usage",
    "decode_mode": "decode",
    "color": "color",
    "ok": "buttons",
    "cancel": "buttons",
}

_PLAY_INLINE = {
    "fps": "Ctrl+F",
    "usage": "Ctrl+U",
    "decode_mode": "Ctrl+D",
    "color": "Ctrl+T",
    "reselect": "Ctrl+R",
    "ok": "Ctrl+S",
}

PLAY_ZONE_HINTS = {
    "src_area": "Esc 返回 | Tab 切换",
    "fps": "Esc 返回 | Tab 切换",
    "usage": "Esc 返回 | Tab 切换",
    "decode": "Esc 返回 | Tab 切换 | Enter 选取",
    "color": "Esc 返回 | Tab 切换",
    "buttons": "Esc 返回 | Enter 执行",
}

EXPORT_CSS = """
    Screen { align: center top; }
    #scroller { width: 100%; height: 1fr; }
    #panel { width: 100%; height: auto; padding: 1 2; }
    #panel > Horizontal { height: auto; margin: 1 0; }
    Label { width: auto; }
    Input { width: 1fr; }
    Select { width: 1fr; }
    /* srcinfo 必须限宽：Static 默认撑满整行，会把右侧"重新选择"
       按钮挤出屏幕（实测各终端宽度下都被裁掉，鼠标点不到） */
    #srcinfo { width: 1fr; }
    #out_path { width: 1fr; }
    #browse_dir { width: 10; }
    .hint { color: $text-muted; }
    .shortcut {
        color: $text-disabled;
        text-style: none;
        width: auto;
        padding: 0 1;
    }
    #err { color: $error; height: auto; }
    #warn { color: $warning; height: auto; }
    KeyBar {
        height: 1;
        background: $primary 10%;
        color: $text;
        padding: 0 1;
        text-style: bold;
        dock: bottom;
    }
    """