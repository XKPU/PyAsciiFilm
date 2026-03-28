#ifndef ASCII_H
#define ASCII_H

#include <string>
#include <vector>
#include <opencv2/opencv.hpp>

namespace AsciiFilm {
extern const char* CURRENT_ASCII_CHARS;
int getAsciiCharSetLength();
std::vector<char> generateAsciiLookup();
std::string processFrame(const cv::Mat& frame, int width, bool useColor);
}

#endif