# 核心功能模块

from .ascii_art import (
    # 字符集管理
    load_charset,
    reload_charset,
    ASCII_CHARS,
    ASCII_LOOKUP,
    make_lookup,
    # 帧生成
    generate_grayscale_frame,
    generate_colored_frame,
    # 配置读写（供 dialogs 使用）
    _read_config,
    _write_config_value,
    LAST_VIDEO_DIR_KEY,
    LAST_EXPORT_DIR_KEY,
    # ANSI 颜色查找表
    ANSI_COLOR_LOOKUP,
    _build_ansi_lookup,
    _color_index,
    _N_COLOR_LEVELS,
    _LEVEL_SHIFT,
    _LEVEL_HALF,
    _COLOR_QBITS,
    ANSI_RESET,
    ANSI_COLOR_PREFIX,
    _DEFAULT_CONFIG,
    CONFIG_FILE,
    _ensure_config,
)

from .decoder import (
    FrameReader,
)

from .audio import (
    start_audio,
    _system_sample_rate,
)