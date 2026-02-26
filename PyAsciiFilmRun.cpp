#include <iostream>
#include <string>
#include <filesystem>
#include <cstring>
#include <vector>
#include <algorithm>
#include <fstream>
#include <windows.h>
#include <shellapi.h>

namespace fs = std::filesystem;

// 启动器类
class PyAsciiFilmLauncher {
private:
    fs::path currentDir; // 当前目录
    std::string errorMessage; // 错误信息

    // 获取系统目录，避免临时对象生命周期问题
    std::vector<std::string> getSystemDirs() {
        std::vector<std::string> systemDirs;
        char buffer[MAX_PATH];

        if (GetEnvironmentVariableA("PROGRAMFILES", buffer, MAX_PATH)) {
            systemDirs.push_back(std::string(buffer));
        }
        if (GetEnvironmentVariableA("PROGRAMFILES(X86)", buffer, MAX_PATH)) {
            systemDirs.push_back(std::string(buffer));
        }
        if (GetEnvironmentVariableA("WINDIR", buffer, MAX_PATH)) {
            systemDirs.push_back(std::string(buffer) + "\\system32");
        }

        return systemDirs;
    }

    // 更新文件中的 VIRTUAL_ENV 变量
    void updateVirtualEnvInFile(const fs::path& filePath, const std::string& newVirtualEnvLine) {
        std::vector<std::string> lines;
        std::ifstream inFile(filePath.string());
        if (inFile.is_open()) {
            std::string line;
            bool foundVirtualEnv = false;
            while (std::getline(inFile, line)) {
                if (line.find("VIRTUAL_ENV") != std::string::npos) {
                    lines.push_back(newVirtualEnvLine);
                    foundVirtualEnv = true;
                }
                else {
                    lines.push_back(line);
                }
            }
            inFile.close();

            if (!foundVirtualEnv) {
                lines.push_back(newVirtualEnvLine);
            }

            std::ofstream outFile(filePath.string());
            if (outFile.is_open()) {
                for (const auto& l : lines) {
                    outFile << l << "\n";
                }
                outFile.close();
            }
        }
    }

public:
    // 构造函数：获取当前可执行文件目录
    PyAsciiFilmLauncher() {
        char path[MAX_PATH];
        GetModuleFileNameA(NULL, path, MAX_PATH);
        currentDir = fs::path(path).parent_path();
    }

    // 检查是否具有管理员权限
    bool isAdmin() {
        BOOL isAdmin = FALSE;
        PSID adminGroup = NULL;
        SID_IDENTIFIER_AUTHORITY ntAuthority = SECURITY_NT_AUTHORITY;

        if (AllocateAndInitializeSid(&ntAuthority, 2, SECURITY_BUILTIN_DOMAIN_RID,
            DOMAIN_ALIAS_RID_ADMINS, 0, 0, 0, 0, 0, 0, &adminGroup)) {
            if (!CheckTokenMembership(NULL, adminGroup, &isAdmin)) {
                isAdmin = FALSE;
            }
            FreeSid(adminGroup);
        }
        return isAdmin == TRUE;
    }

    // 检查是否在系统目录中运行
    bool isInSystemDir() {
        std::string currentPath = currentDir.string();
        std::transform(currentPath.begin(), currentPath.end(), currentPath.begin(), ::tolower);

        auto systemDirs = getSystemDirs();

        for (const auto& sysDir : systemDirs) {
            std::string sysDirLower = sysDir;
            std::transform(sysDirLower.begin(), sysDirLower.end(), sysDirLower.begin(), ::tolower);
            if (currentPath.find(sysDirLower) == 0) {
                return true;
            }
        }

        return false;
    }

    // 请求管理员权限
    bool requestAdminPrivileges() {
        std::cout << "正在请求管理员权限..." << std::endl;

        char path[MAX_PATH];
        GetModuleFileNameA(NULL, path, MAX_PATH);

        std::string currentDirStr = currentDir.string();

        SHELLEXECUTEINFOA sei = { 0 };
        sei.cbSize = sizeof(sei);
        sei.lpVerb = "runas";
        sei.lpFile = path;
        sei.lpDirectory = currentDirStr.c_str();
        sei.nShow = SW_SHOWNORMAL;

        if (ShellExecuteExA(&sei)) {
            return true;
        }
        else {
            DWORD error = GetLastError();
            if (error == ERROR_CANCELLED) {
                std::cout << "用户取消了权限请求。" << std::endl;
            }
            else {
                std::cout << "请求权限失败。错误代码: " << error << std::endl;
            }
            return false;
        }
    }

