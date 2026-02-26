import cv2
import numpy as np
from PIL import Image
import shutil
import time
import multiprocessing as mp
import queue
import threading
from ascii import generate_colored_frame, generate_grayscale_frame

# 将帧转换为ASCII字符画 函数
def process_frame(frame, width, use_color):
    # 转换色彩空间并调整大小
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(frame_rgb)

    aspect = img.height / img.width
    new_height = int(aspect * width * 0.5)
    resized = img.resize((width, new_height))

    if use_color:
        # 全彩：向量化计算亮度并生成彩色ASCII
        pixels = np.array(resized)
        luminescence = np.dot(pixels[...,:3], [0.299, 0.587, 0.114]).astype(np.uint8)
        result = generate_colored_frame(pixels, luminescence)
    else:
        # 灰度：转换为灰度并生成ASCII字符画
        gray_img = resized.convert("L")
        pixels = np.array(gray_img)
        result = generate_grayscale_frame(pixels)

    return result

# 获取终端尺寸 函数
def get_terminal_size():
    size = shutil.get_terminal_size()
    return size.columns, size.lines

# 后台监控终端尺寸变化 函数
def terminal_monitor(size_queue, stop_event):
    last_width, last_height = get_terminal_size()

    while not stop_event.is_set():
        try:
            current_width, current_height = get_terminal_size()

            if current_width != last_width or current_height != last_height:
                size_queue.put((current_width, current_height))
                last_width, last_height = current_width, current_height
        except KeyboardInterrupt:
            break
        except Exception:
            pass

# 计算最佳显示范围 函数
def calculate_optimal_width(term_width, term_height, video_width, video_height):
    max_ascii_width = min(term_width - 1, video_width)
    max_ascii_height = min(term_height - 1, video_height)

    terminal_aspect = max_ascii_height / (max_ascii_width * 0.5)
    video_aspect = video_height / video_width

    if video_aspect <= terminal_aspect:
        ascii_width = max_ascii_width
    else:
        ascii_width = int((max_ascii_height / video_aspect) * 2)

    return ascii_width

# 异步帧处理
class FramePreloader:

    def __init__(self, cap, ascii_width, use_color):
        # 初始化
        self.cap = cap
        self.ascii_width = ascii_width
        self.use_color = use_color
        self.frame_queue = queue.Queue(maxsize=2)
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.cap_lock = threading.Lock()

    def start(self):
        # 启动线程
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self._preload_frames, daemon=True)
        self.worker_thread.start()

    def _preload_frames(self):
        # 后台线程
        while not self.stop_event.is_set():
            if self.frame_queue.full():
                time.sleep(0.001)
                continue
            
            with self.cap_lock:
                ret, frame = self.cap.read()

            if not ret:
                self.stop_event.set()
                break

            try:
                ascii_frame = process_frame(frame, self.ascii_width, self.use_color)

                if not self.stop_event.is_set():
                    self.frame_queue.put(ascii_frame)
            except Exception as e:
                print(f"预加载帧失败: {e}")
                break

    def get_frame(self):
        # 获取帧
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        # 停止线程
        self.stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=0.5)


def create_progress_bar(current, total, width=50):
    # 进度条
    if total <= 0:
        return "[未知进度]"

    progress = current / total
    filled_width = int(width * progress)
    bar = "█" * filled_width + "░" * (width - filled_width)
    percent = progress * 100

    return f"[{bar}] {percent:.1f}%"


def play_video(video_path, use_color=False):
    # 播放为ASCII
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print("错误: 无法打开视频文件")
        return False

    # 获取视频信息
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = 1.0 / fps if fps > 0 else 1/30
    video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 启动终端监控进程
    size_queue = mp.Queue()
    stop_event = mp.Event()
    monitor_process = mp.Process(target=terminal_monitor, args=(size_queue, stop_event))
    monitor_process.start()

    # 计算初始显示尺寸
    term_width, term_height = get_terminal_size()
    ascii_width = calculate_optimal_width(term_width, term_height, video_width, video_height)

    # 启动帧预加载器
    preloader = FramePreloader(cap, ascii_width, use_color)
    preloader.start()

    start_time = time.time()
    frame_count = 0

    try:
        while True:
            # 处理终端尺寸变化
            try:
                while not size_queue.empty():
                    new_width, new_height = size_queue.get_nowait()
                    term_width, term_height = new_width, new_height

                    ascii_width = calculate_optimal_width(term_width, term_height, video_width, video_height)

                    preloader.stop()
                    preloader = FramePreloader(cap, ascii_width, use_color)
                    preloader.start()

                    print("\033[2J\033[H", end='', flush=True)
            except Exception:
                pass

            # 尝试从预加载队列获取帧
            ascii_frame = preloader.get_frame()

            if ascii_frame is None:
                # 预加载队列为空，同步读取并处理
                with preloader.cap_lock:
                    ret, frame = cap.read()
                if not ret:
                    break

                frame_count += 1

                ascii_frame = process_frame(frame, ascii_width, use_color)
            else:
                frame_count += 1

            # 获取当前帧位置和性能统计
            displayed_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
            elapsed_time = time.time() - start_time
            avg_fps = frame_count / elapsed_time if elapsed_time > 0 else 0

            # 显示播放信息
            color_mode_text = "全彩" if use_color else "灰度"
            performance_text = f" | 分辨率: {ascii_width}x{int(ascii_width * 0.5)}"
            progress_info = f"平均帧率: {avg_fps:.1f} FPS | 原视频帧: {displayed_frame}/{total_frames} | {color_mode_text}{performance_text}"
            progress_bar = create_progress_bar(displayed_frame, total_frames, max(10, ascii_width // 2))

            output = f"{ascii_frame}\n\n{progress_info} {progress_bar}"

            print("\033[H" + output, end='', flush=True)

            next_frame_time = start_time + (frame_count * frame_interval)
            sleep_time = next_frame_time - time.time()

            if sleep_time > 0:
                time.sleep(max(0, sleep_time))

    except KeyboardInterrupt:
        print("\n\n[退出] 用户中断播放")
        return True
    finally:
        # 清理资源
        preloader.stop()
        stop_event.set()
        monitor_process.join(timeout=1)
        if monitor_process.is_alive():
            monitor_process.terminate()

        cap.release()
        cv2.destroyAllWindows()

    return True