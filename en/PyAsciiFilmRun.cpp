#include <iostream>
#include <string>
#include <filesystem>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <algorithm>
#include <fstream>
#include <windows.h>
#include <shellapi.h>

namespace fs = std::filesystem;

// Launcher Class
class PyAsciiFilmLauncher {
private:
    fs::path currentDir; // Current directory
    std::string errorMessage; // Error message

    // Get system dirs, avoid temporary object lifetime issue
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

public:
    // Constructor: Get current exe directory
    PyAsciiFilmLauncher() {
        char path[MAX_PATH];
        GetModuleFileNameA(NULL, path, MAX_PATH);
        currentDir = fs::path(path).parent_path();
    }

    // Check if running as administrator
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

    // Check if running in a system directory
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

    // Request administrator privileges
    bool requestAdminPrivileges() {
        std::cout << "Requesting administrator privileges..." << std::endl;

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
                std::cout << "User cancelled the privilege request." << std::endl;
            }
            else {
                std::cout << "Failed to request privileges. Error: " << error << std::endl;
            }
            return false;
        }
    }

    // Setup virtual environment configuration
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
                    return true;
                }
                else {
                    errorMessage = "Error: Could not create/open .venv\\pyvenv.cfg.";
                }
            }
            else {
                errorMessage = "Error: .venv directory does not exist.";
            }
        }
        catch (const std::exception& e) {
            errorMessage = std::string("Error setting up virtual environment config: ") + e.what();
        }
        return false;
    }

    // Check Python virtual environment
    bool checkPythonVenv() {
        fs::path pythonExe = currentDir / ".venv" / "Scripts" / "python.exe";

        if (!fs::exists(pythonExe)) {
            errorMessage = "Error: Python executable not found in virtual environment.";
            return false;
        }
        return true;
    }

    // Check main program file
    bool checkMainPy() {
        fs::path mainPy = currentDir / "main.py";
        if (!fs::exists(mainPy)) {
            errorMessage = "Error: main.py main program file not found.";
            return false;
        }
        return true;
    }

    // Run the main program
    int runMainProgram() {
        fs::path pythonExe = currentDir / ".venv" / "Scripts" / "python.exe";
        fs::path mainPy = currentDir / "main.py";

        // Build command line
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
            errorMessage = "Failed to start main program. Error Code: " + std::to_string(error);
            return -1;
        }
    }

    // Pause and wait for user input
    void pause() {
        std::cout << "Press any key to continue...";
        std::cin.ignore();
        std::cin.get();
    }

    // Main run logic
    int run() {
        // Check if admin privileges are needed
        if (isInSystemDir() && !isAdmin()) {
            if (requestAdminPrivileges()) {
                return 0; // Admin process will restart
            }
            else {
                pause();
                return 1;
            }
        }

        // Setup virtual environment config
        if (!setupVenvConfig()) {
            std::cout << errorMessage << std::endl;
            pause();
            return 1;
        }

        // Check Python virtual environment
        if (!checkPythonVenv()) {
            std::cout << errorMessage << std::endl;
            pause();
            return 1;
        }

        // Check main program file
        if (!checkMainPy()) {
            std::cout << errorMessage << std::endl;
            pause();
            return 1;
        }

        // Run the main program
        int returnCode = runMainProgram();

        // Handle main program exit result
        if (returnCode != 0) {
            std::cout << std::endl;
            std::cout << "Program exited abnormally, error code: " << returnCode << std::endl;
        }
        else {
            std::cout << "Program exited normally." << std::endl;
        }

        // Pause and wait for user input before exit
        pause();
        return returnCode;
    }
};

// Program entry point
int main() {
    SetConsoleOutputCP(936);

    PyAsciiFilmLauncher launcher;
    return launcher.run();
}