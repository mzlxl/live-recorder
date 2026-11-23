# -*- coding: utf-8 -*-
"""全局配置。"""
import os
import platform

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, "storage", "recordings")
WEB_DIR = os.path.join(BASE_DIR, "web")

HOST = os.environ.get("RECORDER_HOST", "127.0.0.1")
PORT = int(os.environ.get("RECORDER_PORT", "8000"))

# 单次录制最大时长（秒），兜底防止检测失效录不停
MAX_RECORD_DURATION = int(os.environ.get("RECORDER_MAX_DURATION", str(12 * 3600)))
# 录制中轮询下播的间隔（秒）
POLL_INTERVAL = int(os.environ.get("RECORDER_POLL_INTERVAL", "30"))

# 浏览器模式：Linux 服务器无显示器默认 headless（省资源），Mac/Windows 有头
HEADLESS = os.environ.get("RECORDER_HEADLESS", "1" if platform.system() == "Linux" else "0") == "1"

# 浏览器启动参数：Linux 服务器精简参数，省内存、适配容器环境
BROWSER_ARGS = ["--autoplay-policy=no-user-gesture-required"]
if platform.system() == "Linux":
    BROWSER_ARGS += [
        "--disable-gpu",            # 无 GPU，禁用省资源
        "--no-sandbox",             # 容器/非特权环境
        "--disable-dev-shm-usage",  # /dev/shm 过小时用 /tmp 避免崩溃
        "--disable-extensions",
    ]

# 浏览器 UA
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
