# -*- coding: utf-8 -*-
"""抖音平台实现：主页 → 检测开播 → 进直播间 → 下播检测。

基于实测验证：开播时主页头部出现指向 live.douyin.com 的直播入口链接
（头像预览窗口），且 body 含「直播中」；直播间下播时 body 含「直播已结束」等。
"""
import time

from app.platforms.base import BasePlatform


class DouyinPlatform(BasePlatform):
    name = "douyin"
    label = "抖音"

    LIVE_END_KEYWORDS = (
        "直播已结束",
        "主播已下播",
        "直播已结束，期待下次",
        "直播暂时结束",
        "主播暂时离开",
    )

    def _live_entry_link(self, page):
        """返回主页头部的直播入口链接（排除导航/推荐里的 from_nav），无则 None。"""
        try:
            links = page.eval_on_selector_all(
                "a[href*='live.douyin.com']", "els => els.map(e => e.href)"
            )
        except Exception:
            return None
        for l in links or []:
            if "from_nav" in l:  # 顶部「直播」导航项，非主播直播入口
                continue
            return l
        return None

    def is_live(self, page) -> bool:
        if self._live_entry_link(page):
            return True
        body = page.locator("body").inner_text(timeout=10000)
        if not body.strip() or not page.locator("h1").count():
            raise RuntimeError("主播主页未正常显示，无法确认开播状态，请检查主页或稍后重试")
        return "直播中" in body

    def enter_live(self, page) -> str:
        link = self._live_entry_link(page)
        if not link:
            return None
        page.goto(link, wait_until="domcontentloaded", timeout=60000)
        time.sleep(8)
        self._ensure_playing(page)
        return page.url

    def live_still_on(self, page) -> bool:
        try:
            body = page.evaluate("document.body.innerText")
        except Exception:
            return True  # 读不到就继续，避免误停
        for kw in self.LIVE_END_KEYWORDS:
            if kw in body:
                return False
        return True

    def _ensure_playing(self, page):
        """确保直播间视频在播放且声音开启。"""
        try:
            page.evaluate(
                """() => {
                    const v = document.querySelector('video');
                    if (v) { v.muted = false; const pr = v.play(); if (pr) pr.catch(()=>{}); }
                }"""
            )
        except Exception:
            pass
