# 后台音频播放（miniaudio）
import atexit
import threading
import time

from utils.helpers import _default_log, _forward_stderr, _ffmpeg_exe, _CREATE_NO_WINDOW, _log, _log_error

_CHANNELS = 2
_BUFFER_MS = 120

_SYS_SAMPLE_RATE = None

# 当前活跃的播放句柄，供退出兜底统一清理
_ACTIVE = []
_ACTIVE_LOCK = threading.Lock()


def stop_all_audio():
    # 终止所有仍在播放的音频（幂等，供退出兜底调用）
    with _ACTIVE_LOCK:
        handles = list(_ACTIVE)
        _ACTIVE.clear()
    for h in handles:
        try:
            h()
        except Exception:
            pass


atexit.register(stop_all_audio)


def _system_sample_rate():
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
    proc_ref = [None]

    def _kill_proc():
        # 真正终止 ffmpeg 子进程（关闭 stdout 可解锁阻塞中的 read）
        proc = proc_ref[0]
        if proc is None:
            return
        try:
            if proc.stdout is not None:
                proc.stdout.close()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=1.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _worker():
        import subprocess

        # 启动前先看是否已被取消：线程可能在 stop() 之后才真正获得调度，若不检查就会"退出后才把 ffmpeg 启起来"，声音继续响
        if stop_event.is_set():
            ended.set()
            return

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
        proc_ref[0] = proc
        _forward_stderr(proc, _logfn)

        nbytes_per_frame = _CHANNELS * 4

        def gen():
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
            # 标记结束，播放端不必再等（无音轨/失败时也要置位）
            ended.set()
            _kill_proc()
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

    def stop():
        # 立即停止播放：先停设备，再杀 ffmpeg
        stop_event.set()
        # 先关设备，避免 ffmpeg 被 kill 时最后一块数据又排进缓冲
        try:
            if device_ref[0] is not None:
                device_ref[0].stop()
        except Exception:
            pass
        _kill_proc()
        try:
            if device_ref[0] is not None:
                device_ref[0].close()
        except Exception:
            pass
        with _ACTIVE_LOCK:
            try:
                _ACTIVE.remove(stop)
            except ValueError:
                pass

    # 句柄必须在启动线程**之前**登记：否则存在"线程已启动、句柄尚未登记"的窗口，此时退出程序，stop_all_audio() 看不到任何句柄，音频仍会被启动并一直响下去
    with _ACTIVE_LOCK:
        _ACTIVE.append(stop)

    threading.Thread(target=_worker, daemon=True).start()

    def get_start_time():
        if started.is_set() and start_time[0] is not None:
            return start_time[0] + latency[0]
        return None

    def no_audio():
        # 音频不可能再开始了（无音轨/解码已结束/出错）。播放端据此提前结束等待：否则没有音轨的视频会白等满 3 秒超时，表现为选了视频后长时间黑屏
        return ended.is_set() and not started.is_set()

    return stop, get_start_time, no_audio
