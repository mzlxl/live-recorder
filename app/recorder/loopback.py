# -*- coding: utf-8 -*-
"""Windows WASAPI 回环采集：直接录系统输出，无需 VB-Cable 虚拟声卡。

依赖 soundcard，通过「默认扬声器 + include_loopback」拿到系统播放的混合音频，
以 PCM 流喂给 ffmpeg 编码成 m4a(AAC)。
"""
import os
import platform
import subprocess
import threading
import warnings


class _NoopStdin:
    def write(self, data):
        return len(data)

    def flush(self):
        pass


class LoopbackCapture:
    """模拟 subprocess.Popen 的最小接口，复用录制主循环。仅 Windows 可用。"""

    is_loopback = True
    SUPPORTED = platform.system() == "Windows"
    SAMPLE_RATE = 48000
    CHANNELS = 2
    FRAMES = 4800  # 100ms

    def __init__(self, ffmpeg_bin, out_path):
        self.ffmpeg_bin = ffmpeg_bin
        self.out_path = out_path
        self.stdin = _NoopStdin()
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._error = ""
        self._thread = None
        self._proc = None
        self.pid = -1

    def start(self):
        cmd = [
            self.ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "s16le", "-ar", str(self.SAMPLE_RATE), "-ac", str(self.CHANNELS),
            "-i", "pipe:0", "-vn", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", self.out_path,
        ]
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        self.pid = self._proc.pid
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self):
        try:
            import soundcard as sc
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                speaker = sc.default_speaker()
                mic = sc.get_microphone(id=str(speaker.id), include_loopback=True)
                with mic.recorder(samplerate=self.SAMPLE_RATE, channels=self.CHANNELS) as rec:
                    while not self._stop.is_set():
                        data = rec.record(numframes=self.FRAMES)
                        if self._paused.is_set():
                            continue
                        # soundcard 返回 numpy 数组；直接调用其方法，无需显式依赖 numpy
                        pcm = (data.clip(-1, 1) * 32767).astype("<i2").tobytes()
                        self._proc.stdin.write(pcm)
        except Exception as e:
            self._error = f"系统音频回环采集失败: {e}"
        finally:
            try:
                self._proc.stdin.close()
            except Exception:
                pass

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def poll(self):
        if self._proc is None:
            return 0
        return self._proc.poll()

    def kill(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def communicate(self, timeout=None):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        try:
            _, err = self._proc.communicate(timeout=timeout)
            err_text = (err or b"").decode("utf-8", "replace").strip()
            if not err_text:
                err_text = self._error
            return None, err_text.encode("utf-8", "replace")
        except Exception:
            self._proc.kill()
            _, err = self._proc.communicate()
            return None, (err or b"").decode("utf-8", "replace").encode("utf-8", "replace")

    def available(self):
        if not self.SUPPORTED:
            return False
        try:
            import soundcard as sc
            speaker = sc.default_speaker()
            return bool(speaker)
        except Exception:
            return False
