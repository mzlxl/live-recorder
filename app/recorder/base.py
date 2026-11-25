# -*- coding: utf-8 -*-
"""系统音录制抽象层：屏蔽 macOS/Windows/Linux 差异。"""
import glob
import os
import platform
import shutil
import sys
from abc import ABC, abstractmethod


def detect_ffmpeg():
    """探测 ffmpeg 可执行文件路径，找不到返回 None。"""
    env_path = os.environ.get("RECORDER_FFMPEG", "").strip()
    candidates = [env_path] if env_path else []
    # 虚拟环境内安装的 ffmpeg（即使 Scripts 未加入 PATH 也能找到）
    exe_dir = os.path.dirname(sys.executable)
    candidates += [
        os.path.join(exe_dir, "ffmpeg.exe"),
        os.path.join(exe_dir, "ffmpeg"),
    ]
    # imageio-ffmpeg 自带的静态二进制
    try:
        import imageio_ffmpeg
        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    # Playwright 自带的 ffmpeg（Windows 为 .exe，macOS/Linux 为无扩展名二进制）
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates += glob.glob(os.path.join(project_dir, ".pw-browsers", "ffmpeg-*", "ffmpeg*"))
    candidates += ["ffmpeg", "ffmpeg.exe"]
    if platform.system() == "Windows":
        candidates += [
            os.path.join(os.environ.get("ProgramFiles", ""), "ffmpeg", "bin", "ffmpeg.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "ffmpeg", "bin", "ffmpeg.exe"),
            os.path.join(os.environ.get("ProgramData", ""), "chocolatey", "bin", "ffmpeg.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links", "ffmpeg.exe"),
            os.path.join(os.environ.get("USERPROFILE", ""), "scoop", "shims", "ffmpeg.exe"),
            os.path.join(project_dir, "ffmpeg.exe"),
        ]
    else:
        candidates += ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]
    for cand in candidates:
        if not cand:
            continue
        found = cand if os.path.isabs(cand) else shutil.which(cand)
        if found and os.path.isfile(found):
            return found
    return None


def current_recorder():
    """按当前系统返回对应录制器实例。"""
    sysname = platform.system()
    if sysname == "Darwin":
        from app.recorder.mac import MacRecorder
        return MacRecorder()
    if sysname == "Windows":
        from app.recorder.windows import WindowsRecorder
        return WindowsRecorder()
    if sysname == "Linux":
        from app.recorder.linux import LinuxRecorder
        return LinuxRecorder()
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
