# -*- coding: utf-8 -*-
"""
bootstrap.py —— 克隆仓库后的一键初始化

做三件事：
  1. 下载 scrcpy 4.1 官方包并校验 SHA256，解压到 tools/scrcpy
  2. 创建 .venv 虚拟环境
  3. 安装托盘工具依赖（pystray + Pillow）

用法：
    python bootstrap.py
"""

import io
import os
import sys
import stat
import shutil
import zipfile
import hashlib
import subprocess
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(BASE, "tools")
SCRCPY_DIR = os.path.join(TOOLS, "scrcpy")
VENV = os.path.join(BASE, ".venv")

VERSION = "4.1"
ZIP_NAME = "scrcpy-win64-v%s.zip" % VERSION
# 官方 Release 里 SHA256sums.txt 中记录的校验值（v4.1）
EXPECT_SHA256 = "5b12172b3264b2889f4583ee64752ce832e29bc8b1089dca81093459697165db"

# 直连优先，失败再走代理镜像（国内网络直连 GitHub 经常不通）
URLS = [
    "https://github.com/Genymobile/scrcpy/releases/download/v%s/%s" % (VERSION, ZIP_NAME),
    "https://gh-proxy.com/https://github.com/Genymobile/scrcpy/releases/download/v%s/%s" % (VERSION, ZIP_NAME),
    "https://ghfast.top/https://github.com/Genymobile/scrcpy/releases/download/v%s/%s" % (VERSION, ZIP_NAME),
]

PYPI_MIRRORS = [
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://registry.npmmirror.com/pypi/simple/",
    "https://pypi.org/simple/",
]


def download(url, timeout=60):
    print("  尝试 %s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": "PhoneAudioDock-bootstrap"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_scrcpy():
    if os.path.exists(os.path.join(SCRCPY_DIR, "scrcpy.exe")):
        print("[跳过] tools/scrcpy 已存在")
        return True

    data = None
    for url in URLS:
        try:
            data = download(url, timeout=180)
            if len(data) > 5 * 1024 * 1024:
                print("  下载完成 %.1f MB" % (len(data) / 1024 / 1024))
                break
            data = None
        except Exception as e:
            print("  失败：%s" % e)
    if not data:
        print("[错误] 所有源都下载失败，请手动下载 scrcpy 并解压到 tools/scrcpy")
        return False

    sha = hashlib.sha256(data).hexdigest()
    print("  SHA256: %s" % sha)
    if sha != EXPECT_SHA256:
        print("[错误] 校验值不匹配！期望 %s" % EXPECT_SHA256)
        print("       为安全起见已中止，请检查网络是否被劫持。")
        return False
    print("  校验通过")

    os.makedirs(TOOLS, exist_ok=True)
    tmp = os.path.join(SCRCPY_DIR + "_tmp")
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(tmp)
    # 官方包解压后带一层 scrcpy-win64-vX.Y 目录，摊平
    inner = [d for d in os.listdir(tmp) if os.path.isdir(os.path.join(tmp, d))]
    src = os.path.join(tmp, inner[0]) if len(inner) == 1 else tmp
    if os.path.exists(SCRCPY_DIR):
        shutil.rmtree(SCRCPY_DIR)
    shutil.move(src, SCRCPY_DIR)
    shutil.rmtree(tmp, ignore_errors=True)
    print("[完成] scrcpy 已就位：%s" % SCRCPY_DIR)
    return True


def setup_venv():
    pyw = os.path.join(VENV, "Scripts", "python.exe")
    if os.path.exists(pyw):
        print("[跳过] .venv 已存在")
        return pyw

    print("创建虚拟环境 .venv ...")
    subprocess.run([sys.executable, "-m", "venv", VENV], check=True)
    py = os.path.join(VENV, "Scripts", "python.exe")
    if not os.path.exists(py):
        print("[错误] 虚拟环境创建失败")
        return None

    for mirror in PYPI_MIRRORS:
        host = mirror.split("//")[-1].split("/")[0]
        print("  用镜像 %s 安装依赖" % host)
        r = subprocess.run(
            [py, "-m", "pip", "install", "-q", "-i", mirror,
             "--trusted-host", host, "pystray", "pillow"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            print("[完成] 依赖安装成功")
            return py
        print("  失败，换下一个")
    print("[错误] 依赖安装失败，请手动执行：.venv\\Scripts\\python.exe -m pip install pystray pillow")
    return None


def main():
    if sys.platform != "win32":
        print("这个工具目前只支持 Windows（托盘与 scrcpy 打包都是 Windows 版）。")
        return 1

    print("=" * 56)
    print("  PhoneAudioDock 初始化")
    print("=" * 56)

    print("\n[1/2] 准备 scrcpy ...")
    if not fetch_scrcpy():
        return 1

    print("\n[2/2] 准备 Python 环境 ...")
    setup_venv()

    print("\n" + "=" * 56)
    print("  初始化完成！")
    print("  双击 start-dock.bat 即可启动托盘工具。")
    print("  详细用法见 手机声音串流到电脑-使用说明.md")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    sys.exit(main())
