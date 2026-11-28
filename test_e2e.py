"""使用独立临时库，从 Web 页面验收真实直播、后台转写、音频和文稿操作。"""
import argparse
import contextlib
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from opencc import OpenCC
from playwright.sync_api import expect, sync_playwright

import config
from app import db
from app.recorder import detect_ffmpeg
from verify_recording import probe_audio

PROFILE = "https://www.douyin.com/user/MS4wLjABAAAAN0PVGSv5hRvO6_3Ug8gYAsRyay5JtackGdBF66YgamU?from_tab_name=main"


@contextlib.contextmanager
def isolated_service(work):
    db.DB_PATH = str(work / "recorder.db")
    config.STORAGE_DIR = str(work / "recordings")
    Path(config.STORAGE_DIR).mkdir()
    config.MAX_RECORD_DURATION = 70
    config.POLL_INTERVAL = 2
    from app.main import app
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            limit = time.monotonic() + 10
            while not server.started and time.monotonic() < limit:
                time.sleep(0.05)
            assert server.started
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(15)


def pick(page, trigger, label):
    trigger.click()
    page.get_by_role("option", name=label, exact=True).click()


def layouts(browser, url):
    page = browser.new_page(reduced_motion="reduce")
    for w, h in [(1920, 1080), (1440, 900), (375, 667), (844, 390), (768, 1024)]:
        page.set_viewport_size({"width": w, "height": h})
        page.goto(url)
        page.locator("#task-search").fill("验收搜索")
        page.get_by_role("button", name="清空任务搜索").click()
        expect(page.locator("#task-search")).to_be_focused()
        expect(page.locator("#task-search")).to_have_value("")
        for key in ("tasks", "recordings", "dashboard"):
            page.locator(f"[data-tab={key}]").click()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#btn-add").click()
        expect(page.locator("#f-name")).to_be_focused()
        assert page.locator("#editor").evaluate("(d)=>d.scrollWidth <= d.clientWidth")
        frequency = page.locator("#f-frequency")
        frequency.click()
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        expect(frequency).to_have_text("每 120 分钟")
        hours = page.get_by_role("combobox", name="开始小时")
        pick(page, hours, "23")
        expect(hours).to_have_text("23")
        minutes = page.get_by_role("combobox", name="开始分钟")
        minutes.click()
        page.keyboard.press("5")
        page.keyboard.press("9")
        page.keyboard.press("Enter")
        expect(minutes).to_have_text("59")
        page.get_by_role("button", name="清除开始时间").click()
        expect(hours).to_have_text("时")
        page.locator("#f-platform").click()
        expect(page.get_by_role("listbox")).to_be_visible()
        rect = page.get_by_role("listbox").bounding_box()
        assert rect["x"] >= 0 and rect["x"] + rect["width"] <= w + 1
        assert rect["y"] >= 0 and rect["y"] + rect["height"] <= h + 1
        page.keyboard.press("Escape")
        expect(page.get_by_role("listbox")).not_to_be_visible()
        expect(page.locator("#editor")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.locator("#editor")).not_to_be_visible()
        expect(page.locator("#btn-add")).to_be_focused()
    page.close()


