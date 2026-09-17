# 导出渲染（字体、字形图集、帧渲染）
import math
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _load_mono_font(charset=None):
    candidates = [
        # Windows
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "C:/Windows/Fonts/lucon.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
        # macOS
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Courier.ttc",
        "/Library/Fonts/Andale Mono.ttf",
    ]

    sample = list(" .:-=+*#%@MWAi01abcdefghijklmnopqrstuvwxyz[](){}/\\|")
    if charset:
        for ch in charset:
            if ch not in sample:
                sample.append(ch)

    def _is_monospace(font):
        try:
            adv = [font.getlength(c) for c in sample]
        except Exception:
            return False
        return bool(adv) and (max(adv) - min(adv)) <= 0.5

    font = None
    for path in candidates:
        if not path or not os.path.exists(path):
            continue
        try:
            f = ImageFont.truetype(path, size=20)
        except Exception:
            continue
        if _is_monospace(f):
            font = f
            break

    if font is None:
        for path in candidates:
            if path and os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, size=20)
                    break
                except Exception:
                    continue
    if font is None:
        font = ImageFont.load_default()

    cell_w = float(font.getlength("M"))
    ascent, descent = font.getmetrics()
    try:
        min_top = 0
        max_bottom = 0
        for ch in (charset or ""):
            bbox = font.getbbox(ch)
            if bbox:
                if bbox[1] < min_top:
                    min_top = bbox[1]
                if bbox[3] > max_bottom:
                    max_bottom = bbox[3]
        if max_bottom > 0 or min_top < 0:
            cell_h = float(max_bottom - min_top)
            y_offset = float(-min_top)
        else:
            cell_h = float(ascent + descent)
            y_offset = 0.0
    except Exception:
        cell_h = float(ascent + descent)
        y_offset = 0.0
    if cell_w <= 0 or cell_h <= 0:
        cell_w, cell_h = 10.0, 20
        y_offset = 0.0
    return font, cell_w, cell_h, y_offset


def _build_glyph_atlas(font, cell_w, cell_h, chars, y_offset=0.0):
    tile_w = max(1, int(math.ceil(cell_w)))
    tile_h = max(1, int(math.ceil(cell_h)))
    y_off = int(math.floor(y_offset))
    uniq = list(dict.fromkeys(chars))
    if " " not in uniq:
        uniq.insert(0, " ")
    G = len(uniq)
    atlas = np.zeros((G, tile_h, tile_w), dtype=np.uint8)
    for i, ch in enumerate(uniq):
        img = Image.new("L", (tile_w, tile_h), 0)
        ImageDraw.Draw(img).text((0, y_off), ch, fill=255, font=font)
        atlas[i] = np.asarray(img, dtype=np.uint8)
    char_to_idx = {ch: i for i, ch in enumerate(uniq)}
    return atlas, tile_w, tile_h, char_to_idx


def _render_frame(char_grid, color_grid, atlas, tile_w, tile_h, char_to_idx, use_color,
                 canvas_w, canvas_h):
    h, w = char_grid.shape
    H, W = h * tile_h, w * tile_w
    space_idx = char_to_idx.get(" ", 0)
    def _lookup(ch):
        return char_to_idx.get(ch, space_idx)
    idx = np.frompyfunc(_lookup, 1, 1)(char_grid.ravel())
    idx = np.asarray(idx, dtype=np.intp).reshape(h, w)
    luma = atlas[idx]
    luma = luma.swapaxes(1, 2).reshape(H, W)

    luma_bin = np.where(luma >= 128, 255, 0).astype(np.uint8)
    if use_color and color_grid is not None:
        color_tiled = cv2.resize(color_grid, (W, H), interpolation=cv2.INTER_NEAREST)
        fg = luma_bin.astype(np.float32) / 255.0
        bg = color_tiled.astype(np.float32)
        rgb = (bg * (1.0 - fg[..., None] * 0.65) + 0.5).astype(np.uint8)
        cur = rgb[:, :, ::-1].copy()
    else:
        out = np.empty((H, W, 3), dtype=np.uint8)
        out[..., 0] = luma_bin
        out[..., 1] = luma_bin
        out[..., 2] = luma_bin
        cur = out
    if cur.shape[0] != canvas_h or cur.shape[1] != canvas_w:
        padded = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
        padded[:cur.shape[0], :cur.shape[1]] = cur
        cur = padded
    return cur


def _small(frame, target_w, target_h):
    if frame.shape[1] == target_w and frame.shape[0] == target_h:
        resized = frame
    else:
        resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    return rgb, gray


def _grids_from_rgb(rgb, use_color, gray=None, gray_lookup=None):
    lum = gray if gray is not None else cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if gray_lookup is None:
        from core.main import ASCII_CHARS, make_lookup
        gray_lookup = make_lookup(ASCII_CHARS)
    char_grid = gray_lookup[lum]
    color_grid = rgb if use_color else None
    return char_grid, color_grid