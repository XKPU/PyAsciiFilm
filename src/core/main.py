# ASCII 字符画核心
import numpy as np

from utils.helpers import load_charset


ANSI_RESET = "\033[0m"
ANSI_COLOR_PREFIX = "\033[38;2;"

_COLOR_QBITS = 2
_N_COLOR_LEVELS = 2 ** (3 * _COLOR_QBITS)
_LEVEL_SHIFT = 8 - _COLOR_QBITS
_LEVEL_HALF = 1 << (_COLOR_QBITS - 1)


def make_lookup(chars):
    return np.array([chars[i * len(chars) // 256] for i in range(256)],
                    dtype=object)


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


def generate_colored_frame(pixels, luminance):
    """RLE 优化彩色帧：仅颜色变化时才输出 ANSI 转义码。"""
    ci = _color_index(pixels[..., 0], pixels[..., 1], pixels[..., 2])
    if ci.size == 0:
        return ""

    lines = []
    for y in range(ci.shape[0]):
        row_ci = ci[y]
        row_lum = luminance[y]
        row_chars = ASCII_LOOKUP[row_lum]

        diffs = np.diff(row_ci, prepend=np.int64(-1))
        changes = np.where(diffs != 0)[0]

        parts = []
        for i in range(len(changes)):
            start = changes[i]
            end = changes[i + 1] if i + 1 < len(changes) else len(row_ci)
            c = row_ci[start]
            parts.append(_ANSI_COLOR_ESCAPES[c])
            parts.append("".join(row_chars[start:end]))

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