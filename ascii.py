import numpy as np

# 10字符集
ASCII_CHARS_10 = " .:-=+*#%@"

# 16字符集
ASCII_CHARS_16 = " .\"!~])txzOp*8$"

# 32字符集
ASCII_CHARS_32 = " .`\";!>~?[)|/frncXUCQOqjka*W8B$"

# 70字符集
ASCII_CHARS_70 = " .'`^\":;Il!i><~+-?][}{)(|\\/tfjrxnuvczXYUJCLQ0OZwmpqdjbkhao*#MW&8%B@$"

# 数字字符集
ASCII_CHARS_NUMERIC = " 0123456789"

# 块字符集
ASCII_CHARS_BLOCK = " ░▒▓█"

'''
选择使用的字符集（修改ASCII_CHARS变量）
可选值：
默认：ASCII_CHARS_10
多样：ASCII_CHARS_16, ASCII_CHARS_32, ASCII_CHARS_70
特殊：ASCII_CHARS_NUMERIC, ASCII_CHARS_BLOCK
'''
ASCII_CHARS = ASCII_CHARS_10


# 预生成ANSI转义码常量
ANSI_RESET = "\033[0m"
ANSI_COLOR_PREFIX = "\033[38;2;"

# 预生成ASCII字符查找表
ASCII_LOOKUP = np.array([ASCII_CHARS[i * len(ASCII_CHARS) // 256] for i in range(256)], dtype=object)

# 将灰度值映射为ASCII字符
def pixel_to_ascii(value):
    return ASCII_CHARS[value * len(ASCII_CHARS) // 256]

# 生成彩色ASCII字符帧
def generate_colored_frame(pixels, luminance):
    height, width = luminance.shape

    # 使用向量化的ASCII查找
    chars = ASCII_LOOKUP[luminance]

    lines = []
    reset_code = ANSI_RESET

    for y in range(height):
        row_parts = []
        for x in range(width):
            char = chars[y, x]
            r, g, b = pixels[y, x]
            row_parts.append(f"{ANSI_COLOR_PREFIX}{r};{g};{b}m{char}")

        lines.append("".join(row_parts) + reset_code)

    return "\n".join(lines)

# 生成灰度ASCII字符帧
def generate_grayscale_frame(pixels):
    if len(pixels.shape) == 3 and pixels.shape[2] == 1:
        pixels = pixels.squeeze(axis=2)

    # 使用向量化的ASCII查找
    chars = ASCII_LOOKUP[pixels]

    lines = ["".join(row) for row in chars]
    
    return "\n".join(lines)
