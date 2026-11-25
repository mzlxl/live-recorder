# -*- coding: utf-8 -*-
"""录制链路自动化验证：浏览器采集 → m4a 转码 → 解码/音量/实际播放检查。

用法：
    python verify_recording.py            # 端到端自检（生成测试音频并录制）
    python verify_recording.py --file X   # 只验证已有产物能否正常打开播放
"""
import argparse
import functools
import http.server
import math
import os
import platform
import re
import shutil
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from urllib.parse import quote

import config
from app.recorder.base import detect_ffmpeg
from app.recorder.browser import BrowserAudioCapture
from app.recorder.loopback import LoopbackCapture
from playwright.sync_api import sync_playwright


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def _serve(directory):
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def _make_tone(path, seconds=8, freq=440):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        frames = bytearray()
        for i in range(44100 * seconds):
            value = int(8000 * math.sin(2 * math.pi * freq * i / 44100))
            frames += struct.pack("<h", value)
        w.writeframes(bytes(frames))


def probe_audio(ffmpeg, path, min_seconds=1.0):
    """用 ffmpeg 解码整段音频，并检查时长/编码/非静音。"""
    info = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)],
                          capture_output=True, text=True)
    text = info.stderr or ""
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", text)
    if not m:
        raise AssertionError("无法读取产物时长（文件可能损坏）")
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    if duration < min_seconds:
        raise AssertionError(f"产物时长过短: {duration:.2f}s")
    if "Audio: aac" not in text:
        raise AssertionError("产物中没有 AAC 音轨")
    decode = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"],
                            capture_output=True, text=True)
    if decode.returncode != 0:
        raise AssertionError("产物无法完整解码：" + (decode.stderr or "").strip()[-200:])
    volume = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-af", "volumedetect",
                             "-f", "null", "-"], capture_output=True, text=True)
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", volume.stderr or "")
    if not mean or float(mean.group(1)) < -60:
        raise AssertionError("产物为静音，录制链路没有采到声音")
    return {"duration": duration, "mean_volume": float(mean.group(1))}


def _system_browser():
    """Playwright 自带 Chromium 不含 AAC 解码器，优先用系统 Chrome/Edge 验证播放。"""
    if config.BROWSER_EXECUTABLE:
        return config.BROWSER_EXECUTABLE
    system = platform.system()
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    elif system == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
    else:
        return shutil.which("google-chrome") or shutil.which("chromium") \
            or shutil.which("microsoft-edge")
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def check_playback(path):
    """用系统浏览器真正打开产物并播放，确认进度前进。"""
    path = Path(path).resolve()
    server, port = _serve(path.parent)
    media_url = f"http://127.0.0.1:{port}/{quote(path.name)}"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=_system_browser(),
            args=["--autoplay-policy=no-user-gesture-required"],
        )
        try:
            page = browser.new_page()
            page.set_content(
                f"<audio id='a' src='{media_url}' controls autoplay></audio>",
                wait_until="domcontentloaded", timeout=30000,
            )
            page.wait_for_function(
                "() => { const a = document.querySelector('audio'); return a && a.readyState >= 1; }",
                timeout=15000,
            )
            result = page.evaluate(
                """async () => {
                    const a = document.querySelector('audio,video');
                    if (!a) return {ok: false, reason: '页面中没有播放器'};
                    if (!isFinite(a.duration) || a.duration <= 0) {
                        return {ok: false, reason: '播放器无法读取时长'};
                    }
                    await a.play();
                    await new Promise(r => setTimeout(r, 900));
                    return {ok: a.currentTime > 0.1, duration: a.duration,
                            currentTime: a.currentTime};
                }"""
            )
        finally:
            browser.close()
    server.shutdown()
    server.server_close()
    if not result.get("ok"):
        raise AssertionError("播放器无法播放：" + str(result))
    return result


def verify_file(ffmpeg, path, min_seconds=1.0):
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise AssertionError(f"产物不存在或为空: {path}")
    info = probe_audio(ffmpeg, path, min_seconds)
    play = check_playback(path)
    return info, play


def self_test(ffmpeg, seconds=5, mode="browser"):
    if mode == "loopback" and platform.system() != "Windows":
        raise AssertionError("WASAPI 回环自检仅支持 Windows")
    os.makedirs(config.STORAGE_DIR, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="lr_verify_", dir=str(Path(config.STORAGE_DIR))))
    server = None
    try:
        wav_path = work / "tone.wav"
        out_path = work / "result.m4a"
        html_path = work / "test.html"
        _make_tone(wav_path, seconds=seconds + 3)
        html_path.write_text(
            "<!doctype html><meta charset='utf-8'>"
            "<audio id='a' src='/tone.wav' autoplay loop></audio>", encoding="utf-8"
        )
        server, port = _serve(work)
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--autoplay-policy=no-user-gesture-required"],
            )
            try:
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{port}/test.html", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => { const a = document.querySelector('audio'); return a && !a.paused; }",
                    timeout=15000,
                )
                if mode == "loopback":
                    capture = LoopbackCapture(ffmpeg, str(out_path))
                    capture.start()
                    if os.name == "nt":
                        import winsound
                        winsound.PlaySound(str(wav_path), winsound.SND_ASYNC | winsound.SND_FILENAME)
                    print("[采集] WASAPI 系统输出回环已启动")
                else:
                    capture = BrowserAudioCapture(page, ffmpeg, str(out_path))
                    started = capture.start()
                    print(f"[采集] 启动成功，格式 {started.get('mime')}，音源 {started.get('elements')} 个")
                time.sleep(seconds)
                _, err = capture.communicate()
                if err:
                    raise AssertionError(err.decode("utf-8", "replace"))
            finally:
                browser.close()
                if mode == "loopback" and os.name == "nt":
                    import winsound
                    winsound.PlaySound(None, winsound.SND_PURGE)
        info, play = verify_file(ffmpeg, out_path, min_seconds=seconds * 0.6)
        print(f"[产物] {out_path.name} {out_path.stat().st_size} 字节，"
              f"时长 {info['duration']:.2f}s，平均音量 {info['mean_volume']:.1f}dB")
        print(f"[播放] Chromium 已打开并播放，进度 {play['currentTime']:.2f}s / {play['duration']:.2f}s")
        return out_path
    finally:
        if server:
            server.shutdown()
            server.server_close()
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="只验证指定产物文件")
    parser.add_argument("--seconds", type=int, default=5, help="自检录制秒数")
    args = parser.parse_args()
    ffmpeg = detect_ffmpeg()
    if not ffmpeg:
        print("FAIL: 未找到 ffmpeg")
        return 1
    print(f"[ffmpeg] {ffmpeg}")
    try:
        if args.file:
            info, play = verify_file(ffmpeg, args.file)
            print(f"[产物] {args.file} 时长 {info['duration']:.2f}s，音量 {info['mean_volume']:.1f}dB")
            print(f"[播放] Chromium 进度 {play['currentTime']:.2f}s / {play['duration']:.2f}s")
        else:
            modes = ["browser"]
            if platform.system() == "Windows" and LoopbackCapture("", "").available():
                modes.append("loopback")
            for mode in modes:
                print(f"--- {mode} 模式自检 ---")
                self_test(ffmpeg, args.seconds, mode=mode)
        print("=== 验证通过：录制文件可正常打开并播放 ===")
        return 0
    except Exception as e:
        print(f"=== 验证失败：{e} ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())
