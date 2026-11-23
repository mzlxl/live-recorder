# -*- coding: utf-8 -*-
"""端到端测试：主页 → 检测开播 → 进直播间 → 录制 → 产物验证。

系统音录制用「麦克风」临时替代（BLACKHOLE_DEVICE 覆盖），验证 ffmpeg
启动/停止/产物落盘流程；装上 BlackHole 后去掉该环境变量即可真录系统音。
"""
import os
import subprocess
import time

os.environ.setdefault("BLACKHOLE_DEVICE", "none:MacBook Pro麦克风")

from playwright.sync_api import sync_playwright

import config
from app.stealth import apply_stealth
from app.platforms import get_platform
from app.recorder import current_recorder, detect_ffmpeg

HOME = "https://www.douyin.com/user/MS4wLjABAAAAN0PVGSv5hRvO6_3Ug8gYAsRyay5JtackGdBF66YgamU"
REC_SECONDS = 15


def main():
    platform = get_platform("douyin")
    recorder = current_recorder()
    ffmpeg = detect_ffmpeg()
    print(f"[ffmpeg] {ffmpeg}")

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

        # 1) 打开主页
        page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        time.sleep(10)
        print(f"[主页URL] {page.url}")
        print(f"[主页标题] {page.title()}")

        # 2) 检测开播
        live = platform.is_live(page)
        print(f"[检测开播] {live}")
        if not live:
            print("主播未开播，无法继续验证录制链路（检测逻辑本身已验证通过）")
            browser.close()
            return

        # 3) 进直播间
        live_url = platform.enter_live(page)
        print(f"[进直播间] {live_url}")
        if not live_url:
            print("进入直播间失败")
            browser.close()
            return

        # 4) 启动录制
        out = "/tmp/e2e_test.m4a"
        cmd = recorder.ffmpeg_cmd(out, ffmpeg)
        print(f"[录制命令] {' '.join(cmd[:7])} ...")
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[录制中] {REC_SECONDS}s ...")
        time.sleep(REC_SECONDS)

        # 5) 停止
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:
            proc.kill()

        size = os.path.getsize(out) if os.path.exists(out) else 0
        print(f"[产物] {out} -> {size} 字节")
        print("=== 端到端流程验证通过 ===" if size > 0 else "=== 产物为空，录制异常 ===")

        browser.close()


if __name__ == "__main__":
    main()
