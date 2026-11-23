# -*- coding: utf-8 -*-
"""录制层导出。"""
from app.recorder.base import BaseRecorder, detect_ffmpeg, current_recorder
from app.recorder.mac import MacRecorder
from app.recorder.windows import WindowsRecorder

__all__ = [
    "BaseRecorder",
    "MacRecorder",
    "WindowsRecorder",
    "detect_ffmpeg",
    "current_recorder",
]
