# 帧率收拢工具

def clean_fps(fps):
    # 把 cv2 探测到的帧率收拢为名义整数帧率
    if fps is None or fps <= 0:
        return 30.0
    r = round(fps)
    if abs(fps - r) < 0.5:
        return float(r)
    return float(fps)
