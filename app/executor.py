# -*- coding: utf-8 -*-
"""录制执行器：核心流程「主播主页 → 检测开播 → 进直播间 → 系统音录制 → 下播自停」。

系统音是全局共享资源，同一时刻只允许一个任务在录，加锁保证不串音。
"""
import os
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


def is_running(task_id):
    return task_id in _running


def run_recording(task):
    """调度入口。返回结果描述字符串。"""
    task_id = task["id"]
    if not _lock.acquire(blocking=False):
        return "已有其他任务在录制（系统音全局共享），本次跳过"
    _running.add(task_id)
    try:
        return _do_record(task)
    finally:
        _running.discard(task_id)
        _lock.release()


def _do_record(task):
    task_id = task["id"]
    platform = get_platform(task["platform"])
    recorder = current_recorder()
    ffmpeg_bin = detect_ffmpeg()

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
            start_ts = time.time()

            # 5) 轮询下播，直到直播结束或超时
            while ffmpeg_proc.poll() is None:
                elapsed = time.time() - start_ts
                if elapsed > config.MAX_RECORD_DURATION:
                    break
                if not platform.live_still_on(page):
                    break
                time.sleep(config.POLL_INTERVAL)

            # 6) 停止录制
            ffmpeg_proc.terminate()
            try:
                ffmpeg_proc.wait(timeout=15)
            except Exception:
                ffmpeg_proc.kill()

            duration = int(time.time() - start_ts)
            size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
            if size == 0:
                db.finish_recording(rec_id, out_path, duration, size, status="failed", error="产物为空")
                browser.close()
                return "录制产物为空"

            db.finish_recording(rec_id, out_path, duration, size, status="completed")
            browser.close()
            return f"录制完成 {duration}s / {size} 字节"
    except Exception as e:
        db.create_recording(task_id)  # 记录失败
        return f"录制异常: {e}"
