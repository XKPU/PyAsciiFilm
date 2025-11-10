# ASCII character set
ASCII_CHARS = "@%#*+=-:. "

# Grayscale character mapping
def pixel_to_ascii(value):
    return ASCII_CHARS[value * len(ASCII_CHARS) // 256]

# Color character mapping
def get_colored_ascii_char(char, r, g, b):
    return f"\033[38;2;{r};{g};{b}m{char}\033[0m"