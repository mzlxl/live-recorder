# -*- coding: utf-8 -*-
"""Linux 系统音录制：基于 PulseAudio/PipeWire 虚拟 sink（monitor 源）。

轻量方案：创建 null-sink 作为虚拟声卡，浏览器音频路由到它，ffmpeg 录其 monitor。
"""
import os

from app.recorder.base import BaseRecorder


class LinuxRecorder(BaseRecorder):
    device_hint = (
        "需安装 PulseAudio/PipeWire，创建虚拟 sink 后录制其 monitor：\n"
        "  pactl load-module module-null-sink sink_name=recording\n"
        "  并设置环境变量 PULSE_SOURCE=recording.monitor"
    )

    @property
    def DEVICE(self):
        # monitor 源名，通过环境变量覆盖（默认 recording.monitor）
        return os.environ.get("PULSE_SOURCE", "recording.monitor")

    def ffmpeg_cmd(self, out_path, ffmpeg_bin):
        return [
            ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "warning",
            "-f", "pulse", "-i", self.DEVICE,
            "-vn", "-c:a", "aac", "-b:a", "192k",
            "-f", "mp4", out_path,
        ]
