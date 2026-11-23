# -*- coding: utf-8 -*-
"""Windows 系统音录制：基于 VB-Cable 虚拟声卡（dshow 采集）。

注意：本机为 macOS，此实现未经真机验证，设备名按 VB-Audio Virtual Cable
默认「CABLE Output」写入，可按实际设备名调整。
"""
from app.recorder.base import BaseRecorder


class WindowsRecorder(BaseRecorder):
    device_hint = "需安装 VB-Audio Virtual Cable，并在声音设置里把系统输出路由到 CABLE Input"

    #: VB-Cable 采集设备名，可用环境变量 VBCABLE_DEVICE 覆盖
    DEVICE = "audio=CABLE Output (VB-Audio Virtual Cable)"

    def ffmpeg_cmd(self, out_path, ffmpeg_bin):
        return [
            ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "warning",
            "-f", "dshow", "-i", self.DEVICE,
            "-vn", "-c:a", "aac", "-b:a", "192k",
            "-f", "mp4", out_path,
        ]
