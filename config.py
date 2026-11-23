# -*- coding: utf-8 -*-
"""全局配置。"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, "storage", "recordings")
WEB_DIR = os.path.join(BASE_DIR, "web")

HOST = os.environ.get("RECORDER_HOST", "127.0.0.1")
PORT = int(os.environ.get("RECORDER_PORT", "8000"))

# 单次录制最大时长（秒），兜底防止检测失效录不停
MAX_RECORD_DURATION = int(os.environ.get("RECORDER_MAX_DURATION", str(12 * 3600)))
# 录制中轮询下播的间隔（秒）
POLL_INTERVAL = int(os.environ.get("RECORDER_POLL_INTERVAL", "30"))

# 浏览器 UA
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
