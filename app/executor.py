# -*- coding: utf-8 -*-
"""录制执行器：核心流程「主播主页 → 检测开播 → 进直播间 → 系统音录制 → 下播自停」。

系统音是全局共享资源，同一时刻只允许一个任务在录，加锁保证不串音。
支持：暂停(暂停 ffmpeg 录音)/恢复/停止，以及按任务时间窗口扫描与录制。
"""
import ctypes
import os
import platform
import re
import signal
import subprocess
import threading
import time
from contextlib import nullcontext
from datetime import datetime

# wintypes 只存在于 Windows，非 Windows 上不能导入，否则整个应用无法启动
_IS_WINDOWS = platform.system() == "Windows"
if _IS_WINDOWS:
    from ctypes import wintypes
else:
    wintypes = None

from playwright.sync_api import sync_playwright

import config
from app import db
from app.stealth import apply_stealth
from app.platforms import get_platform
from app.recorder import current_recorder, detect_ffmpeg
from app.recorder.browser import BrowserAudioCapture
from app.recorder.loopback import LoopbackCapture

# 全局锁：系统音同一时刻只能录一路
_lock = threading.Lock()
# 轻量模式下优先录制，浏览器和模型互斥。
low_memory_slot = threading.Lock()
recording_requested = threading.Event()
_running = set()
last_result = {}
# task_id -> {"proc": ffmpeg, "paused": bool, "stop": bool, "rec_id": int, "out_path": str}
_run_state = {}
_suspended_pids = set()


if _IS_WINDOWS:
    class _ThreadEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG), ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]


def _win_thread_ids(pid):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32)]
    kernel32.Thread32First.restype = wintypes.BOOL
    kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32)]
    kernel32.Thread32Next.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x4, 0)  # TH32CS_SNAPTHREAD
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return []
    entry = _ThreadEntry32()
    entry.dwSize = ctypes.sizeof(_ThreadEntry32)
    tids = []
    try:
        ok = kernel32.Thread32First(snapshot, ctypes.byref(entry))
        while ok:
            if entry.th32OwnerProcessID == pid:
                tids.append(entry.th32ThreadID)
            ok = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return tids


def _win_suspend(pid, suspend):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.SuspendThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    invalid = ctypes.c_void_p(-1).value
    for tid in _win_thread_ids(pid):
        handle = kernel32.OpenThread(0x0002, False, tid)  # THREAD_SUSPEND_RESUME
        if not handle or handle == invalid:
            continue
        try:
            if suspend:
                kernel32.SuspendThread(handle)
            else:
                kernel32.ResumeThread(handle)
        finally:
            kernel32.CloseHandle(handle)


def _suspend_process(proc):
    if proc.poll() is not None:
        return
    if getattr(proc, "is_browser_capture", False) or getattr(proc, "is_loopback", False):
        proc.pause()
        return
    if _IS_WINDOWS:
        if proc.pid not in _suspended_pids:
            _win_suspend(proc.pid, True)
            _suspended_pids.add(proc.pid)
    elif hasattr(signal, "SIGSTOP"):
        proc.send_signal(signal.SIGSTOP)


def _resume_process(proc):
    if getattr(proc, "is_browser_capture", False) or getattr(proc, "is_loopback", False):
        proc.resume()
        return
    if _IS_WINDOWS:
        if proc.pid in _suspended_pids:
            _win_suspend(proc.pid, False)
            _suspended_pids.discard(proc.pid)
    elif hasattr(signal, "SIGCONT"):
        proc.send_signal(signal.SIGCONT)


def _is_custom_capture(proc):
    return getattr(proc, "is_browser_capture", False) or getattr(proc, "is_loopback", False)


def is_running(task_id):
    return task_id in _running


def is_capturing(task_id):
    return task_id in _run_state


def is_paused(task_id):
    s = _run_state.get(task_id)
    return bool(s and s["paused"])


def pause_task(task_id):
    s = _run_state.get(task_id)
    if not s or s["paused"]:
        return False
    if not _is_custom_capture(s["proc"]):
        try:
            _suspend_process(s["proc"])
        except Exception:
            return False
    # 浏览器/回环采集的 page.evaluate 只能在录制线程调用，交由主循环执行
    s["sync_capture"] = True
    s["paused"] = True
    return True


