# PhoneAudioDock

**English below** — 把 Android 手机的声音，实时串流到 Windows 电脑的音箱上。托盘常驻，点一下开关，支持手机端局域网遥控。

基于 [scrcpy](https://github.com/Genymobile/scrcpy) 的音频转发能力（Android 11+），免 root、手机上不装任何 App、延迟低至几十毫秒。

---

## 它能做什么

- 手机放歌 / 看视频 / 打游戏，声音从电脑音箱出来
- 托盘常驻，**单击图标**开关串流，图标颜色就是状态
- 支持 USB（延迟最低）和 WiFi 无线两种连接
- **手机端可主动控制**：手机浏览器或快捷开关磁贴，点一下就切换
- 可设置开机自启、手机一插上就自动开始

## 不能做什么（重要）

Android 系统的「输出设备切换器」由音频 HAL 层定义，**非 root 的第三方应用无法往里面插入设备**。
所以这台电脑不会出现在手机的系统音量面板设备列表里 —— 想在手机上"选设备"，本项目提供的是**局域网遥控**（效果等价，操作在手机侧），而不是系统级设备项。

如果你确实需要系统级设备切换，唯一非 root 路径是蓝牙 A2DP 接收（电脑伪装成蓝牙音箱），代价是 150–300ms 延迟。详见使用说明第五节。

## 快速开始

```bat
python bootstrap.py        :: 自动下载 scrcpy + 建虚拟环境 + 装依赖
start-dock.bat             :: 双击启动托盘工具
```

手动步骤：

1. 手机：设置 → 关于手机 → 连点「版本号」7 次 → 开发者选项 → 打开 **USB 调试**
2. 数据线连电脑（注意：部分充电线不能传数据），手机上点「允许 USB 调试」
3. 双击 `start-dock.bat`，托盘出现喇叭图标 → 单击它 → 开始串流

手机需 Android 11 及以上。

## 状态与操作

| 图标 | 含义 |
|---|---|
| 灰 | 没检测到手机 |
| 蓝 | 手机已连接，待命 |
| 绿 | 串流中 |
| 红 | 串流异常结束 |

**单击** = 开始 / 停止。**右键** = 菜单：播放模式、WiFi 配置、手机遥控、开机自启、自动开始…

## 手机端遥控

托盘菜单开启「手机遥控（局域网）」后，电脑会起一个 HTTP 服务（默认 8765 端口），手机浏览器打开提示的地址即可看到大按钮页；用浏览器的「添加到主屏幕」可变成桌面图标。

首次需要放行防火墙：右键 `allow-firewall.bat` → **以管理员身份运行**。

开放接口（可接 Tasker / MacroDroid / HTTP Shortcuts，做成下拉快捷开关磁贴）：

| 路径 | 作用 |
|---|---|
| `/start` | 开始串流 |
| `/stop` | 停止（声音回到手机） |
| `/toggle` | 切换 |
| `/mode/lowlatency` | 超低延迟模式 |
| `/mode/dup` | 电脑 + 手机同时响 |
| `/mode/video` | 画面 + 声音 |
| `/status` | JSON 状态 |

遥控指令走 WiFi，音频仍可走 USB，延迟不受影响。

## 原理

1. 手机端：`adb push` 一个 733KB 的 `scrcpy-server`，用 `adb shell app_process` 以 shell 权限运行（非 root、不留痕迹）
2. 捕获：`AudioRecord` 使用 `REMOTE_SUBMIX`（远程混音总线）—— 一旦被录制，Android 就把音频路由从扬声器改道到这条总线，**这是手机静音的真正原因**
3. 编码：MediaCodec 编成 Opus（实测 Android 上通常是 `c2.android.opus.encoder`）
4. 通道：`adb reverse localabstract:scrcpy_xxxx tcp:27183`，音频字节流顺着 adb 通道回到电脑的 127.0.0.1:27183
5. 电脑端：FFmpeg(libav) 解码 → SDL3 输出到 Windows 默认音频设备

WiFi 模式没有任何特殊逻辑：只是 adb 的连接层从 USB 换成 TCP 5555，scrcpy 全程只跟 adb 打交道。

## 目录结构

```
PhoneAudioDock.py        托盘工具主程序
bootstrap.py             一键初始化（下载 scrcpy + 建环境）
start-dock.bat           启动托盘
allow-firewall.bat       放行 8765 端口（手机遥控用，需管理员）
audio-usb.bat            命令行版：USB 仅音频
start-phone-audio.bat    命令行版：菜单
audio-wifi.bat           命令行版：WiFi 配对向导
tools/scrcpy/            scrcpy + adb（由 bootstrap.py 下载，不入库）
```

## 已知限制

- 需要 Android 11+；音频转发依赖系统的音频捕获能力
- 手机端遥控需要手机与电脑在同一局域网
- 只支持 Windows

## 许可

MIT

---

## English

PhoneAudioDock streams your Android phone's audio to your Windows PC speakers in real time,
built on [scrcpy](https://github.com/Genymobile/scrcpy)'s audio forwarding (Android 11+).
No root, nothing installed on the phone, tens of milliseconds of latency over USB.

Quick start: `python bootstrap.py`, then double-click `start-dock.bat`.
See `手机声音串流到电脑-使用说明.md` for the full Chinese guide.
