# ASCII 字符画核心
import os
import sys
import json
import numpy as np

# onefile 模式下 __file__ 指向临时解压目录，用 exe 同目录更可靠
_APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(__file__)
CONFIG_FILE = os.path.join(_APP_DIR, "setting.json")

_DEFAULT_CONFIG = {
    "CharSets": {
        "ASCII_CHARS_10": " .:-=+*#%@",
        "ASCII_CHARS_16": " .\"!~])txzOp*8$",
        "ASCII_CHARS_32": " .`\";!>~?[)|/frncXUCQOqjka*W8B$",
        "ASCII_CHARS_70": " .'`^\":;Il!i><~+-?][}{)(|\\/tfjrxnuvczXYUJCLQOZwmpqdjbkhao*#MW&8%B@$",
        "ASCII_CHARS_NUMERIC": " 0123456789",
        "ASCII_CHARS_BLOCK": " ░▒▓█"
    },
    "Charset": "ASCII_CHARS_10"
}


def _ensure_config():
    # 若 setting.json 不存在则用默认配置生成
    if not os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(_DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def load_charset():
    # 从配置文件加载字符集
    _ensure_config()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            selected = config.get("Charset", "ASCII_CHARS_10")
            charsets = config.get("CharSets", {})
            if selected in charsets:
                return charsets[selected]
            return next(iter(charsets.values()), " .:-=+*#%@")
    except (FileNotFoundError, json.JSONDecodeError):
        return " .:-=+*#%@"


# 从配置文件加载字符集
ASCII_CHARS = load_charset()


# 预生成 ANSI 转义码常量
ANSI_RESET = "\033[0m"
ANSI_COLOR_PREFIX = "\033[38;2;"


def make_lookup(chars):
    # 为指定字符集预生成 256 级灰度查找表
    return np.array([chars[i * len(chars) // 256] for i in range(256)], dtype=object)


# 预生成默认 ASCII 字符查找表
ASCII_LOOKUP = make_lookup(ASCII_CHARS)


def _make_escaped_lookup(chars):
    # 预生成 256 级灰度查找表（字符中的 '[' 已转义为 '\\['）
    return np.array([chars[i * len(chars) // 256].replace("[", "\\[") for i in range(256)], dtype=object)


ESCAPED_LOOKUP = _make_escaped_lookup(ASCII_CHARS)


# 颜色量化级数（每通道位数）：2bit -> 4 级/通道，共 64 色
_COLOR_QBITS = 2
_N_COLOR_LEVELS = 2 ** (3 * _COLOR_QBITS)  # 64
_LEVEL_SHIFT = 8 - _COLOR_QBITS
_LEVEL_HALF = 1 << (_COLOR_QBITS - 1)


def _build_ansi_lookup(chars):
    # 预生成 (颜色索引, 亮度) -> ANSI 字符串 的查找表
    n = len(chars)
    table = np.empty((_N_COLOR_LEVELS, 256), dtype=object)
    for ci in range(_N_COLOR_LEVELS):
        r = ((ci >> (2 * _COLOR_QBITS)) & 0b11) << _LEVEL_SHIFT
        g = ((ci >> _COLOR_QBITS) & 0b11) << _LEVEL_SHIFT
        b = (ci & 0b11) << _LEVEL_SHIFT
        rc = min(255, r + _LEVEL_HALF)
        gc = min(255, g + _LEVEL_HALF)
        bc = min(255, b + _LEVEL_HALF)
        for v in range(256):
            ch = chars[v * n // 256]
            table[ci, v] = f"{ANSI_COLOR_PREFIX}{rc};{gc};{bc}m{ch}"
    return table


# 预生成默认字符集的彩色查找表（仅模块加载时构建一次）
ANSI_COLOR_LOOKUP = _build_ansi_lookup(ASCII_CHARS)


def _color_index(r, g, b):
    # 把 RGB 数组量化为 0..63 的颜色索引
    ri = (r >> _LEVEL_SHIFT) * (2 ** (2 * _COLOR_QBITS))
    gi = (g >> _LEVEL_SHIFT) * (2 ** _COLOR_QBITS)
    bi = (g >> _LEVEL_SHIFT)
    return ri + gi + bi


def generate_colored_frame(pixels, luminance, charset=None):
    # 终端 ANSI 彩色字符画（用于裸终端播放）
    lookup = _build_ansi_lookup(charset) if charset else ANSI_COLOR_LOOKUP
    ci = _color_index(pixels[..., 0], pixels[..., 1], pixels[..., 2])
    ansi_grid = lookup[ci, luminance]
    lines = ["".join(row) + ANSI_RESET for row in ansi_grid]
    return "\n".join(lines)


def generate_grayscale_frame(pixels, charset=None):
    # 灰度 ASCII 字符帧
    if len(pixels.shape) == 3 and pixels.shape[2] == 1:
        pixels = pixels.squeeze(axis=2)
    chars = charset if charset else ASCII_CHARS
    lookup = make_lookup(chars) if charset else ASCII_LOOKUP
    chars_grid = lookup[pixels]
    lines = ["".join(row) for row in chars_grid]
    return "\n".join(lines)


def reload_charset():
    # 重新读取 setting.json，更新所有模块级查找表
    global ASCII_CHARS, ASCII_LOOKUP, ESCAPED_LOOKUP, ANSI_COLOR_LOOKUP
    ASCII_CHARS = load_charset()
    ASCII_LOOKUP = make_lookup(ASCII_CHARS)
    ESCAPED_LOOKUP = _make_escaped_lookup(ASCII_CHARS)
    ANSI_COLOR_LOOKUP = _build_ansi_lookup(ASCII_CHARS)
    return ASCII_CHARS