def resume_task(task_id):
    s = _run_state.get(task_id)
    if not s or not s["paused"]:
        return False
    if not _is_custom_capture(s["proc"]):
        try:
            _resume_process(s["proc"])
        except Exception:
            return False
    s["sync_capture"] = True
    s["paused"] = False
    return True


def stop_task(task_id):
    s = _run_state.get(task_id)
    if not s:
        return False
    s["stop"] = True
    if s["paused"]:  # 暂停中先恢复，否则收不到退出指令
        if not _is_custom_capture(s["proc"]):
            try:
                _resume_process(s["proc"])
            except Exception:
                pass
        s["sync_capture"] = True
        s["paused"] = False
    return True


def in_time_range(task):
    """当前时间是否落在任务的扫描时间窗口内。空值表示不限。"""
    ss = (task.get("scan_start") or "").strip()
    se = (task.get("scan_end") or "").strip()
    if not ss and not se:
        return True
    now = datetime.now().strftime("%H:%M")
    if ss and se:
        if ss <= se:
            return ss <= now <= se
        return now >= ss or now <= se  # 跨午夜
    if ss:
        return now >= ss
    return now <= se


def _reserve(task):
    if not in_time_range(task):
        return "不在扫描时间范围内，跳过"
    if not _lock.acquire(blocking=False):
        return "已有任务在检查或录制，本次跳过"
    _running.add(task["id"])
    recording_requested.set()


def _record_reserved(task):
    task_id = task["id"]
    try:
        with low_memory_slot if config.whisper_cpp_model() else nullcontext():
            last_result[task_id] = _do_record(task)
            return last_result[task_id]
    finally:
        recording_requested.clear()
        _running.discard(task_id)
        _run_state.pop(task_id, None)
        _lock.release()


def run_recording(task):
    """定时调度入口。"""
    reason = _reserve(task)
    if reason:
        last_result[task["id"]] = reason
        return reason
    return _record_reserved(task)


def start_recording(task):
    """手动检查在响应前占用录制槽，重复请求立即得到反馈。"""
    reason = _reserve(task)
    if reason:
        return reason
    threading.Thread(target=_record_reserved, args=(task,), daemon=True).start()


def _ffmpeg_error_hint(stderr_text, recorder):
    text = (stderr_text or "").strip()
    low = text.lower()
    if ("could not find audio device" in low or "device not found" in low
            or ("dshow" in low and "error" in low)):
        return "未找到虚拟声卡采集设备：" + recorder.device_hint
    if "permission denied" in low or "access is denied" in low:
        return "录音设备权限不足：" + recorder.device_hint
    if text:
        return "ffmpeg：" + text[-300:]
    return "ffmpeg 未输出音频数据，请检查系统音路由：" + recorder.device_hint


