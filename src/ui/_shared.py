"""app.py 与 screens/ 之间的共享工具，避免循环导入"""

_EXPORTER = None
_cached_decode_backends = None


def _exporter():
    global _EXPORTER
    if _EXPORTER is None:
        from export.main import export_video
        from export.renderer import _load_mono_font
        from export.writer import _MAX_CANVAS_W, _MAX_CANVAS_H, _ENCODER_MAX_SIZE
        _EXPORTER = (export_video, _load_mono_font, _MAX_CANVAS_W, _MAX_CANVAS_H, _ENCODER_MAX_SIZE)
    return _EXPORTER


def _probe_video(path):
    from decoder.main import FrameReader
    cap = FrameReader(path, log=lambda msg: None)
    w, h, fps = cap.width, cap.height, cap.fps
    cap.release()
    return w, h, fps