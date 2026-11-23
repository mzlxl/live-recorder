# -*- coding: utf-8 -*-
"""录制执行器：核心流程「主播主页 → 检测开播 → 进直播间 → 系统音录制 → 下播自停」。

系统音是全局共享资源，同一时刻只允许一个任务在录，加锁保证不串音。
支持：暂停(暂停 ffmpeg 录音)/恢复/停止，以及按任务时间窗口扫描与录制。
"""
import os
import signal
import subprocess
import threading
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

import config
from app import db
from app.stealth import apply_stealth
from app.platforms import get_platform
from app.recorder import current_recorder, detect_ffmpeg

# 全局锁：系统音同一时刻只能录一路
_lock = threading.Lock()
_running = set()
# task_id -> {"proc": ffmpeg, "paused": bool, "stop": bool, "rec_id": int, "out_path": str}
_run_state = {}


def is_running(task_id):
    return task_id in _running


def is_paused(task_id):
    s = _run_state.get(task_id)
    return bool(s and s["paused"])


def pause_task(task_id):
    s = _run_state.get(task_id)
    if not s or s["paused"]:
        return False
    s["paused"] = True
    try:
        s["proc"].send_signal(signal.SIGSTOP)
    except Exception:
        pass
    return True


def resume_task(task_id):
    s = _run_state.get(task_id)
    if not s or not s["paused"]:
        return False
    s["paused"] = False
    try:
        s["proc"].send_signal(signal.SIGCONT)
    except Exception:
        pass
    return True


def stop_task(task_id):
    s = _run_state.get(task_id)
    if not s:
        return False
    s["stop"] = True
    if s["paused"]:  # 暂停中先恢复再停，让 ffmpeg 能正常退出
        try:
            s["proc"].send_signal(signal.SIGCONT)
        except Exception:
            pass
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


def run_recording(task):
    """调度入口。返回结果描述字符串。"""
    task_id = task["id"]
    if not in_time_range(task):
        return "不在扫描时间范围内，跳过"
    if not _lock.acquire(blocking=False):
        return "已有其他任务在录制（系统音全局共享），本次跳过"
    _running.add(task_id)
    try:
        return _do_record(task)
    finally:
        _running.discard(task_id)
        _run_state.pop(task_id, None)
        _lock.release()


def _do_record(task):
    task_id = task["id"]
    platform = get_platform(task["platform"])
    recorder = current_recorder()
    ffmpeg_bin = detect_ffmpeg()
    start_ts = time.time()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--autoplay-policy=no-user-gesture-required"],
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

            # 4) 创建产物记录，启动系统音录制
            rec_id = db.create_recording(task_id)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = os.path.join(config.STORAGE_DIR, f"task{task_id}_{ts}.m4a")
            ffmpeg_proc = subprocess.Popen(
                recorder.ffmpeg_cmd(out_path, ffmpeg_bin),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _run_state[task_id] = {
                "proc": ffmpeg_proc, "paused": False, "stop": False,
                "rec_id": rec_id, "out_path": out_path,
            }

            # 5) 轮询：停止请求 / 超时 / 时间窗口结束 / 下播
            while ffmpeg_proc.poll() is None:
                st = _run_state.get(task_id, {})
                if st.get("stop"):
                    break
                if time.time() - start_ts > config.MAX_RECORD_DURATION:
                    break
                if not in_time_range(task):
                    break
                if not st.get("paused") and not platform.live_still_on(page):
                    break
                time.sleep(config.POLL_INTERVAL)

            # 6) 停止录制
            if ffmpeg_proc.poll() is None:
                ffmpeg_proc.terminate()
                try:
                    ffmpeg_proc.wait(timeout=15)
                except Exception:
                    ffmpeg_proc.kill()

            duration = int(time.time() - start_ts)
            size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
            if size == 0:
                db.finish_recording(rec_id, out_path, duration, size, status="failed",
                                    error="产物为空（检查虚拟声卡 BlackHole 是否安装）")
                browser.close()
                return "录制产物为空"
            db.finish_recording(rec_id, out_path, duration, size, status="completed")
            browser.close()
            return f"录制完成 {duration}s / {size} 字节"
    except Exception as e:
        st = _run_state.pop(task_id, None)
        if st and st.get("rec_id"):
            fp = st.get("out_path", "")
            size = os.path.getsize(fp) if fp and os.path.exists(fp) else 0
            db.finish_recording(st["rec_id"], fp, int(time.time() - start_ts), size,
                                status="failed", error=str(e))
        return f"录制异常: {e}"
