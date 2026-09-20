# ASCII 字符画核心
import numpy as np

from utils.helpers import load_charset


ANSI_RESET = "\033[0m"
ANSI_COLOR_PREFIX = "\033[38;2;"

_COLOR_QBITS = 2
_N_COLOR_LEVELS = 2 ** (3 * _COLOR_QBITS)
_LEVEL_SHIFT = 8 - _COLOR_QBITS
_LEVEL_HALF = 1 << (_COLOR_QBITS - 1)


_FALLBACK_CHARSET = " .:-=+*#%@"


def make_lookup(chars):
    # 空字符集回退默认，避免导入时索引越界
    if not isinstance(chars, str) or not chars:
        chars = _FALLBACK_CHARSET
    n = len(chars)
    # 保持原有向下取整映射，暗部对应关系不变；仅令最亮档取到末位字符
    idx = [i * n // 256 for i in range(256)]
    idx[255] = n - 1
    return np.array([chars[v] for v in idx], dtype=object)


ASCII_CHARS = load_charset()
ASCII_LOOKUP = make_lookup(ASCII_CHARS)


def _color_index(r, g, b):
    ri = (r >> _LEVEL_SHIFT) * (2 ** (2 * _COLOR_QBITS))
    gi = (g >> _LEVEL_SHIFT) * (2 ** _COLOR_QBITS)
    bi = (b >> _LEVEL_SHIFT)
    return ri + gi + bi


_ANSI_COLOR_ESCAPES = np.array([
    f"{ANSI_COLOR_PREFIX}"
    f"{min(255, ((ci >> 4 & 3) << _LEVEL_SHIFT) + _LEVEL_HALF)};"
    f"{min(255, ((ci >> 2 & 3) << _LEVEL_SHIFT) + _LEVEL_HALF)};"
    f"{min(255, ((ci & 3) << _LEVEL_SHIFT) + _LEVEL_HALF)}m"
    for ci in range(_N_COLOR_LEVELS)
], dtype=object)

# 原生 Python str 列表：内层热循环用它索引比 numpy 对象数组快得多
_ANSI_COLOR_ESCAPES_LIST = [str(e) for e in _ANSI_COLOR_ESCAPES]


def generate_colored_frame(pixels, luminance):
    # RLE 优化彩色帧：仅颜色变化时才输出 ANSI 转义码。实现要点（性能）：每格都发一次转义码约 9~10 ms/帧，RLE 后真实视频降到 ~1.2 ms/帧
    ci = _color_index(pixels[..., 0], pixels[..., 1], pixels[..., 2])
    rows, cols = ci.shape
    if rows == 0 or cols == 0:
        return ""

    lines = []
    esc = _ANSI_COLOR_ESCAPES_LIST
    for row_ci, row_lum in zip(ci.tolist(), luminance.tolist()):
        row_chars = ASCII_LOOKUP[row_lum]
        parts = []
        last = -1
        for i, c in enumerate(row_ci):
            if c != last:
                parts.append(esc[c])
                last = c
            parts.append(row_chars[i])
        parts.append(ANSI_RESET)
        lines.append("".join(parts))

    return "\n".join(lines)


def generate_grayscale_frame(pixels):
    if len(pixels.shape) == 3 and pixels.shape[2] == 1:
        pixels = pixels.squeeze(axis=2)
    chars_grid = ASCII_LOOKUP[pixels]
    lines = ["".join(row) for row in chars_grid]
    return "\n".join(lines)


def reload_charset():
    global ASCII_CHARS, ASCII_LOOKUP
    ASCII_CHARS = load_charset()
    ASCII_LOOKUP = make_lookup(ASCII_CHARS)
    return ASCII_CHARS