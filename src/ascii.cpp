#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#else
#include <limits.h>
#endif

#include "ascii.h"
#include <opencv2/opencv.hpp>
#include <sstream>
#include <iomanip>
#include <fstream>
#include <cstring>
#include <array>
#include <thread>

namespace AsciiFilm {

// 从 JSON 获取配置
static std::string extractJsonValue(const std::string& json, const std::string& key) {
    std::string searchKey = "\"" + key + "\"";
    size_t keyPos = json.find(searchKey);
    if (keyPos == std::string::npos) return "";

    size_t colonPos = json.find(":", keyPos);
    if (colonPos == std::string::npos) return "";

    size_t searchStart = colonPos + 1;
    while (searchStart < json.length() && (json[searchStart] == ' ' || json[searchStart] == '\t' ||
           json[searchStart] == '\n' || json[searchStart] == '\r')) {
        searchStart++;
    }

    size_t valueStart = json.find("\"", searchStart);
    if (valueStart == std::string::npos) return "";
    valueStart++;

    size_t valueEnd = json.find("\"", valueStart);
    if (valueEnd == std::string::npos) return "";

    return json.substr(valueStart, valueEnd - valueStart);
}

// 加载配置
static bool loadConfig() {
    static std::string staticCharsetValue;

#ifdef _WIN32
    char exePath[MAX_PATH];
    GetModuleFileNameA(NULL, exePath, MAX_PATH);
    std::string configPath = exePath;
    size_t pos = configPath.find_last_of("\\/");
    if (pos != std::string::npos) {
        configPath = configPath.substr(0, pos + 1);
    }
    configPath += "setting.json";
#else
    std::string configPath = "setting.json";
#endif

    std::ifstream file(configPath);
    if (!file.is_open()) {
        return false;
    }

    std::stringstream buffer;
    buffer << file.rdbuf();
    file.close();

    std::string jsonContent = buffer.str();

    std::string defaultCharset = extractJsonValue(jsonContent, "Charset");
    if (!defaultCharset.empty()) {
        staticCharsetValue = extractJsonValue(jsonContent, defaultCharset);
        if (!staticCharsetValue.empty()) {
            CURRENT_ASCII_CHARS = staticCharsetValue.c_str();
        }
    }

    return true;
}

const char* CURRENT_ASCII_CHARS = " .:-=+*#%@";

int getAsciiCharSetLength() {
    return static_cast<int>(strlen(CURRENT_ASCII_CHARS));
}

std::vector<char> generateAsciiLookup() {
    int charSetLen = getAsciiCharSetLength();
    std::vector<char> lookup(256);
    for (int i = 0; i < 256; ++i) {
        lookup[i] = CURRENT_ASCII_CHARS[i * charSetLen / 256];
    }
    return lookup;
}

static std::vector<char> ASCII_LOOKUP = []() {
    loadConfig();
    return generateAsciiLookup();
}();

// ANSI转换常量
static constexpr const char* ANSI_RESET = "\033[0m";
static constexpr const char* ANSI_COLOR_PREFIX = "\033[38;2;";

// 像素转ASCII
inline char pixelToAscii(int value) {
    return ASCII_LOOKUP[value];
}

// 全彩ASCII帧生成函数
std::string generateColoredFrame(const cv::Mat& pixels, const cv::Mat& luminance) {
    const int height = pixels.rows;
    const int width = pixels.cols;

    if (height <= 0 || width <= 0) {
        return "";
    }

    // 预分配内存空间
    const size_t estimated_size = height * width * 25 + height * 10; 
    std::string result;
    result.reserve(estimated_size);

    const char* COLOR_PREFIX = "\033[38;2;";
    const char* COLOR_SUFFIX = "m";
    const char* RESET_CODE = "\033[0m\n";

    // 预分配线程局部缓冲区
    thread_local static std::string temp_buffer;
    temp_buffer.clear();
    temp_buffer.reserve(20);

    // 预分配数字转字符串的查找表
    thread_local static const std::array<std::string, 256> number_strings = []() {
        std::array<std::string, 256> arr;
        for (int i = 0; i < 256; ++i) {
            if (i >= 100) {
                arr[i] = std::string(1, '0' + i/100) + 
                         std::string(1, '0' + (i/10)%10) + 
                         std::string(1, '0' + i%10);
            } else if (i >= 10) {
                arr[i] = std::string(1, '0' + i/10) + 
                         std::string(1, '0' + i%10);
            } else {
                arr[i] = std::string(1, '0' + i);
            }
        }
        return arr;
    }();

    for (int y = 0; y < height; ++y) {
        const cv::Vec3b* pixelRow = pixels.ptr<cv::Vec3b>(y);
        const uchar* lumaRow = luminance.ptr<uchar>(y);

        for (int x = 0; x < width; ++x) {
            const cv::Vec3b& pixel = pixelRow[x];
            const uchar luma = lumaRow[x];

            // 构建颜色代码字符串
            temp_buffer.clear();
            temp_buffer.append(COLOR_PREFIX);
            temp_buffer.append(number_strings[pixel[0]]);  // R
            temp_buffer.append(1, ';');
            temp_buffer.append(number_strings[pixel[1]]);  // G
            temp_buffer.append(1, ';');
            temp_buffer.append(number_strings[pixel[2]]);  // B
            temp_buffer.append(COLOR_SUFFIX);
            temp_buffer.append(1, ASCII_LOOKUP[luma]);

            result.append(temp_buffer);
        }
        result.append(RESET_CODE);
    }

    return result;
}

// 生成灰度ASCII帧
std::string generateGrayscaleFrame(const cv::Mat& pixels) {
    const int height = pixels.rows;
    const int width = pixels.cols;

    if (height <= 0 || width <= 0) {
        return "";
    }

    const int pixelCount = height * width;

    // 预分配内存
    std::string result;
    result.reserve(pixelCount + height);

    const char NEWLINE = '\n';
    for (int y = 0; y < height; ++y) {
        const uchar* row = pixels.ptr<uchar>(y);
        for (int x = 0; x < width; ++x) {
            result.append(1, ASCII_LOOKUP[row[x]]);
        }
        result.append(1, NEWLINE);
    }

    return result;
}

// 处理帧
std::string processFrame(const cv::Mat& frame, int width, bool useColor) {
    if (frame.empty() || width <= 0) {
        return "";
    }

    // BGR转RGB
    cv::Mat frame_rgb;
    cv::cvtColor(frame, frame_rgb, cv::COLOR_BGR2RGB);

    // 计算保持宽高比的新高度
    const int frame_height = frame.rows;
    const int frame_width = frame.cols;

    if (frame_width == 0) {
        return "";
    }

    const double aspect = static_cast<double>(frame_height) / frame_width;
    const int new_height = std::max(1, static_cast<int>(aspect * width * 0.5));

    cv::Mat resized(new_height, width, CV_8UC3);
    const int interpolation = (frame_width > width * 2) ? cv::INTER_AREA : cv::INTER_LINEAR;
    cv::resize(frame_rgb, resized, cv::Size(width, new_height), 0, 0, interpolation);

    std::string result;
    if (useColor) {
        // 全彩
        cv::Mat gray;
        cv::cvtColor(resized, gray, cv::COLOR_RGB2GRAY);
        result = generateColoredFrame(resized, gray);
    } else {
        // 灰度
        cv::Mat gray;
        cv::cvtColor(resized, gray, cv::COLOR_RGB2GRAY);
        result = generateGrayscaleFrame(gray);
    }

    return result;
}

}