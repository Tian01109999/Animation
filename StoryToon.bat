@echo off
rem StoryToon - cua so desktop, du lieu cung thu muc voi EXE
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist "%~dp0StoryToon-Desktop-Portable.exe" (
  echo Khong tim thay StoryToon-Desktop-Portable.exe trong thu muc chinh.
  pause
  exit /b 1
)
start "" "%~dp0StoryToon-Desktop-Portable.exe" %*
endlocal
