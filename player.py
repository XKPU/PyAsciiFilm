import cv2
import numpy as np
from PIL import Image
import shutil
import time
import multiprocessing as mp
from init import pixel_to_ascii, get_colored_ascii_char

def get_terminal_size():
    size = shutil.get_terminal_size()
    return size.columns, size.lines

# 转换ASCII
def frame_to_ascii(image, width=80, use_color=False):
    if use_color:
        rgb_image = image
    else:
        rgb_image = image.convert("L")
    
    aspect = rgb_image.height / rgb_image.width
    new_width = width
    new_height = int(aspect * new_width * 0.5)
    resized = rgb_image.resize((new_width, new_height))
    
    if use_color:
        pixels = np.array(resized)
        ascii_frame = "\n".join(
            "".join(get_colored_ascii_char(pixel_to_ascii(int(0.299 * pixel[0] + 0.587 * pixel[1] + 0.114 * pixel[2])), 
                      pixel[0], pixel[1], pixel[2]) for pixel in row)
            for row in pixels
        )
    else:
        pixels = np.array(resized)
        ascii_frame = "\n".join(
            "".join(pixel_to_ascii(pixel) for pixel in row)
            for row in pixels
        )
    return ascii_frame

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

# 计算最佳显示尺寸
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

# 创建进度条
def create_progress_bar(current, total, width=50):
    if total <= 0:
        return "[未知进度]"
    
    progress = current / total if total > 0 else 0
    filled_width = int(width * progress)
    bar = "█" * filled_width + "░" * (width - filled_width)
    percent = progress * 100
    
    return f"[{bar}] {percent:.1f}%"

def play_video(video_path, use_color=False):
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print("错误: 无法打开视频文件")
        return False
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = 1.0 / fps if fps > 0 else 1/30
    video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    size_queue = mp.Queue()
    stop_event = mp.Event()
    
    monitor_process = mp.Process(target=terminal_monitor, args=(size_queue, stop_event))
    monitor_process.start()
    
    term_width, term_height = get_terminal_size()
    
    ascii_width = calculate_optimal_width(term_width, term_height, video_width, video_height)
    
    start_time = time.time()
    frame_count = 0
    
    try:
        while True:
            try:
                while not size_queue.empty():
                    new_width, new_height = size_queue.get_nowait()
                    term_width, term_height = new_width, new_height
                    
                    ascii_width = calculate_optimal_width(term_width, term_height, video_width, video_height)
                    
                    print("\033[2J\033[H", end='', flush=True)
            except:
                pass

            expected_frame = int((time.time() - start_time) * fps)
            current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

            if expected_frame > current_frame:
                for _ in range(expected_frame - current_frame):
                    ret = cap.grab()
                    if not ret:
                        return True
                ret, frame = cap.read()
            else:
                ret, frame = cap.read()
            
            if not ret:
                break
            
            frame_count += 1
            
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)

            ascii_frame = frame_to_ascii(img, width=ascii_width, use_color=use_color)
            
            displayed_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

            elapsed_time = time.time() - start_time
            avg_fps = frame_count / elapsed_time if elapsed_time > 0 else 0

            # 信息输出
            color_mode_text = "全彩" if use_color else "灰度"
            progress_info = f"平均帧率: {avg_fps:.1f} FPS | 原视频帧: {displayed_frame}/{total_frames} | {color_mode_text}"
            progress_bar = create_progress_bar(displayed_frame, total_frames, max(10, ascii_width // 2))
            
            output = f"{ascii_frame}\n\n{progress_info} {progress_bar}"

            print("\033[H" + output, end='', flush=True)
            
            next_frame_time = start_time + (frame_count * frame_interval)
            sleep_time = next_frame_time - time.time()
            
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    except KeyboardInterrupt:
        print("\n\n[退出] 用户中断播放")
        return True
    finally:
        # 停止子进程
        stop_event.set()
        monitor_process.join(timeout=1)
        if monitor_process.is_alive():
            monitor_process.terminate()
            
        cap.release()
        cv2.destroyAllWindows()
    
    return True