    // 设置虚拟环境配置
    bool setupVenvConfig() {
        fs::path venvCfgPath = currentDir / ".venv" / "pyvenv.cfg";
        fs::path pythonPath = currentDir / "python";

        try {
            if (fs::exists(venvCfgPath.parent_path())) {
                std::ofstream file(venvCfgPath.string());
                if (file.is_open()) {
                    file << "home = " << pythonPath.string() << "\n";
                    file << "include-system-site-packages = false\n";
                    file << "version = 3.8.0\n";
                    file.close();
                }
                else {
                    errorMessage = "错误：无法创建/打开 .venv\\pyvenv.cfg。";
                    return false;
                }

                return true;
            }
            else {
                errorMessage = "错误：.venv 目录不存在。";
            }
        }
        catch (const std::exception& e) {
            errorMessage = "设置虚拟环境配置时出错: " + std::string(e.what());
        }
        return false;
    }

    // 检查 Python 虚拟环境
    bool checkPythonVenv() {
        fs::path pythonExe = currentDir / ".venv" / "Scripts" / "python.exe";

        if (!fs::exists(pythonExe)) {
            errorMessage = "错误: 找不到虚拟环境中的Python可执行文件";
            return false;
        }
        return true;
    }

    // 检查主程序文件
    bool checkMainPy() {
        fs::path mainPy = currentDir / "main.py";
        if (!fs::exists(mainPy)) {
            errorMessage = "错误: 找不到 main.py 主程序文件";
            return false;
        }
        return true;
    }

    // 运行主程序
    int runMainProgram() {
        fs::path pythonExe = currentDir / ".venv" / "Scripts" / "python.exe";
        fs::path mainPy = currentDir / "main.py";

        // 构建命令行
        std::string command = "\"" + pythonExe.string() + "\" \"" + mainPy.string() + "\"";

        STARTUPINFOA si = { 0 };
        PROCESS_INFORMATION pi = { 0 };
        si.cb = sizeof(si);

        if (CreateProcessA(NULL, (LPSTR)command.c_str(), NULL, NULL, FALSE,
            0, NULL, NULL, &si, &pi)) {
            WaitForSingleObject(pi.hProcess, INFINITE);

            DWORD exitCode;
            GetExitCodeProcess(pi.hProcess, &exitCode);

            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);

            return static_cast<int>(exitCode);
        }
        else {
            DWORD error = GetLastError();
            errorMessage = "启动主程序失败。错误代码: " + std::to_string(error);
            return -1;
        }
    }

    // 暂停等待用户按键
    void pause() {
        std::cout << "按任意键继续...";
        std::cin.ignore();
        std::cin.get();
    }

    // 主运行逻辑
    int run() {
        // 检查是否需要管理员权限
        if (isInSystemDir() && !isAdmin()) {
            if (requestAdminPrivileges()) {
                return 0; // 管理员进程会重新启动
            }
            else {
                pause();
                return 1;
            }
        }

        // 设置虚拟环境配置
        if (!setupVenvConfig()) {
            std::cout << errorMessage << std::endl;
            pause();
            return 1;
        }

        // 检查Python虚拟环境
        if (!checkPythonVenv()) {
            std::cout << errorMessage << std::endl;
            pause();
            return 1;
        }

        // 检查主程序文件
        if (!checkMainPy()) {
            std::cout << errorMessage << std::endl;
            pause();
            return 1;
        }

        // 运行主程序
        int returnCode = runMainProgram();

        // 处理主程序退出结果
        if (returnCode != 0) {
            std::cout << std::endl;
            std::cout << "程序异常退出，错误代码：" << returnCode << std::endl;
        }
        else {
            std::cout << "程序正常退出。" << std::endl;
        }

        // 暂停并等待用户按键退出
        pause();
        return returnCode;
    }
};

// 程序入口点
int main() {
    // 设置控制台代码页为 GBK (CP936) 以支持中文输出
    SetConsoleOutputCP(936);

    PyAsciiFilmLauncher launcher;
    return launcher.run();
}
