# -*- coding: utf-8 -*-
"""Windows 系统音录制：基于 VB-Cable 虚拟声卡（dshow 采集）。

设备名可通过环境变量 VBCABLE_DEVICE 覆盖；未配置时优先从 ffmpeg 的
dshow 设备列表里自动匹配 VB-Cable，避免硬编码名称与实际设备不符。
"""
import os
import re
import subprocess
import time

from app.recorder.base import BaseRecorder, detect_ffmpeg

_device_cache = {"at": 0.0, "devices": []}


class WindowsRecorder(BaseRecorder):
    device_hint = "需安装 VB-Audio Virtual Cable，把系统输出路由到 CABLE Input；设备名不匹配时设置 VBCABLE_DEVICE"

    DEFAULT_DEVICE = "CABLE Output (VB-Audio Virtual Cable)"

    @staticmethod
    def _list_audio_devices(ffmpeg_bin=None):
        ffmpeg_bin = ffmpeg_bin or detect_ffmpeg()
        if not ffmpeg_bin:
            return []
        if time.time() - _device_cache["at"] < 30 and _device_cache["devices"]:
            return list(_device_cache["devices"])
        try:
            r = subprocess.run(
                [ffmpeg_bin, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", timeout=10,
            )
            devices = re.findall(r'"([^"]+)"\s*\(audio\)', r.stdout or "")
        except Exception:
            devices = []
        _device_cache.update(at=time.time(), devices=devices)
        return list(devices)

    def device_name(self, ffmpeg_bin=None):
        override = os.environ.get("VBCABLE_DEVICE", "").strip()
        if override:
            return override
        for name in self._list_audio_devices(ffmpeg_bin):
            low = name.lower()
            if "cable output" in low or "vb-audio" in low:
                return name
        return self.DEFAULT_DEVICE

    def ffmpeg_cmd(self, out_path, ffmpeg_bin):
        return [
            ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "warning",
            "-f", "dshow", "-i", f"audio={self.device_name(ffmpeg_bin)}",
            "-vn", "-c:a", "aac", "-b:a", "192k",
            "-f", "mp4", out_path,
        ]

    def device_ready(self):
        ffmpeg_bin = detect_ffmpeg()
        if not ffmpeg_bin:
            return False
        devices = self._list_audio_devices(ffmpeg_bin)
        if not devices:
            return False
        configured = self.device_name(ffmpeg_bin).lower()
        return any(configured == name.lower() for name in devices)
