# 后台音频播放（miniaudio 替代 sounddevice）
import threading
import time

from utils import _default_log, _forward_stderr, _ffmpeg_exe, _CREATE_NO_WINDOW, _log, _log_error

# 统一解码为固定采样率/声道
_CHANNELS = 2
_BUFFER_MS = 120

_SYS_SAMPLE_RATE = None


def _system_sample_rate():
    # WASAPI 共享模式使用统一混音采样率；让 ffmpeg 与 miniaudio 都用此速率，
    # 避免与 ffmpeg -ar 叠加成双重重采样（高频丢失、声音发闷）
    global _SYS_SAMPLE_RATE
    if _SYS_SAMPLE_RATE is not None:
        return _SYS_SAMPLE_RATE
    rate = 44100
    try:
        import miniaudio
        for d in miniaudio.Devices().get_playbacks():
            for f in (d.get("formats") or []):
                sr = f.get("samplerate")
                if isinstance(sr, int) and sr > 0:
                    rate = sr
                    break
            if rate != 44100:
                break
    except Exception:
        pass
    _SYS_SAMPLE_RATE = rate
    return rate



def start_audio(video_path, log=None):
    # 后台流式播放音轨
    ffmpeg = _ffmpeg_exe()
    if not ffmpeg:
        _log("音频初始化跳过：未找到 ffmpeg")
        return None
    _logfn = log or _default_log
    try:
        import miniaudio
    except ImportError:
        _log("音频初始化跳过：未安装 miniaudio")
        return None

    sample_rate = _system_sample_rate()
    _log(f"音频初始化: {video_path} | 采样率 {sample_rate} 声道 {_CHANNELS}")

    stop_event = threading.Event()
    started = threading.Event()
    start_time = [None]
    latency = [0.0]
    ended = threading.Event()
    device_ref = [None]

    def _worker():
        import subprocess

        cmd = [
            ffmpeg, "-nostdin", "-loglevel", "info",
            "-i", video_path,
            "-vn",
            "-f", "f32le",
            "-acodec", "pcm_f32le",
            "-ac", str(_CHANNELS),
            "-ar", str(sample_rate),
            "-",
        ]
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
                  "creationflags": _CREATE_NO_WINDOW}
        proc = subprocess.Popen(cmd, **kwargs)
        _forward_stderr(proc, _logfn)

        nbytes_per_frame = _CHANNELS * 4

        def gen():
            # miniaudio 生成器回调：send(framecount) 进，yield 等长 float32 字节
            framecount = yield
            while True:
                if stop_event.is_set():
                    return
                nbytes = framecount * nbytes_per_frame
                raw = proc.stdout.read(nbytes)
                if not raw:
                    ended.set()
                    return
                if not started.is_set():
                    started.set()
                    start_time[0] = time.monotonic()
                if len(raw) < nbytes:
                    raw = raw + b"\x00" * (nbytes - len(raw))
                elif len(raw) > nbytes:
                    raw = raw[:nbytes]
                framecount = yield raw

        try:
            device = miniaudio.PlaybackDevice(
                output_format=miniaudio.SampleFormat.FLOAT32,
                nchannels=_CHANNELS,
                sample_rate=sample_rate,
                buffersize_msec=_BUFFER_MS,
            )
            device_ref[0] = device
            try:
                latency[0] = float(device.buffersize_msec) / 1000.0
            except Exception:
                latency[0] = _BUFFER_MS / 1000.0
            g = gen()
            next(g)
            device.start(g)
            _log(f"音频播放开始: 延迟 {latency[0]:.3f}s")
            while device.running and not stop_event.is_set() and not ended.is_set():
                time.sleep(0.05)
            _log("音频播放结束")
        except Exception as e:
            _log_error(f"音频播放异常: {e}")
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                if device_ref[0] is not None:
                    device_ref[0].stop()
            except Exception:
                pass
            try:
                if device_ref[0] is not None:
                    device_ref[0].close()
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()

    def stop():
        stop_event.set()
        try:
            if device_ref[0] is not None:
                device_ref[0].stop()
                device_ref[0].close()
        except Exception:
            pass

    def get_start_time():
        if started.is_set() and start_time[0] is not None:
            return start_time[0] + latency[0]
        return None

    return stop, get_start_time
