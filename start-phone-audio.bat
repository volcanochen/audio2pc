@echo off
chcp 936 >nul 2>&1
title 手机声音 串流到 电脑音箱 - scrcpy
cd /d "%~dp0"

set "SCRCPY=%~dp0tools\scrcpy\scrcpy.exe"
set "ADB=%~dp0tools\scrcpy\adb.exe"

if not exist "%SCRCPY%" (
    echo [错误] 找不到 scrcpy.exe，请确认 tools\scrcpy 目录完整。
    pause
    exit /b 1
)

:MENU
cls
echo ==========================================================
echo    手机声音  ->->->  电脑音箱        [scrcpy 4.1 / adb]
echo ==========================================================
echo.
echo    [1]  USB 有线 - 仅音频            ^(推荐，延迟最低^)
echo    [2]  USB 有线 - 仅音频 - 超低延迟  ^(打游戏/看视频^)
echo    [3]  USB 有线 - 画面 + 声音        ^(等于投屏^)
echo    [4]  WiFi 无线 - 仅音频            ^(需先配对一次^)
echo    [5]  USB 有线 - 电脑音箱 + 手机扬声器同时出声
echo    [6]  检查设备连接状态
echo    [0]  退出
echo.
set "CHOICE="
set /p CHOICE=请输入数字后回车 [0-6] : 

if "%CHOICE%"=="1" goto A1
if "%CHOICE%"=="2" goto A2
if "%CHOICE%"=="3" goto A3
if "%CHOICE%"=="4" goto A4
if "%CHOICE%"=="5" goto A5
if "%CHOICE%"=="6" goto A6
if "%CHOICE%"=="0" goto END
goto MENU

:A1
echo.
echo 正在启动：USB 仅音频转发（手机扬声器会静音，声音全部从电脑出来）
echo 按 Ctrl+C 结束串流。
echo.
"%SCRCPY%" --no-video --no-window
goto AFTER

:A2
echo.
echo 正在启动：USB 仅音频 - 超低延迟模式
echo 若出现爆音/断音，请改回 [1] 标准模式。
echo.
"%SCRCPY%" --no-video --no-window --audio-buffer=25 --audio-output-buffer=5
goto AFTER

:A3
echo.
echo 正在启动：画面 + 声音（关闭本窗口即结束）
echo.
"%SCRCPY%" --max-size=1280 --max-fps=60
goto AFTER

:A4
call "%~dp0audio-wifi.bat"
goto AFTER

:A5
echo.
echo 正在启动：电脑音箱 与 手机扬声器 同时出声
echo.
"%SCRCPY%" --no-video --no-window --audio-dup
goto AFTER

:A6
cls
echo === 已连接的设备 ===
"%ADB%" devices -l
echo.
echo 说明：
echo   - 列表为空        : 手机没连上。检查数据线是否支持传数据、USB 调试是否打开
echo   - unauthorized    : 手机上没点「允许 USB 调试」，拔插一次再看弹窗
echo   - device          : 正常
echo.
pause
goto MENU

:AFTER
echo.
echo 串流已结束。
pause
goto MENU

:END
"%ADB%" kill-server >nul 2>&1
exit /b 0