def verify_live(browser, url, profile, work):
    page = browser.new_page(accept_downloads=True, permissions=["clipboard-read", "clipboard-write"])
    desktop = page.request.get(url + "/api/status").json()["desktop_files"]
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    page.locator("#btn-add").click()
    page.get_by_text("保存任务", exact=True).click()
    expect(page.locator("#f-name")).to_be_focused()
    page.locator("#f-name").fill("企智直播 · 自动验收")
    page.locator("#f-home").fill(profile)
    pick(page, page.locator("#f-frequency"), "每 120 分钟")
    pick(page, page.get_by_role("combobox", name="开始小时"), "22")
    pick(page, page.get_by_role("combobox", name="结束小时"), "01")
    page.get_by_text("保存任务", exact=True).click()
    expect(page.locator("#task-meta")).to_contain_text("次日")
    page.get_by_role("button", name="编辑").click()
    expect(page.locator("#f-frequency")).to_have_text("每 120 分钟")
    page.get_by_role("button", name="清除开始时间").click()
    page.get_by_role("button", name="清除结束时间").click()
    page.get_by_text("保存任务", exact=True).click()
    page.locator("#task-actions summary").click()
    page.get_by_role("button", name="停用", exact=True).click()
    page.locator("#task-actions summary").click()
    page.get_by_role("button", name="启用", exact=True).click()
    page.get_by_role("button", name="立即检查").click()
    pause = page.get_by_role("button", name="暂停", exact=True)
    try:
        pause.wait_for(timeout=120000)
    except Exception as e:
        raise AssertionError("未进入真实录制：" + page.locator("#task-detail").inner_text()) from e
    time.sleep(12)
    pause.click()
    expect(page.locator("#task-list")).to_contain_text("已暂停")
    page.wait_for_timeout(1500)
    page.get_by_role("button", name="恢复").click()
    page.wait_for_timeout(18000)
    page.get_by_role("button", name="停止").click()
    page.locator("#confirm-submit").click()
    expect(page.locator("#inline-reader .sentence").first).to_be_visible(timeout=300000)
    page.locator("#sentence-view").click()
    page.locator("#inline-reader .sentence").first.click()
    page.wait_for_function("()=>!player.paused && player.currentTime > 0.1")
    page.get_by_role("button", name="暂停回听").click()
    pick(page, page.locator("#speed"), "1.5×")
    assert page.locator("#player").evaluate("p => p.paused && p.playbackRate === 1.5")
    page.locator("#play-position").focus()
    page.keyboard.press("End")
    page.keyboard.press("Home")
    page.get_by_role("button", name="播放录音").click()
    page.wait_for_function("()=>!player.paused && player.currentTime > 0.1")
    page.locator("#mute").click()
    expect(page.locator("#mute")).to_have_attribute("aria-pressed", "true")
    page.locator("#paragraph-view").click()
    expect(page.locator("#paragraph-view")).to_have_attribute("aria-pressed", "true")
    print("PASS 正式工作台内联转写、逐句回听与段落切换", flush=True)
    page.locator("[data-tab=recordings]").click()
    pick(page, page.locator("#filter-task"), "企智直播 · 自动验收")
    page.get_by_role("button", name="刷新资料库").click()
    page.wait_for_function("""()=>/等待转写|正在转写|文稿已就绪/.test(document.querySelector('#recording-list').textContent)""", timeout=45000)
    page.locator("#recording-list [data-action=read]").first.click()
    expect(page.locator(".sentence").first).to_be_visible(timeout=300000)
    groups = page.locator(".passage").count()
    sentences = page.locator(".sentence").count()
    assert groups and sentences
    page.locator("#sentence-view").click()
    expect(page.locator("#sentence-view")).to_have_attribute("aria-pressed", "true")
    page.locator("#copy-text").click()
    expect(page.locator("#transcript-status")).to_have_text("全文已复制")
    copied = page.evaluate("navigator.clipboard.readText()")
    assert copied.strip() and OpenCC("t2s").convert(copied) == copied
    page.locator(".sentence").last.click()
    page.wait_for_function("()=>!player.paused && player.currentTime > 0.1")
    with page.expect_download() as download:
        page.get_by_text("下载音频", exact=True).click()
    output = work / "verified.m4a"
    download.value.save_as(output)
    result = probe_audio(detect_ffmpeg(), output, min_seconds=12)
    (work / "verified.txt").write_text(page.locator("#transcript-body").inner_text(), encoding="utf-8")
    if desktop:
        for name, route in (("定位文件", "reveal"), ("系统播放", "open")):
            with page.expect_response(lambda r: r.url.endswith("/" + route)) as response:
                page.get_by_role("button", name=name).click()
            assert response.value.ok and response.value.json()["ok"]
    else:
        assert page.get_by_role("button", name="系统播放").count() == 0
    page.get_by_role("button", name="删除录音").click()
    page.get_by_role("button", name="取消", exact=True).click()
    expect(page.locator("#reader")).to_be_visible()
    page.get_by_role("button", name="删除录音").click()
    page.locator("#confirm-submit").click()
    expect(page.locator("#recording-list")).to_contain_text("暂无匹配")
    if desktop:
        page.get_by_role("button", name="打开目录").click()
    page.locator("[data-tab=tasks]").click()
    page.locator("#task-actions summary").click()
    page.get_by_role("button", name="删除", exact=True).click()
    page.locator("#confirm-submit").click()
    expect(page.locator("#task-list")).to_contain_text("还没有")
    assert not errors, errors
    assert page.request.get(url + "/api/recordings").json() == []
    print(f"PASS 真实账号录制、转写、回听、文件和任务操作：{result}，{groups} 段 / {sentences} 句")
    page.close()


def verify_retry(browser, url, profile, work):
    """在隔离库构造已损坏的历史文件，然后用刚刚的实录修复它。"""
    task_id = db.create_task("历史文稿恢复", profile)
    path = Path(config.STORAGE_DIR, "repair.m4a")
    path.write_bytes(b"invalid")
    rec_id = db.create_recording(task_id)
    with db._conn() as c:
        c.execute("UPDATE recordings SET file_path=?,file_size=7,status='completed' WHERE id=?",
                  (str(path), rec_id))
    page = browser.new_page(viewport={"width": 375, "height": 667})
    try:
        page.goto(url + "/#recordings")
        page.locator("[data-action=read]").click()
        page.get_by_text("生成文稿", exact=True).click()
        expect(page.locator("#transcript-status")).to_contain_text("转写失败", timeout=60000)
        shutil.copyfile(work / "verified.m4a", path)
        page.get_by_text("重试转写", exact=True).click()
        expect(page.locator(".sentence").first).to_be_visible(timeout=300000)
        page.locator("#sentence-view").click()
        assert page.locator("#reader").evaluate("d=>d.scrollWidth<=d.clientWidth")
        assert not page.request.post(url + "/api/tasks", data={"name":"", "anchor_home":"invalid"}).ok
        assert page.request.delete(f"{url}/api/tasks/{task_id}?delete_files=true").ok
        assert not path.exists() and db.get_recording(rec_id) is None
        print("PASS 历史录音、损坏文件、恢复后重试、手机文稿和关联删除")
    finally:
        page.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=PROFILE)
    parser.add_argument("--artifacts", type=Path, help="创建新目录，保留实录与识别文稿")
    parser.add_argument("--engines", nargs="+", default=["chromium"], choices=["chromium", "webkit", "firefox"])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        work = args.artifacts or Path(tmp)
        if args.artifacts:
            work.mkdir(parents=True, exist_ok=False)
        with isolated_service(work) as url, sync_playwright() as playwright:
            for name in args.engines:
                options = {"executable_path": config.BROWSER_EXECUTABLE} if name == "chromium" else {}
                browser = getattr(playwright, name).launch(headless=True, **options)
                try:
                    layouts(browser, url)
                    print(f"PASS {name} 五种视口、导航、表单和键盘关闭", flush=True)
                finally:
                    browser.close()
            browser = playwright.chromium.launch(headless=True, executable_path=config.BROWSER_EXECUTABLE)
            try:
                verify_live(browser, url, args.profile, work)
                verify_retry(browser, url, args.profile, work)
            finally:
                browser.close()


if __name__ == "__main__":
    main()