def _do_record(task):
    task_id = task["id"]
    platform = get_platform(task["platform"])
    recorder = current_recorder()
    ffmpeg_bin = detect_ffmpeg()
    start_ts = time.time()
    rec_id = None
    out_path = ""
    system_audio = False

    try:
        if not ffmpeg_bin:
            raise RuntimeError("未找到 ffmpeg，请安装后加入 PATH 或设置 RECORDER_FFMPEG")
        system_audio = recorder.device_ready()
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=config.HEADLESS,
                executable_path=config.BROWSER_EXECUTABLE,
                args=config.BROWSER_ARGS,
            )
            ctx = browser.new_context(
                user_agent=config.UA,
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )
            page = ctx.new_page()
            apply_stealth(page)

            # 1) 打开主播主页
            page.goto(task["anchor_home"], wait_until="domcontentloaded", timeout=60000)
            time.sleep(10)

            # 2) 检测是否开播
            if not platform.is_live(page):
                browser.close()
                return "未开播"

            # 3) 进入直播间
            live_url = platform.enter_live(page)
            if not live_url:
                browser.close()
                return "进入直播间失败"

            # 4) 创建产物记录，启动录制
            #    有虚拟声卡时录系统音；没有时用浏览器内音频采集（无需额外驱动）
            rec_id = db.create_recording(task_id)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = os.path.join(config.STORAGE_DIR, f"task{task_id}_{ts}.m4a")
            capture = None
            if system_audio:
                ffmpeg_proc = subprocess.Popen(
                    recorder.ffmpeg_cmd(out_path, ffmpeg_bin),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
            else:
                # 无虚拟声卡：Windows 用 WASAPI 回环录系统输出；其他平台或不可用时退回浏览器内采集
                loopback = LoopbackCapture(ffmpeg_bin, out_path)
                use_loopback = _IS_WINDOWS and loopback.available()
                capture = loopback if use_loopback else BrowserAudioCapture(page, ffmpeg_bin, out_path)
                capture.start()
                ffmpeg_proc = capture
            _run_state[task_id] = {
                "proc": ffmpeg_proc, "paused": False, "stop": False,
                "rec_id": rec_id, "out_path": out_path, "capture": capture,
                "sync_capture": False, "capture_paused": False,
            }
            start_ts = time.time()  # 录制计时从录音启动后开始

            # 5) 轮询：停止请求 / 超时 / 时间窗口结束 / 下播
            while ffmpeg_proc.poll() is None:
                st = _run_state.get(task_id, {})
                # 浏览器采集的 page.evaluate 必须在录制线程调用，不能由 API 线程直接调用
                if st.get("sync_capture") and _is_custom_capture(ffmpeg_proc):
                    want = bool(st.get("paused"))
                    if want != bool(st.get("capture_paused")):
                        try:
                            if want:
                                ffmpeg_proc.pause()
                            else:
                                ffmpeg_proc.resume()
                            st["capture_paused"] = want
                        except Exception:
                            pass
                    st["sync_capture"] = False
                if st.get("stop"):
                    break
                if time.time() - start_ts > config.MAX_RECORD_DURATION:
                    break
                if not in_time_range(task):
                    break
                if not st.get("paused") and not platform.live_still_on(page):
                    break
                # 分段等待，让暂停/恢复/停止请求及时生效
                deadline = time.monotonic() + config.POLL_INTERVAL
                while time.monotonic() < deadline:
                    st = _run_state.get(task_id, {})
                    if st.get("stop") or st.get("sync_capture"):
                        break
                    time.sleep(min(0.5, config.POLL_INTERVAL))

            # 6) 优雅停止：Windows 下 terminate() 是硬杀，MP4 来不及写 moov 头会变空文件
            stderr_text = ""
            _custom_capture = (getattr(ffmpeg_proc, "is_browser_capture", False)
                               or getattr(ffmpeg_proc, "is_loopback", False))
            if ffmpeg_proc.poll() is None and not _custom_capture:
                try:
                    if _run_state[task_id]["paused"]:
                        _resume_process(ffmpeg_proc)
                    ffmpeg_proc.stdin.write(b"q\n")
                    ffmpeg_proc.stdin.flush()
                except Exception:
                    pass
            try:
                _, err = ffmpeg_proc.communicate(timeout=12)
                stderr_text = (err or b"").decode("utf-8", "replace").strip()
            except Exception:
                try:
                    ffmpeg_proc.kill()
                except Exception:
                    pass
                _, err = ffmpeg_proc.communicate()
                stderr_text = (err or b"").decode("utf-8", "replace").strip()
            _suspended_pids.discard(ffmpeg_proc.pid)

            duration = int(time.time() - start_ts)
            size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
            if size == 0 or ffmpeg_proc.poll() not in (0, None):
                detail = stderr_text if (capture and stderr_text) else _ffmpeg_error_hint(stderr_text, recorder)
                db.finish_recording(rec_id, out_path, duration, size, status="failed", error=detail)
                browser.close()
                return "录制失败：" + detail
            # 读取封装时长，排除暂停、转码和浏览器退出耗时，同时验证音轨存在。
            metadata = subprocess.run([ffmpeg_bin, "-hide_banner", "-i", out_path],
                                      capture_output=True, text=True, errors="replace", timeout=15)
            clock = re.search(r"Duration: (\d+):(\d+):([\d.]+)", metadata.stderr)
            if not clock or "Audio:" not in metadata.stderr:
                raise RuntimeError("文件缺少可读取的音频时长或音轨")
            duration = round(int(clock[1]) * 3600 + int(clock[2]) * 60 + float(clock[3]))
            browser.close()
            db.finish_recording(rec_id, out_path, duration, size, status="completed")
            return f"录制完成 {duration}s / {size} 字节"
    except Exception as e:
        st = _run_state.pop(task_id, None)
        if st and st.get("proc"):
            proc = st["proc"]
            _suspended_pids.discard(proc.pid)
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
        if rec_id:
            size = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
            db.finish_recording(rec_id, out_path, int(time.time() - start_ts), size,
                                status="failed", error=str(e))
        return f"录制异常: {e}"
