# -*- coding: utf-8 -*-
"""浏览器内音频采集：无虚拟声卡时的回退方案。

通过 Web Audio API 把页面里的 <video>/<audio> 接到 MediaStreamDestination，
再用 MediaRecorder 录成 webm/opus，边录边回传分片落盘，停止后由 ffmpeg
转成 m4a(AAC)。不下载/解析直播流，完全走浏览器正常播放链路。
"""
import base64
import os
import subprocess
import tempfile
import time
import uuid

_START_JS = """() => {
    if (window.__lrCapture) {
        return {mime: window.__lrCapture.rec.mimeType, elements: window.__lrCapture.count};
    }
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx || !window.MediaRecorder) throw new Error('当前浏览器不支持 Web Audio / MediaRecorder');
    const ctx = new AudioCtx();
    const dest = ctx.createMediaStreamDestination();
    const connected = new WeakSet();
    let count = 0;
    const connect = (el) => {
        if (!el || connected.has(el)) return;
        try {
            el.muted = false;
            el.volume = 1;
            const src = ctx.createMediaElementSource(el);
            src.connect(dest);
            src.connect(ctx.destination);
            connected.add(el);
            count++;
        } catch (e) {}
    };
    document.querySelectorAll('video,audio').forEach(connect);
    const observer = new MutationObserver((records) => {
        for (const r of records) {
            for (const n of r.addedNodes) {
                if (n.nodeType !== 1) continue;
                if (n.matches && n.matches('video,audio')) connect(n);
                if (n.querySelectorAll) n.querySelectorAll('video,audio').forEach(connect);
            }
        }
    });
    observer.observe(document.documentElement, {childList: true, subtree: true});
    const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
        .find(m => MediaRecorder.isTypeSupported(m)) || '';
    const rec = new MediaRecorder(dest.stream, mime ? {mimeType: mime} : undefined);
    rec.ondataavailable = (e) => {
        if (!e.data || !e.data.size) return;
        const reader = new FileReader();
        reader.onload = () => {
            const value = String(reader.result || '');
            const comma = value.indexOf(',');
            if (comma >= 0) window.__lrChunk(value.slice(comma + 1));
        };
        reader.readAsDataURL(e.data);
    };
    rec.start(1000);
    if (ctx.state === 'suspended') ctx.resume();
    window.__lrCapture = {ctx, dest, rec, observer, connected, count};
    return {mime: rec.mimeType, elements: count};
}"""

_PAUSE_JS = """() => {
    const c = window.__lrCapture;
    if (!c) return false;
    if (c.rec.state === 'recording') c.rec.pause();
    return c.rec.state;
}"""

_RESUME_JS = """() => {
    const c = window.__lrCapture;
    if (!c) return false;
    if (c.rec.state === 'paused') c.rec.resume();
    if (c.ctx.state === 'suspended') c.ctx.resume();
    return c.rec.state;
}"""

_STOP_JS = """async () => {
    const c = window.__lrCapture;
    if (!c) return {stopped: false};
    if (c.rec.state !== 'inactive') {
        await new Promise((resolve) => {
            c.rec.onstop = resolve;
            c.rec.stop();
        });
    }
    c.observer.disconnect();
    window.__lrCapture = null;
    return {stopped: true};
}"""


class _NoopStdin:
    def write(self, data):
        return len(data)

    def flush(self):
        pass


class BrowserAudioCapture:
    """模拟 subprocess.Popen 的最小接口，便于复用原有录制主循环。"""

    is_browser_capture = True

    def __init__(self, page, ffmpeg_bin, out_path):
        self.page = page
        self.ffmpeg_bin = ffmpeg_bin
        self.out_path = out_path
        self.stdin = _NoopStdin()
        self.pid = -1
        self._binding = "__lrChunk_" + uuid.uuid4().hex
        fd, self.raw_path = tempfile.mkstemp(prefix="live_recorder_", suffix=".webm")
        os.close(fd)
        self._raw = open(self.raw_path, "wb")
        self._done = False
        self._returncode = None
        self._error = ""
        self._chunks = 0
        self._paused = False

    def _on_chunk(self, _source, data_b64):
        if not data_b64:
            return
        try:
            data = base64.b64decode(data_b64)
        except Exception:
            return
        if data:
            self._raw.write(data)
            self._raw.flush()
            self._chunks += 1

    def start(self):
        self.page.expose_binding(self._binding, self._on_chunk)
        self.page.evaluate(
            "(name) => { window.__lrChunk = (data) => window[name](data); }",
            self._binding,
        )
        info = self.page.evaluate(_START_JS)
        if not info or not info.get("mime"):
            raise RuntimeError("浏览器不支持音频录制（需要 Chromium/Edge）")
        return info

    def pause(self):
        try:
            self.page.evaluate(_PAUSE_JS)
            self._paused = True
        except Exception:
            pass

    def resume(self):
        try:
            self.page.evaluate(_RESUME_JS)
            self._paused = False
        except Exception:
            pass

    def poll(self):
        return self._returncode

    def kill(self):
        try:
            self._finalize(allow_error=True)
        except Exception:
            pass

    def communicate(self, timeout=None):
        self._finalize()
        return None, self._error.encode("utf-8", "replace")

    def _finalize(self, allow_error=False):
        if self._done:
            return
        self._done = True
        try:
            self.page.evaluate(_STOP_JS)
        except Exception as e:
            if not allow_error:
                self._error = f"停止浏览器采集失败: {e}"
        time.sleep(0.3)  # 等待最后的 dataavailable 分片写入
        try:
            self._raw.close()
        except Exception:
            pass
        raw_size = os.path.getsize(self.raw_path) if os.path.exists(self.raw_path) else 0
        if raw_size == 0:
            self._returncode = 1
            self._error = self._error or "浏览器未采集到音频数据（页面可能没有播放中的视频/音频）"
            return
        cmd = [
            self.ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error",
            "-i", self.raw_path, "-vn", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", self.out_path,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or "ffmpeg 转码失败").strip()[-300:])
            if not os.path.exists(self.out_path) or os.path.getsize(self.out_path) == 0:
                raise RuntimeError("转码后产物为空")
            check = subprocess.run(
                [self.ffmpeg_bin, "-v", "error", "-i", self.out_path, "-f", "null", "-"],
                capture_output=True, text=True, timeout=60,
            )
            if check.returncode != 0:
                raise RuntimeError("产物无法解码：" + (check.stderr or "").strip()[-200:])
            self._returncode = 0
        except Exception as e:
            self._returncode = 1
            self._error = self._error or str(e)
        finally:
            try:
                os.remove(self.raw_path)
            except OSError:
                pass
