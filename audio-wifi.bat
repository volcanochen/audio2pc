@echo off
chcp 936 >nul 2>&1
title 手机声音 - WiFi 无线串流到电脑
cd /d "%~dp0"

set "SCRCPY=%~dp0tools\scrcpy\scrcpy.exe"
set "ADB=%~dp0tools\scrcpy\adb.exe"
set "IPFILE=%TEMP%\pa_wlan_ip.txt"

echo ==========================================================
echo   WiFi 无线音频串流  -  首次配置向导
echo ==========================================================
echo.
echo 第一步：先用 USB 数据线把手机连到电脑（只需一次）。
echo         手机需开启「开发者选项 - USB 调试」。
echo.
pause

echo.
echo 正在检测 USB 设备...
"%ADB%" devices | findstr /r /c:"device$" >nul
if errorlevel 1 goto NOUSB

echo [OK] 检测到设备，正在开启无线调试端口 5555 ...
"%ADB%" tcpip 5555
timeout /t 2 >nul

"%ADB%" shell ip -f inet addr show wlan0 > "%IPFILE%" 2>nul
set "PHONEIP="
for /f "tokens=2 delims=/ " %%i in ('findstr /r /c:"inet " "%IPFILE%"') do (
    if not defined PHONEIP set "PHONEIP=%%i"
)

if not defined PHONEIP (
    "%ADB%" shell ip route > "%IPFILE%" 2>nul
    for /f "tokens=7" %%i in ('findstr /r /c:"src " "%IPFILE%"') do (
        if not defined PHONEIP set "PHONEIP=%%i"
    )
)

if not defined PHONEIP (
    echo 自动获取 IP 失败，请手动输入。
    set /p PHONEIP=手机 IP 地址（设置 - WLAN - 当前网络详情）: 
)

if not defined PHONEIP goto NOUSB

echo.
echo 手机 IP : %PHONEIP%
echo 正在连接 %PHONEIP%:5555 ...
"%ADB%" connect %PHONEIP%:5555
timeout /t 2 >nul

echo.
echo ----------------------------------------------------------
echo  现在可以拔掉 USB 线了。
echo ----------------------------------------------------------
pause

echo.
echo 正在启动无线音频串流（手机扬声器静音，声音走电脑音箱）...
"%SCRCPY%" --no-video --no-window --tcpip=%PHONEIP%:5555
goto DONE

:NOUSB
echo.
echo [提示] 没有检测到已授权的 USB 设备。
echo.
echo 如果你的手机是 Android 11 以上，也可以用「无线调试」配对：
echo   手机：开发者选项 - 无线调试 - 使用配对码配对设备
echo   屏幕上会显示 IP:端口 和 配对码，填进来即可。
echo   （直接回车则跳过配对，改用手动 IP 连接）
echo.
set "PAIRADDR="
set /p PAIRADDR=配对地址 IP:端口 （如 192.168.1.5:37651）: 
if defined PAIRADDR (
    set "PAIRCODE="
    set /p PAIRCODE=配对码: 
    "%ADB%" pair %PAIRADDR% %PAIRCODE%
)

set "PHONEIP="
set /p PHONEIP=手机的无线调试 IP:端口 （如 192.168.1.5:5555）: 
if not defined PHONEIP (
    echo 未输入地址，已取消。
    pause
    exit /b 1
)
"%ADB%" connect %PHONEIP%
timeout /t 2 >nul
"%ADB%" devices -l
echo.
echo 正在启动无线音频串流...
"%SCRCPY%" --no-video --no-window --tcpip=%PHONEIP%

:DONE
echo.
echo 结束。
pause
exit /b 0
