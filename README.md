# PyAsciiFilm

![构建-Windows-x64](https://img.shields.io/badge/Windows-x64-blue?logo=data:image/svg%2bxml;base64,PHN2ZyB0PSIxNzg2ODcyNzIwMTU2IiBjbGFzcz0iaWNvbiIgdmlld0JveD0iMCAwIDEwMjQgMTAyNCIgdmVyc2lvbj0iMS4xIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHAtaWQ9IjM3NzMiIHdpZHRoPSIyMDAiIGhlaWdodD0iMjAwIj48cGF0aCBkPSJNNDE5Ljg0IDU0MC4xNnY0MDAuMzg0TDAgODgzLjJ2LTM0Mi41MjhoNDE5Ljg0eiBtMC00NTcuMjE2djQwNS41MDRIMFYxNDAuOGw0MTkuODQtNTcuODU2eiBtNjA0LjE2IDQ1Ny4yMTZWMTAyNEw0NjUuOTIgOTQ3LjJ2LTQwNi41MjhoNTU4LjA4ek0xMDI0IDB2NDg4LjQ0OEg0NjUuOTJWNzYuOEwxMDI0IDB6IiBmaWxsPSIjZmZmZmZmIiBwLWlkPSIzNzc0Ij48L3BhdGg+PC9zdmc+)
![构建-Windows-ARM64](https://img.shields.io/badge/Windows-ARM64-blue?logo=data:image/svg%2bxml;base64,PHN2ZyB0PSIxNzg2ODcyNzIwMTU2IiBjbGFzcz0iaWNvbiIgdmlld0JveD0iMCAwIDEwMjQgMTAyNCIgdmVyc2lvbj0iMS4xIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHAtaWQ9IjM3NzMiIHdpZHRoPSIyMDAiIGhlaWdodD0iMjAwIj48cGF0aCBkPSJNNDE5Ljg0IDU0MC4xNnY0MDAuMzg0TDAgODgzLjJ2LTM0Mi41MjhoNDE5Ljg0eiBtMC00NTcuMjE2djQwNS41MDRIMFYxNDAuOGw0MTkuODQtNTcuODU2eiBtNjA0LjE2IDQ1Ny4yMTZWMTAyNEw0NjUuOTIgOTQ3LjJ2LTQwNi41MjhoNTU4LjA4ek0xMDI0IDB2NDg4LjQ0OEg0NjUuOTJWNzYuOEwxMDI0IDB6IiBmaWxsPSIjZmZmZmZmIiBwLWlkPSIzNzc0Ij48L3BhdGg+PC9zdmc+)

![构建-Linux-x64](https://img.shields.io/badge/Linux-x64-brightgreen?logo=linux)
![构建-Linux-ARM64](https://img.shields.io/badge/Linux-ARM64-brightgreen?logo=linux)

![构建-macOS-x64](https://img.shields.io/badge/macOS-x64-red?logo=apple)
![构建-macOS-ARM64](https://img.shields.io/badge/macOS-ARM64-red?logo=apple)

[![版本](https://img.shields.io/github/v/release/XKPU/PyAsciiFilm?logo=github)](https://github.com/XKPU/PyAsciiFilm/releases)
[![许可证](https://img.shields.io/github/license/XKPU/PyAsciiFilm?logo=data:image/svg+xml;base64,PHN2ZyB0PSIxNzg2ODczMTA1MjgwIiBjbGFzcz0iaWNvbiIgdmlld0JveD0iMCAwIDEwMjQgMTAyNCIgdmVyc2lvbj0iMS4xIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHAtaWQ9IjY2MzEiIHdpZHRoPSIyMDAiIGhlaWdodD0iMjAwIj48cGF0aCBkPSJNNTEyIDE2QzIzOC4wNjYgMTYgMTYgMjM4LjA2NiAxNiA1MTJzMjIyLjA2NiA0OTYgNDk2IDQ5NiA0OTYtMjIyLjA2NiA0OTYtNDk2Uzc4NS45MzQgMTYgNTEyIDE2eiBtMCA4OTZjLTIyMS4wNjQgMC00MDAtMTc4LjkwMi00MDAtNDAwIDAtMjIxLjA2MiAxNzguOTAyLTQwMCA0MDAtNDAwIDIyMS4wNjQgMCA0MDAgMTc4LjkwMiA0MDAgNDAwIDAgMjIxLjA2NC0xNzguOTAyIDQwMC00MDAgNDAweiBtMjE0LjcwMi0yMDIuMTI4Yy0xOS4yMjggMTkuNDI0LTkxLjA2IDgyLjc5Mi0yMDguMTMgODIuNzkyLTE2NC44NiAwLTI4MC45NjgtMTIyLjg1LTI4MC45NjgtMjgzLjEzNCAwLTE1OC4zMDQgMTIwLjU1LTI3OC44MDIgMjc5LjUyNC0yNzguODAyIDExMS4wNjIgMCAxNzcuNDc2IDUzLjI0IDE5NS4xODYgNjkuNTU4YTIzLjkzIDIzLjkzIDAgMCAxIDMuODcyIDMwLjY0NGwtMzYuMzEgNTYuMjI2Yy03LjY4MiAxMS45LTIzLjkzMiAxNC41NjQtMzQuOTk4IDUuODQyLTE3LjE5LTEzLjU1Mi02My42MjgtNDUuMDc2LTEyMy40MTYtNDUuMDc2LTk2LjYwNiAwLTE1NS44MzIgNzAuNjYtMTU1LjgzMiAxNjAuMTY0IDAgODMuMTc4IDUzLjc3NiAxNjcuMzg0IDE1Ni41NTQgMTY3LjM4NCA2NS4zMTQgMCAxMDMuNjg2LTM4LjA3OCAxMzEuNDUyLTU0LjQ1IDEwLjU0LTkuNzE0IDI3LjE5Mi04LjA3OCAzNS42NCAzLjQ3NmwzOS43MyA1NC4zNGEyMy44OTQgMjMuODk0IDAgMCAxLTIuMzA0IDMxLjAzNnoiIGZpbGw9IiNmZmZmZmYiIHAtaWQ9IjY2MzIiPjwvcGF0aD48L3N2Zz4=)](https://github.com/XKPU/PyAsciiFilm/blob/main/LICENSE)

一个基于 Python 开发的创意工具，能够将视频实时转换为 ASCII 字符画，并直接在终端中进行流畅播放。同时支持将字符画视频导出为标准的视频文件。

## 运行时依赖库

运行源码需要以下 Python 依赖：

- `numpy`
- `opencv-python`
- `pillow`
- `imageio-ffmpeg`
- `textual`
- `miniaudio`
- `zstandard`

## 构建

### 支持目标

| 平台 | 架构 | 输出格式 | Runner |
|------|------|----------|--------|
| Windows | ARM64 | `.exe` | `windows-latest` |
| Windows | x86_64 | `.exe` | `windows-latest` |
| Linux | x86_64 | 二进制可执行文件 | `ubuntu-latest` |
| Linux | aarch64 (ARM64) | 二进制可执行文件 | `ubuntu-latest` |
| macOS | aarch64 (Apple Silicon) | 二进制可执行文件 | `macos-latest` |

### 构建配置说明

- `.github/workflows/ci.yml` — GitHub Actions 自动化构建流水线（6 个平台）

## 许可证

本项目基于 [GNU Affero General Public License v3.0](LICENSE) 开源。
