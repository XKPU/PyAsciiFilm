#ifndef PLAYER_H
#define PLAYER_H

#include <string>
#include <memory>
#include <utility>

namespace AsciiFilm {
class VideoPlayer {
public:
    VideoPlayer(const std::string& videoPath, int asciiWidth = 80, bool useColor = false);
    ~VideoPlayer();
    
    bool initialize();
    void play();
    void stop();
private:
    class Impl;
    std::unique_ptr<Impl> pimpl_;
};
void playVideo(const std::string& videoPath, bool useColor = false);
std::pair<int, int> getTerminalSize();
}

#endif