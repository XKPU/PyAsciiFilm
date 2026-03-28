#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#else
#include <sys/ioctl.h>
#include <unistd.h>
#endif

#include "player.h"
#include "ascii.h"
#include <opencv2/opencv.hpp>
#include <iostream>
#include <chrono>
#include <thread>
#include <cmath>
#include <sstream>
#include <iomanip>
#include <queue>
#include <mutex>
#include <condition_variable>
#include <atomic>

namespace AsciiFilm {

// 获取终端尺寸
std::pair<int, int> getTerminalSize() {
#ifdef _WIN32
    HANDLE hStdOut = GetStdHandle(STD_OUTPUT_HANDLE);
    CONSOLE_SCREEN_BUFFER_INFO csbi;
    GetConsoleScreenBufferInfo(hStdOut, &csbi);
    return {csbi.srWindow.Right - csbi.srWindow.Left + 1,
            csbi.srWindow.Bottom - csbi.srWindow.Top + 1};
#else
    struct winsize w;
    ioctl(STDOUT_FILENO, TIOCGWINSZ, &w);
    return {w.ws_col, w.ws_row};
#endif
}

// 计算最优显示宽度
int calculateOptimalWidth(int termWidth, int termHeight, int videoWidth, int videoHeight) {
    int maxAsciiWidth = std::min(termWidth - 1, videoWidth);
    int maxAsciiHeight = std::min(termHeight - 1, videoHeight);

    double terminalAspect = static_cast<double>(maxAsciiHeight) / (maxAsciiWidth * 0.5);
    double videoAspect = static_cast<double>(videoHeight) / videoWidth;

    if (videoAspect <= terminalAspect) {
        return maxAsciiWidth;
    } else {
        return static_cast<int>((maxAsciiHeight / videoAspect) * 2);
    }
}

// 创建进度条显示
std::string createProgressBar(int current, int total, int width) {
    if (total <= 0) return "[未知进度]";

    double progress = static_cast<double>(current) / total;
    int filledWidth = static_cast<int>(width * progress);
    std::string bar(filledWidth, '#');
    std::string empty(width - filledWidth, '-');
    double percent = progress * 100;

    std::ostringstream oss;
    oss << "[" << bar << empty << "] " << std::fixed << std::setprecision(1) << percent << "%";
    return oss.str();
}

// 播放视频函数
void playVideo(const std::string& videoPath, bool useColor) {
    cv::VideoCapture cap(videoPath);

    if (!cap.isOpened()) {
        std::cerr << "错误: 无法打开视频文件" << std::endl;
        return;
    }

    // 获取视频信息
    double fps = cap.get(cv::CAP_PROP_FPS);
    double frameInterval = fps > 0 ? 1.0 / fps : 1.0 / 30.0;
    int videoWidth = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_WIDTH));
    int videoHeight = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_HEIGHT));
    int totalFrames = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_COUNT));

    // 计算初始显示尺寸
    auto [termWidth, termHeight] = getTerminalSize();
    int asciiWidth = calculateOptimalWidth(termWidth, termHeight, videoWidth, videoHeight);

    const int BUFFER_SIZE = useColor ? 2 : 5;
    std::queue<std::string> frameQueue;
    std::mutex queueMutex;
    std::condition_variable queueCV;
    bool producerDone = false;
    std::atomic<bool> shouldStop{false};

    auto producer = [&]() {
        cv::Mat frame;
        int consecutiveEmptyFrames = 0;
        const int MAX_EMPTY_FRAMES = 5;

        while (!shouldStop.load() && consecutiveEmptyFrames < MAX_EMPTY_FRAMES) {
            {
                std::unique_lock<std::mutex> lock(queueMutex);
                int currentBufferSize = useColor ? std::min(2, BUFFER_SIZE) : BUFFER_SIZE;
                if (frameQueue.size() >= currentBufferSize) {
                    lock.unlock();
                    std::this_thread::sleep_for(std::chrono::milliseconds(5));
                    continue;
                }
            }

            cap >> frame;
            if (frame.empty()) {
                consecutiveEmptyFrames++;
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                continue;
            }

            consecutiveEmptyFrames = 0;
            std::string asciiFrame = processFrame(frame, asciiWidth, useColor);

            {
                std::lock_guard<std::mutex> lock(queueMutex);
                frameQueue.push(std::move(asciiFrame));
            }
            queueCV.notify_one();
        }

        std::lock_guard<std::mutex> lock(queueMutex);
        producerDone = true;
        queueCV.notify_one();
    };

    std::thread producerThread(producer);

    auto startTime = std::chrono::steady_clock::now();
    int frameCount = 0;

    try {
        while (!shouldStop.load()) {
            // 处理终端尺寸变化
            auto [currentTermWidth, currentTermHeight] = getTerminalSize();
            if (currentTermWidth != termWidth || currentTermHeight != termHeight) {
                termWidth = currentTermWidth;
                termHeight = currentTermHeight;
                asciiWidth = calculateOptimalWidth(termWidth, termHeight, videoWidth, videoHeight);
                std::cout << "\033[2J\033[H" << std::flush;
            }

            // 从队列获取预加载的帧
            std::string asciiFrame;
            {
                std::unique_lock<std::mutex> lock(queueMutex);
                queueCV.wait_for(lock, std::chrono::milliseconds(50), [&] {
                    return !frameQueue.empty() || producerDone;
                });

                if (frameQueue.empty() && producerDone) {
                    break;
                }

                if (!frameQueue.empty()) {
                    asciiFrame = std::move(frameQueue.front());
                    frameQueue.pop();
                    frameCount++;
                }
            }

            if (asciiFrame.empty()) continue;

            // 计算性能统计数据
            auto currentTime = std::chrono::steady_clock::now();
            auto elapsedTime = std::chrono::duration<double>(currentTime - startTime).count();
            double avgFps = elapsedTime > 0 ? frameCount / elapsedTime : 0.0;

            int displayedFrame = static_cast<int>(cap.get(cv::CAP_PROP_POS_FRAMES));
            std::string colorModeText = useColor ? "全彩" : "灰度";
            std::string performanceText = " | 分辨率: " + std::to_string(asciiWidth) + "x" +
                                          std::to_string(static_cast<int>(asciiWidth * 0.5));
            std::string progressInfo = "平均帧率: " + std::to_string(avgFps).substr(0, 4) + " FPS | " +
                                       "原始视频帧: " + std::to_string(displayedFrame) + "/" +
                                       std::to_string(totalFrames) + " | " +
                                       colorModeText + performanceText;
            std::string progressBar = createProgressBar(displayedFrame, totalFrames, std::max(10, asciiWidth / 2));

            std::string output = asciiFrame + progressInfo + " " + progressBar;

            std::cout << "\033[H" << output << std::flush;

            auto targetTime = startTime + std::chrono::duration<double>(frameCount * frameInterval);
            auto currentTimeCheck = std::chrono::steady_clock::now();
            auto sleepTime = targetTime - currentTimeCheck;
            
            if (sleepTime.count() > 0.001) {
                std::this_thread::sleep_for(sleepTime);
            } else if (sleepTime.count() < -0.1) {
                // 丢帧逻辑：跳过队列中的一半帧以追赶进度
                std::lock_guard<std::mutex> lock(queueMutex);
                int framesToSkip = std::min(3, static_cast<int>(frameQueue.size() / 2));
                for (int i = 0; i < framesToSkip && !frameQueue.empty(); ++i) {
                    frameQueue.pop();
                    frameCount++; // 补偿被跳过的帧计数
                }
            }
        }
    } catch (const std::exception& e) {
        std::cerr << "\n[错误] 播放过程中发生异常: " << e.what() << std::endl;
        shouldStop.store(true);
    }

    shouldStop.store(true);
    if (producerThread.joinable()) {
        producerThread.join();
    }

    cap.release();
    cv::destroyAllWindows();
}

}