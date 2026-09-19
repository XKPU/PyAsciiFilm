
_EXPORTER = None


def _exporter():
    global _EXPORTER
    if _EXPORTER is None:
        from export.main import export_video
        from export.renderer import _load_mono_font
        from export.writer import _MAX_CANVAS_W, _MAX_CANVAS_H, _ENCODER_MAX_SIZE
        _EXPORTER = (export_video, _load_mono_font, _MAX_CANVAS_W, _MAX_CANVAS_H, _ENCODER_MAX_SIZE)
    return _EXPORTER
