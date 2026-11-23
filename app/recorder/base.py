# -*- coding: utf-8 -*-
"""系统音录制抽象层：屏蔽操作系统差异（Mac/Windows）。"""
import platform
import shutil
from abc import ABC, abstractmethod


def detect_ffmpeg():
    """探测 ffmpeg 可执行文件路径。"""
    p = shutil.which("ffmpeg")
    if p:
        return p
    # macOS 常见路径（brew）
    for cand in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if shutil.which(cand):
            return cand
    return "ffmpeg"  # 兜底，交给 shell 报错


def current_recorder():
    """按当前系统返回对应录制器实例。"""
    sysname = platform.system()
    if sysname == "Darwin":
        from app.recorder.mac import MacRecorder
        return MacRecorder()
    if sysname == "Windows":
        from app.recorder.windows import WindowsRecorder
        return WindowsRecorder()
    raise RuntimeError(f"暂不支持的操作系统: {sysname}")


class BaseRecorder(ABC):
    #: 供前端展示/校验的说明
    device_hint = ""

    @abstractmethod
    def ffmpeg_cmd(self, out_path: str, ffmpeg_bin: str):
        """返回录制系统音的命令列表。"""

    def device_ready(self) -> bool:
        """检查系统音录制设备是否就绪（可被前端调用提示用户）。"""
        return True
