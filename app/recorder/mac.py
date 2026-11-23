# -*- coding: utf-8 -*-
"""macOS 系统音录制：基于 BlackHole 虚拟声卡。"""
import os

from app.recorder.base import BaseRecorder


class MacRecorder(BaseRecorder):
    device_hint = "需安装 BlackHole 2ch 虚拟声卡（brew install blackhole-2ch），并配置多输出设备"

    @property
    def DEVICE(self):
        # 环境变量 BLACKHOLE_DEVICE 可覆盖（测试时可用麦克风等替代）
        return os.environ.get("BLACKHOLE_DEVICE", "none:BlackHole 2ch")

    def ffmpeg_cmd(self, out_path, ffmpeg_bin):
        return [
            ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "warning",
            "-f", "avfoundation", "-i", self.DEVICE,
            "-vn", "-c:a", "aac", "-b:a", "192k",
            "-f", "mp4", out_path,
        ]

    def device_ready(self):
        import subprocess
        try:
            r = subprocess.run(
                [ffmpeg_bin_path(), "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                capture_output=True, text=True, timeout=15,
            )
            return "BlackHole" in (r.stderr or "")
        except Exception:
            return False


def ffmpeg_bin_path():
    from app.recorder.base import detect_ffmpeg
    return detect_ffmpeg()
