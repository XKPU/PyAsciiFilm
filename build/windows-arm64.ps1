param(
    [ValidateSet('standalone', 'onefile')]
    [string]$Mode = 'standalone'
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$Version = (Get-Content version.txt -Raw).Trim()
$Suffix = 'windows_arm64'
$OutName = "PyAsciiFilm-v$Version-$Suffix.exe"

if ($Mode -eq 'standalone') {
    $OutDir = 'dist/standalone'
    $ModeFlag = '--standalone'
} else {
    $OutDir = 'dist/onefile'
    $ModeFlag = '--onefile'
}

if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

python -m nuitka `
    $ModeFlag `
    --follow-imports `
    --assume-yes-for-downloads `
    --enable-plugin=tk-inter `
    --include-package=textual `
    --include-package=rich._unicode_data `
    --include-package=imageio_ffmpeg `
    --include-module=miniaudio `
    --output-filename="$OutName" `
    --output-dir="$OutDir" `
    --lto=yes `
    --windows-company-name=K_PU `
    --windows-product-name=PyAsciiFilm `
    --windows-file-version=$Version `
    --windows-product-version=$Version `
    src/main.py

if ($LASTEXITCODE -ne 0) { throw "nuitka failed (exit $LASTEXITCODE)" }

if ($Mode -eq 'standalone') {
    $distFolder = Get-ChildItem -Path $OutDir -Directory -Filter '*.dist' | Select-Object -First 1
    if (-not $distFolder) { throw "build failed: no .dist directory in $OutDir" }
    $zip = Join-Path $OutDir "$($distFolder.Name).zip"
    7z a -tzip -mx=9 $zip "$($distFolder.FullName)\*" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "packaging failed (exit $LASTEXITCODE)" }
    Write-Host "artifact: $zip"
} else {
    Write-Host "artifact: $OutDir/$OutName"
}
