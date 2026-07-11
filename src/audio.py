# 后台音频播放
import threading
import time

from utils import _default_log, _forward_stderr, _ffmpeg_exe

# 统一解码为固定采样率/声道
_SAMPLE_RATE = 44100
_CHANNELS = 2
_CHUNK_FRAMES = 4096


def start_audio(video_path, log=None):
    # 后台流式播放音轨
    ffmpeg = _ffmpeg_exe()
    if not ffmpeg:
        return None
    _log = log or _default_log
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        return None

    stop_event = threading.Event()
    started = threading.Event()
    start_time = [None]
    latency = [0.0]
    stream_ref = [None]

    def _worker():
        import subprocess
        cmd = [
            ffmpeg, "-nostdin", "-loglevel", "info",
            "-i", video_path,
            "-vn",
            "-f", "f32le",
            "-acodec", "pcm_f32le",
            "-ac", str(_CHANNELS),
            "-ar", str(_SAMPLE_RATE),
            "-",
        ]
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(cmd, **kwargs)
        _forward_stderr(proc, _log)

        def callback(outdata, frames, time_info, status):
            nbytes = frames * _CHANNELS * 4
            raw = proc.stdout.read(nbytes)
            if not raw:
                outdata[:] = 0
                raise sd.CallbackStop
            arr = np.frombuffer(raw, dtype=np.float32)
            avail = arr.size // _CHANNELS
            if avail >= frames:
                outdata[:] = arr[:frames * _CHANNELS].reshape(frames, _CHANNELS)
            else:
                outdata[:avail] = arr.reshape(avail, _CHANNELS)
                outdata[avail:] = 0
            if not started.is_set():
                started.set()
                start_time[0] = time.monotonic()

        try:
            stream = sd.OutputStream(
                samplerate=_SAMPLE_RATE,
                channels=_CHANNELS,
                blocksize=_CHUNK_FRAMES,
                callback=callback,
            )
            stream_ref[0] = stream
            stream.start()
            try:
                latency[0] = float(stream.latency)
            except Exception:
                latency[0] = 0.0
            while stream.active and not stop_event.is_set():
                time.sleep(0.05)
            stream.stop()
            stream.close()
        except Exception:
            pass
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()

    def stop():
        stop_event.set()
        try:
            if stream_ref[0] is not None:
                stream_ref[0].stop()
                stream_ref[0].close()
        except Exception:
            pass

    def get_start_time():
        if started.is_set() and start_time[0] is not None:
            return start_time[0] + latency[0]
        return None

    return stop, get_start_time
