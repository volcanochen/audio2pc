# -*- coding: utf-8 -*-
"""
PhoneAudioDock —— 手机声音串流到电脑音箱的 Windows 托盘常驻工具
单击托盘图标 = 开始/停止串流；右键 = 完整菜单。
底层使用 tools/scrcpy/scrcpy.exe（scrcpy 4.1）。
"""

import os
import sys
import json
import time
import errno
import threading
import socket
import subprocess
import winreg
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pystray
from pystray import Menu, MenuItem as Item
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
SCRCPY = os.path.join(BASE, "tools", "scrcpy", "scrcpy.exe")
ADB = os.path.join(BASE, "tools", "scrcpy", "adb.exe")
CONFIG = os.path.join(BASE, "dock-config.json")
LOGFILE = os.path.join(BASE, "dock.log")

CREATE_NO_WINDOW = 0x08000000
REMOTE_PORT = 8765

# 模式名 -> scrcpy 参数
MODES = {
    "usb": (
        "USB 仅音频（推荐）",
        ["--no-video", "--no-window"],
    ),
    "lowlatency": (
        "超低延迟（打游戏/看视频）",
        ["--no-video", "--no-window", "--audio-buffer=25", "--audio-output-buffer=5"],
    ),
    "video": (
        "画面 + 声音（投屏）",
        ["--max-size=1280", "--max-fps=60"],
    ),
    "dup": (
        "电脑音箱 + 手机扬声器 同时响",
        ["--no-video", "--no-window", "--audio-dup"],
    ),
}

STATE_COLOR = {
    "no_device": (120, 124, 132),
    "idle": (45, 125, 210),
    "streaming": (40, 180, 90),
    "error": (210, 70, 60),
}
STATE_TEXT = {
    "no_device": "未检测到手机",
    "idle": "手机已连接 · 点击开始串流",
    "streaming": "串流中 · 声音正在从电脑音箱输出",
    "error": "串流异常结束",
}


def log(msg):
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def make_icon(state):
    """绘制喇叭图标，底色随状态变化"""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = STATE_COLOR.get(state, STATE_COLOR["no_device"])
    d.ellipse((2, 2, 61, 61), fill=color + (255,), outline=(255, 255, 255, 200), width=2)
    w = (255, 255, 255, 255)
    # 喇叭主体
    d.polygon([(15, 26), (23, 26), (33, 15), (33, 49), (23, 38), (15, 38)], fill=w)
    # 声波
    d.arc((34, 21, 49, 43), start=-55, end=55, fill=w, width=3)
    d.arc((42, 13, 60, 51), start=-55, end=55, fill=w, width=3)
    return img


PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>手机声音遥控器</title></head><body>
<h1>手机声音遥控器</h1>
<p class="sub">目标电脑：__NAME__</p>
<div id="st">读取状态…</div>
<button class="g" onclick="go('/start')">播放到电脑音箱</button>
<button onclick="go('/stop')">回到手机扬声器</button>
<button class="gray" onclick="go('/mode/dup')">两边同时响</button>
<button class="gray" onclick="go('/mode/lowlatency')">切到超低延迟</button>
<button class="gray" onclick="go('/mode/video')">画面 + 声音</button>
<p class="tip">提示：用浏览器的「添加到主屏幕」，之后点桌面图标就能直接用。</p>
<script>
function go(u){fetch(u).then(function(){upd();}).catch(function(){upd();});}
function upd(){fetch('/status').then(function(r){return r.json();}).then(function(j){
document.getElementById('st').textContent=(j.streaming?'串流中':'待命')+' · '+j.mode;
}).catch(function(){document.getElementById('st').textContent='连不上电脑';});}
upd();setInterval(upd,3000);
</script></body></html>"""

PAGE = PAGE.replace("<body>", "<body>").replace(
    "<h1>", "<style>"
    "body{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:18px;background:#f4f4f6;color:#1c1c1e}"
    "h1{font-size:19px;font-weight:600;margin:0 0 4px}"
    ".sub{color:#6e6e73;font-size:13px;margin:0 0 14px}"
    "#st{padding:12px 14px;border-radius:10px;background:#fff;font-size:14px;margin-bottom:16px}"
    "button{display:block;width:100%;padding:17px;margin-bottom:11px;font-size:16px;border:0;"
    "border-radius:12px;background:#2d7dd2;color:#fff;font-weight:500}"
    "button.g{background:#28b45a}button.gray{background:#8a8a8e}"
    "button:active{opacity:.75}"
    ".tip{color:#8a8a8e;font-size:12px;margin-top:16px;line-height:1.6}"
    "</style><h1>")


class Dock:
    def __init__(self):
        self.state = "no_device"
        self.mode = "usb"
        self.proc = None
        self.wifi_ip = None
        self.use_wifi = False
        self.auto_start = False
        self.remote_on = False
        self.remote_server = None
        self._last_has_dev = False
        self.icon = None
        self.load_config()

    # ---------- 配置 ----------
    def load_config(self):
        try:
            with open(CONFIG, encoding="utf-8") as f:
                cfg = json.load(f)
            self.wifi_ip = cfg.get("wifi_ip")
            self.mode = cfg.get("mode", "usb")
            self.use_wifi = bool(cfg.get("use_wifi", False))
            self.auto_start = bool(cfg.get("auto_start", False))
            self.remote_on = bool(cfg.get("remote_on", False))
        except Exception:
            pass

    def save_config(self):
        try:
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(
                    {"wifi_ip": self.wifi_ip, "mode": self.mode,
                 "use_wifi": self.use_wifi, "auto_start": self.auto_start,
                 "remote_on": self.remote_on},
                    f, ensure_ascii=False, indent=2,
                )
        except Exception:
            pass

    # ---------- adb ----------
    def adb(self, *args, timeout=15):
        try:
            r = subprocess.run(
                [ADB] + list(args),
                capture_output=True, text=True, timeout=timeout,
                creationflags=CREATE_NO_WINDOW,
            )
            return (r.stdout or "") + (r.stderr or "")
        except Exception as e:
            log("adb %s 失败: %s" % (args, e))
            return ""

    def devices(self):
        out = self.adb("devices")
        return [ln.split("\t")[0] for ln in out.splitlines()
                if ln.strip().endswith("\tdevice")]

    def phone_ip(self):
        out = self.adb("shell", "ip", "-f", "inet", "addr", "show", "wlan0")
        for ln in out.splitlines():
            ln = ln.strip()
            if ln.startswith("inet "):
                return ln.split()[1].split("/")[0]
        return None

    # ---------- 串流控制 ----------
    def build_args(self):
        args = list(MODES[self.mode][1])
        if self.use_wifi and self.wifi_ip:
            args.append("--tcpip=%s:5555" % self.wifi_ip)
        return args

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        if not self.devices() and not (self.use_wifi and self.wifi_ip):
            self.notify("没检测到手机", "请检查数据线、USB 调试是否开启")
            return
        if self.use_wifi and self.wifi_ip and not self.devices():
            self.adb("connect", "%s:5555" % self.wifi_ip)
            time.sleep(1.5)

        args = self.build_args()
        log("启动: scrcpy %s" % " ".join(args))
        try:
            self.proc = subprocess.Popen(
                [SCRCPY] + args,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as e:
            log("启动失败: %s" % e)
            self.notify("启动失败", str(e))
            return
        self.set_state("streaming")
        self.notify("已开始串流", "手机声音正在从电脑音箱输出")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            log("停止串流")
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        self.proc = None
        self.set_state("idle" if self.devices() else "no_device")

    def toggle(self):
        if self.proc and self.proc.poll() is None:
            self.stop()
        else:
            self.start()

    # ---------- WiFi ----------
    def wifi_setup(self):
        self.notify("WiFi 配置", "请先用数据线连接手机")
        if not self.devices():
            # 尝试直连已知 IP
            if self.wifi_ip:
                self.adb("connect", "%s:5555" % self.wifi_ip)
                time.sleep(1.5)
                if self.devices():
                    self.use_wifi = True
                    self.save_config()
                    self.notify("已连上", "WiFi 设备 %s" % self.wifi_ip)
                    return
            self.notify("WiFi 配置失败", "需要先用数据线连一次手机")
            return
        self.adb("tcpip", "5555")
        time.sleep(2)
        ip = self.phone_ip()
        if not ip:
            self.notify("取不到手机 IP", "请确认手机连着 WiFi")
            return
        self.adb("connect", "%s:5555" % ip)
        time.sleep(1.5)
        self.wifi_ip = ip
        self.use_wifi = True
        self.save_config()
        self.notify("WiFi 已就绪", "手机 IP %s —— 现在可以拔掉数据线了" % ip)

    # ---------- 开机自启 ----------
    @staticmethod
    def autostart_cmd():
        pyw = os.path.join(BASE, ".venv", "Scripts", "pythonw.exe")
        if not os.path.exists(pyw):
            pyw = sys.executable.replace("python.exe", "pythonw.exe")
        return '"%s" "%s"' % (pyw, os.path.join(BASE, "PhoneAudioDock.py"))

    @staticmethod
    def autostart_enabled():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                val, _ = winreg.QueryValueEx(k, "PhoneAudioDock")
                return bool(val)
        except Exception:
            return False

    def toggle_autostart(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE) as k:
                if self.autostart_enabled():
                    winreg.DeleteValue(k, "PhoneAudioDock")
                    self.notify("已关闭开机自启", "")
                else:
                    winreg.SetValueEx(k, "PhoneAudioDock", 0, winreg.REG_SZ,
                                      self.autostart_cmd())
                    self.notify("已开启开机自启", "下次开机托盘会自动出现")
        except Exception as e:
            log("自启设置失败: %s" % e)
            self.notify("设置失败", str(e))

    # ---------- 状态 ----------
    def set_state(self, s):
        if s != self.state:
            self.state = s
            log("状态 -> %s" % s)
        if self.icon:
            self.icon.icon = make_icon(self.state)
            self.icon.title = "手机声音 → 电脑音箱\n" + STATE_TEXT.get(self.state, "")
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def notify(self, title, msg):
        log("通知: %s / %s" % (title, msg))
        if self.icon:
            try:
                self.icon.notify(msg or title, title)
            except Exception:
                pass

    # ---------- 轮询 ----------
    def poll(self):
        while True:
            try:
                has_dev = bool(self.devices())
                running = self.proc is not None and self.proc.poll() is None
                # 手机刚插上 -> 自动开始串流（可选）
                if has_dev and not self._last_has_dev and self.auto_start and not running \
                        and self.state != "error":
                    log("检测到手机插入，自动开始串流")
                    self.start()
                    running = self.proc is not None and self.proc.poll() is None
                self._last_has_dev = has_dev
                if running:
                    if not has_dev:
                        # 手机掉了：scrcpy 自己会退出，这里收尾
                        self.proc = None
                        self.set_state("no_device")
                        self.notify("手机已断开", "串流结束")
                    else:
                        self.set_state("streaming")
                else:
                    if self.proc is not None:
                        # 进程意外结束
                        code = self.proc.poll()
                        self.proc = None
                        self.set_state("error")
                        self.notify("串流已停止", "退出码 %s" % code)
                    elif self.state != "no_device" or has_dev:
                        self.set_state("idle" if has_dev else "no_device")
            except Exception as e:
                log("轮询异常: %s" % e)
            finally:
                time.sleep(3)

    # ---------- 手机遥控（局域网） ----------
    @staticmethod
    def lan_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            s.close()

    def remote_url(self):
        return "http://%s:%d" % (self.lan_ip(), REMOTE_PORT)

    def start_remote(self):
        if self.remote_server:
            return True
        dock = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = urlparse(self.path).path
                try:
                    if path in ("/", "/index.html"):
                        body = PAGE.replace("__NAME__", socket.gethostname()).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                    elif path == "/start":
                        dock.start()
                        self.reply_text("started")
                    elif path == "/stop":
                        dock.stop()
                        self.reply_text("stopped")
                    elif path == "/toggle":
                        dock.toggle()
                        self.reply_text("toggled")
                    elif path.startswith("/mode/"):
                        key = path.split("/", 2)[2]
                        if key in MODES:
                            dock.set_mode(key)
                            self.reply_text("mode=" + key)
                        else:
                            self.reply_text("unknown mode", 400)
                    elif path == "/status":
                        import json as _json
                        data = _json.dumps({
                            "state": STATE_TEXT.get(dock.state, dock.state),
                            "mode": MODES[dock.mode][0],
                            "streaming": dock.proc is not None and dock.proc.poll() is None,
                            "device": dock.devices()[:1],
                        }, ensure_ascii=False).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                    else:
                        self.reply_text("not found", 404)
                except Exception as e:
                    log("遥控请求异常 %s: %s" % (path, e))
                    try:
                        self.reply_text("error", 500)
                    except Exception:
                        pass

            def reply_text(self, text, code=200):
                body = text.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                log("遥控: " + (fmt % args))

        try:
            srv = ThreadingHTTPServer(("0.0.0.0", REMOTE_PORT), Handler)
        except OSError as e:
            log("遥控服务启动失败: %s" % e)
            self.notify("遥控服务启动失败", "端口 %d 可能被占用" % REMOTE_PORT)
            return False
        self.remote_server = srv
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        log("遥控服务已启动: %s" % self.remote_url())
        return True

    def stop_remote(self):
        if self.remote_server:
            try:
                self.remote_server.shutdown()
                self.remote_server.server_close()
            except Exception:
                pass
            self.remote_server = None
            log("遥控服务已停止")

    def toggle_remote(self):
        if self.remote_on:
            self.stop_remote()
            self.remote_on = False
            self.save_config()
            self.notify("已关闭手机遥控", "")
        else:
            if self.start_remote():
                self.remote_on = True
                self.save_config()
                self.notify("手机遥控已开启", self.remote_url())

    def show_remote_url(self):
        url = self.remote_url()
        log("遥控地址: %s" % url)
        self.notify("用手机浏览器打开", url)

    # ---------- 菜单 ----------
    def menu(self):
        def label_toggle(_):
            return "■ 停止串流" if (self.proc and self.proc.poll() is None) else "▶ 开始串流"

        def mode_item(key):
            return Item(
                MODES[key][0],
                lambda _k=key: self.set_mode(_k),
                checked=lambda _i, _k=key: self.mode == _k,
                radio=True,
            )

        def wifi_label(_):
            if self.use_wifi and self.wifi_ip:
                return "WiFi 无线 · 已连 %s" % self.wifi_ip
            return "WiFi 无线 · 点此配置（需先插数据线）"

        def usb_label(_):
            return "切回 USB 有线模式" if self.use_wifi else "USB 有线模式（当前）"

        return Menu(
            Item(label_toggle, lambda: self.toggle(), default=True),
            Menu.SEPARATOR,
            Item("播放模式", Menu(
                mode_item("usb"),
                mode_item("lowlatency"),
                mode_item("video"),
                mode_item("dup"),
            )),
            Menu.SEPARATOR,
            Item(wifi_label, lambda: self.wifi_setup()),
            Item(usb_label, lambda: self.use_usb(), enabled=lambda _: self.use_wifi),
            Menu.SEPARATOR,
            Item("手机一连上就自动串流", lambda: self.toggle_auto(),
                 checked=lambda _: self.auto_start),
            Item("手机遥控（局域网）", lambda: self.toggle_remote(),
                 checked=lambda _: self.remote_on),
            Item("查看遥控地址", lambda: self.show_remote_url(),
                 enabled=lambda _: self.remote_on),
            Item("重新检测手机", lambda: self.redetect()),
            Item("打开 Windows 声音设置", lambda: open_sound_settings()),
            Item("开机自动启动", lambda: self.toggle_autostart(),
                 checked=lambda _: self.autostart_enabled()),
            Item("打开使用说明", lambda: open_guide()),
            Menu.SEPARATOR,
            Item("退出", lambda: self.quit()),
        )

    def set_mode(self, key):
        self.mode = key
        self.save_config()
        was_running = self.proc and self.proc.poll() is None
        if was_running:
            self.stop()
            time.sleep(0.6)
            self.start()
        else:
            self.set_state(self.state)
        self.notify("已切换模式", MODES[key][0])

    def toggle_auto(self):
        self.auto_start = not self.auto_start
        self.save_config()
        self.notify("已" + ("开启" if self.auto_start else "关闭"),
                    "检测到手机插入时自动开始串流" if self.auto_start else "")

    def use_usb(self):
        self.use_wifi = False
        self.save_config()
        self.notify("已切回 USB", "请用数据线连接手机")

    def redetect(self):
        self.adb("kill-server")
        self.adb("start-server")
        time.sleep(2)
        n = len(self.devices())
        self.notify("已重新检测", "发现 %d 台设备" % n)
        self.set_state("idle" if n else "no_device")

    def quit(self):
        try:
            self.stop()
        except Exception:
            pass
        if self.icon:
            self.icon.stop()

    # ---------- 启动 ----------
    def run(self):
        self.icon = pystray.Icon(
            "PhoneAudioDock",
            make_icon(self.state),
            "手机声音 → 电脑音箱",
            self.menu(),
        )
        t = threading.Thread(target=self.poll, daemon=True)
        t.start()
        if self.remote_on:
            self.start_remote()
        log("Dock 启动")
        self.icon.run()


def open_sound_settings():
    try:
        os.startfile("ms-settings:sound")
    except Exception:
        subprocess.Popen(["control.exe", "mmsys.cpl"], creationflags=CREATE_NO_WINDOW)


def open_guide():
    p = os.path.join(BASE, "手机声音串流到电脑-使用说明.md")
    if os.path.exists(p):
        try:
            os.startfile(p)
        except Exception:
            pass


_lock_socket = None


def already_running(port=47621):
    """单实例保护：占住一个本机端口，占不到说明已经有一个 Dock 在跑"""
    global _lock_socket
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
    except OSError:
        return True
    s.listen(1)
    _lock_socket = s
    return False


if __name__ == "__main__":
    if not os.path.exists(SCRCPY):
        print("找不到 %s" % SCRCPY)
        sys.exit(1)
    if already_running():
        print("PhoneAudioDock 已经在运行了（托盘里找喇叭图标）")
        sys.exit(0)
    Dock().run()
