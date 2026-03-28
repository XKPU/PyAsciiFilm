#include <iostream>
#include <windows.h>
#include <shlobj.h>
#include <comdef.h>
#include <string>
#include <filesystem>
#include "player.h"
#include "ascii.h"

#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "ole32.lib")

namespace AsciiFilm {

// 全局音频进程句柄
static PROCESS_INFORMATION g_audioProcess = {0};

// 清理函数
void cleanupOnExit() {
    if (g_audioProcess.hProcess != NULL) {
        TerminateProcess(g_audioProcess.hProcess, 0);
        WaitForSingleObject(g_audioProcess.hProcess, 1000);
        CloseHandle(g_audioProcess.hProcess);
        CloseHandle(g_audioProcess.hThread);
        g_audioProcess.hProcess = NULL;
    }
}

// 选择视频文件
std::string selectVideoFile() {
    OPENFILENAME ofn = {0};
    char szFile[MAX_PATH] = {0};

    ofn.lStructSize = sizeof(OPENFILENAME);
    ofn.hwndOwner = NULL;
    ofn.lpstrFilter = "视频文件\0*.mp4;*.avi;*.mkv;*.mov;*.wmv\0所有文件\0*.*\0";
    ofn.lpstrFile = szFile;
    ofn.nMaxFile = MAX_PATH;
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_HIDEREADONLY;
    ofn.lpstrTitle = "选择视频文件";

    if (GetOpenFileName(&ofn)) {
        return std::string(szFile);
    }
    return "";
}

// 询问是否播放音频
bool askAudioPlay() {
    std::string choice;
    while (true) {
        std::cout << "是否播放音频(回车默认播放，输入n不播放): ";
        std::getline(std::cin, choice);
        if (choice.empty() || choice == "y" || choice == "Y") {
            return true;
        } else if (choice == "n" || choice == "N") {
            return false;
        }
        std::cout << "无效输入，请输入 y 或 n" << std::endl;
    }
}

// 询问显示模式
bool askColorMode() {
    std::string choice;
    while (true) {
        std::cout << "是否使用全彩播放(回车默认灰度，输入y全彩): ";
        std::getline(std::cin, choice);
        if (choice.empty() || choice == "n" || choice == "N") {
            return false;
        } else if (choice == "y" || choice == "Y") {
            return true;
        }
        std::cout << "无效输入，请输入 y 或 n" << std::endl;
    }
}

// 音频播放
PROCESS_INFORMATION playAudio(const std::string& videoPath) {
    PROCESS_INFORMATION pi = {0};
    STARTUPINFO si = {0};
    si.cb = sizeof(STARTUPINFO);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    si.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
    si.hStdError = GetStdHandle(STD_ERROR_HANDLE);

    // 获取当前执行文件所在目录
    char exePath[MAX_PATH];
    GetModuleFileNameA(NULL, exePath, MAX_PATH);
    std::string exeDir = exePath;
    size_t pos = exeDir.find_last_of("\\/");
    if (pos != std::string::npos) {
        exeDir = exeDir.substr(0, pos);
    }

    std::string ffplayPath = exeDir + "\\ffplay.exe";

    DWORD attrs = GetFileAttributesA(ffplayPath.c_str());
    if (attrs == INVALID_FILE_ATTRIBUTES) {
        std::cout << "找不到ffplay.exe，将无音频播放" << std::endl;
        return pi;
    }

    std::string cmdLine = "\"" + ffplayPath + "\" -nodisp -autoexit -vn \"" + videoPath + "\"";

    if (!CreateProcessA(NULL, const_cast<char*>(cmdLine.c_str()), NULL, NULL,
                        FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        std::cout << "无法启动音频播放" << std::endl;
        return pi;
    }

    g_audioProcess = pi;

    return pi;
}

// 主函数入口
int main() {
    atexit(cleanupOnExit);

    SetConsoleCtrlHandler([](DWORD dwCtrlType) -> BOOL {
        if (dwCtrlType == CTRL_C_EVENT || dwCtrlType == CTRL_CLOSE_EVENT) {
            cleanupOnExit();
            return TRUE;
        }
        return FALSE;
    }, TRUE);

    SetConsoleOutputCP(65001);
    SetConsoleCP(65001);

    HANDLE hStdOut = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD dwMode = 0;
    GetConsoleMode(hStdOut, &dwMode);
    dwMode |= ENABLE_VIRTUAL_TERMINAL_PROCESSING;
    SetConsoleMode(hStdOut, dwMode);

    std::string videoPath = selectVideoFile();
    if (videoPath.empty()) {
        std::cout << "未选择视频文件，程序退出" << std::endl;
        return 0;
    }

    std::cout << "=== CppAsciiFilm 视频播放器 ===" << std::endl;
    std::cout << "已选择视频: " << videoPath << std::endl;

    bool playAudioFlag = askAudioPlay();
    bool useColor = askColorMode();

    PROCESS_INFORMATION audioProcess = {0};
    if (playAudioFlag) {
        audioProcess = playAudio(videoPath);
    }

    try {
        playVideo(videoPath, useColor);
    } catch (const std::exception& e) {
        std::cout << "\n[错误] 播放过程中发生异常: " << e.what() << std::endl;
    }

    cleanupOnExit();

    std::cout << "\n程序已退出" << std::endl;
    return 0;
}

}

int main() {
    return AsciiFilm::main();
}