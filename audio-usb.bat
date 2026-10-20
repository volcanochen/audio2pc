@echo off
chcp 936 >nul 2>&1
title 手机声音 -> 电脑音箱 (USB)
cd /d "%~dp0"

set "SCRCPY=%~dp0tools\scrcpy\scrcpy.exe"
set "ADB=%~dp0tools\scrcpy\adb.exe"

if not exist "%SCRCPY%" (
    echo.
    echo [错误] 找不到 tools\scrcpy\scrcpy.exe
    echo.
    pause
    exit /b 1
)

echo.
echo   手机声音 串流到 电脑音箱  [USB / 仅音频]
echo   手机扬声器会静音，声音全部从电脑音箱出来。
echo   按 Ctrl+C 或关闭窗口结束。
echo.

"%ADB%" devices | findstr /r /c:"device$" >nul
if errorlevel 1 (
    echo ----------------------------------------------------------
    echo   没有检测到可用的手机设备，请检查：
    echo.
    echo   1. 手机是否用【数据线】连上电脑（部分充电线不能传数据）
    echo   2. 开发者选项 - USB 调试 是否已打开
    echo      （设置 - 关于手机 - 连点「版本号」7 次 开启开发者选项）
    echo   3. 手机上是否点过「允许 USB 调试」的弹窗
    echo   4. 手机系统需要 Android 11 及以上
    echo ----------------------------------------------------------
    echo.
    echo   当前 adb 设备列表：
    "%ADB%" devices -l
    echo.
    pause
    exit /b 1
)

"%SCRCPY%" --no-video --no-window

echo.
echo 串流已结束。
pause
