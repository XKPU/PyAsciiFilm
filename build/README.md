# Build scripts

One script per platform/architecture. This is the single source of truth for
build logic. CI only selects a runner, installs dependencies, calls the script
and uploads artifacts. Change build parameters here and every workflow picks
them up.

## Scripts

| Script | Platform | Usage |
|---|---|---|
| `linux-x64.sh` | Linux x86_64 | `bash build/linux-x64.sh [standalone\|onefile]` |
| `linux-arm64.sh` | Linux arm64 | `bash build/linux-arm64.sh [standalone\|onefile]` |
| `macos-arm64.sh` | macOS arm64 | `bash build/macos-arm64.sh [standalone\|onefile]` |
| `windows-x64.ps1` | Windows x86_64 | `pwsh -File build/windows-x64.ps1 -Mode standalone` |
| `windows-arm64.ps1` | Windows arm64 | `pwsh -File build/windows-arm64.ps1 -Mode standalone` |

## Naming

Both the binary and the archive use `PyAsciiFilm-v<version>-<platform>_<arch>`:

| Platform | Binary | Archive |
|----------|--------|---------|
| Linux x86_64 | `PyAsciiFilm-v3.1.1-linux_x64` | `PyAsciiFilm-v3.1.1-linux_x64.tar.gz` |
| Linux arm64 | `PyAsciiFilm-v3.1.1-linux_arm64` | `PyAsciiFilm-v3.1.1-linux_arm64.tar.gz` |
| macOS arm64 | `PyAsciiFilm-v3.1.1-macos_arm64` | `PyAsciiFilm-v3.1.1-macos_arm64.zip` |
| Windows x86_64 | `PyAsciiFilm-v3.1.1-windows_x64.exe` | `PyAsciiFilm-v3.1.1-windows_x64.zip` |
| Windows arm64 | `PyAsciiFilm-v3.1.1-windows_arm64.exe` | `PyAsciiFilm-v3.1.1-windows_arm64.zip` |

The Windows binary keeps its `.exe` suffix so it stays double-clickable.
The archive name comes from `$OUT_NAME` (or `$BaseName` on Windows), not from
the Nuitka `.dist` directory name, which is always `main.dist`.

## Modes

- `standalone` -> directory output in `dist/standalone/<name>.dist/`
  - Linux: packed as `*.tar.gz` (tar/gzip are BaseOS, no zip install needed)
  - Windows/macOS: packed as `*.zip`
  - all platforms pack the **contents** of `<name>.dist/`, with no top-level
    directory inside the archive; extracting drops the program files directly
    into the current directory
- `onefile` -> single file in `dist/onefile/PyAsciiFilm-v<version>-<platform>_<arch>`

The two modes write to different directories and never overwrite each other.

## Containers

`containers/Dockerfile.linux-x64` and `containers/Dockerfile.linux-arm64`
define the Linux build environment, based on `quay.io/pypa/manylinux_2_28_*`.

Two constraints drive this:

1. **glibc baseline.** glibc cannot be bundled with the program (it is the
   dynamic loader itself, loaded by the kernel before the executable). The
   build machine's glibc is therefore the compatibility floor of the artifact.
   `ubuntu-latest` has moved to 24.04 (glibc 2.39), which produces artifacts
   requiring `GLIBC_2.38` that refuse to start on Ubuntu 22.04 (glibc 2.35).
   `manylinux_2_28` lowers the floor to glibc 2.28.
2. **Static libpython.** The manylinux Python is statically linked; there is no
   `libpython3.10.so`. Nuitka `--standalone` needs a linkable libpython or it
   aborts with `FATAL: Automatic detection of static libpython failed.` The
   Dockerfile extracts the official static library shipped in the image.

Build the image locally:

```bash
docker build -f build/containers/Dockerfile.linux-x64 -t pyasciifilm-linux-x64 .
```

Run a build inside it:

```bash
docker run --rm -v "$PWD:/w" -w /w pyasciifilm-linux-x64 bash build/linux-x64.sh standalone
```

## Artifact verification

All platforms verify the packed artifact and fail the build otherwise:

1. archive must contain no top-level `<name>.dist/` directory
2. archive must contain at least 10 files (rejects a hollow directory)
3. on Linux, the highest required glibc symbol version is printed for review

Packing must run with the `.dist` directory as the working directory:
`tar -C "$distFolder" .` for Linux, a subshell `cd` for macOS `zip`, and
`Push-Location` for Windows `7z`. Passing a bare `main.dist` name to `zip`
from the repo root makes zip exit **12** (`Nothing to do!`) even though Nuitka
already reported success.

`find ... | head -1` is avoided in favour of `find ... -print -quit`: under
`set -o pipefail`, `head` closing the pipe early makes `find` die of SIGPIPE
and aborts the script with exit 141.

## Manual builds

Install dependencies first:

```bash
pip install "nuitka>=2.3.7" ordered-set zstandard -r requirements.txt
```

On Linux use the container as shown above; the scripts require the manylinux
environment.

## Note on the PowerShell scripts

Both `.ps1` files must be saved as **UTF-8 with BOM**. Windows PowerShell 5.1
decodes BOM-less files as ANSI, which corrupts the file and breaks `param()`
with a `ParserError`. Keep the BOM when re-saving in an editor.
