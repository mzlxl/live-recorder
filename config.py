# -*- coding: utf-8 -*-
"""全局配置。"""
import os
import platform
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, "storage", "recordings")
WEB_DIR = os.path.join(BASE_DIR, "web")

# 优先使用项目内的 Chromium，避免依赖全局 Playwright 浏览器缓存
_local_browsers = os.path.join(BASE_DIR, ".pw-browsers")
if os.path.isdir(_local_browsers):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _local_browsers)

HOST = os.environ.get("RECORDER_HOST", "127.0.0.1")
PORT = int(os.environ.get("RECORDER_PORT", "8000"))

# 轻量量化配置用于 Linux 服务器；桌面沿用本地 Whisper。
def whisper_cpp_model():
    return os.environ.get("RECORDER_WHISPER_CPP_MODEL") if platform.system() == "Linux" else None


# 单次录制最大时长（秒），兜底防止检测失效录不停
MAX_RECORD_DURATION = int(os.environ.get("RECORDER_MAX_DURATION", str(12 * 3600)))
# 录制中轮询下播的间隔（秒）
POLL_INTERVAL = int(os.environ.get("RECORDER_POLL_INTERVAL", "30"))

# 浏览器模式：Linux 服务器无显示器默认 headless（省资源），Mac/Windows 有头
HEADLESS = os.environ.get("RECORDER_HEADLESS", "1" if platform.system() == "Linux" else "0") == "1"

def _find_browser():
    """优先系统 Chrome/Edge（含 H.264/AAC 解码器），跨平台探测。"""
    override = os.environ.get("RECORDER_BROWSER", "").strip()
    if override:
        if os.path.isfile(override):
            return override
        return shutil.which(override)  # 也允许填 PATH 中的命令名，如 google-chrome

    system = platform.system()
    if system == "Windows":
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
    elif system == "Darwin":
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            os.path.expanduser("~/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ]
    else:
        paths = []
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                     "microsoft-edge", "microsoft-edge-stable"):
            found = shutil.which(name)
            if found:
                return found

    for path in paths:
        if os.path.isfile(path):
            return path
    return None


# 优先用系统 Chrome/Edge：Playwright 自带 Chromium 缺少 H.264/AAC 解码器，
# 抖音直播等常见直播流无法解码，会表现为「加载中」且录不到声音。
BROWSER_EXECUTABLE = _find_browser()


def browser_available():
    """系统浏览器或已安装的 Playwright Chromium 至少有一个可用。"""
    if BROWSER_EXECUTABLE:
        return True
    roots = []
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        roots.append(os.environ["PLAYWRIGHT_BROWSERS_PATH"])
    if os.path.isdir(_local_browsers):
        roots.append(_local_browsers)
    if platform.system() == "Windows":
        roots.append(os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright"))
    elif platform.system() == "Darwin":
        roots.append(os.path.expanduser("~/Library/Caches/ms-playwright"))
    else:
        roots.append(os.path.expanduser("~/.cache/ms-playwright"))
    for root in roots:
        try:
            if any(name.startswith("chromium-") for name in os.listdir(root)):
                return True
        except OSError:
            pass
    return False


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
