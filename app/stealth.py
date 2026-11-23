# -*- coding: utf-8 -*-
"""浏览器指纹隐藏：抹掉 Playwright 最容易被检测的自动化特征。

仅隐藏「浅层」指纹（webdriver 标志、chrome 对象、plugins 等），
不追求 100% 反检测（无法做到），目标是让常规风控看不到明显自动化痕迹。
"""

STEALTH_JS = """
(() => {
    // 1. navigator.webdriver 置 undefined
    try {
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    } catch (e) {}
    // 2. 补齐 window.chrome（真 Chrome 必有，Playwright 默认缺失）
    try {
        window.chrome = window.chrome || { runtime: {} };
    } catch (e) {}
    // 3. languages 伪装
    try {
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en'],
        });
    } catch (e) {}
    // 4. plugins 伪装（真 Chrome 有 5 个 plugin）
    try {
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
    } catch (e) {}
    // 5. permissions 兜底
    try {
        const oq = navigator.permissions && navigator.permissions.query;
        if (oq) {
            navigator.permissions.query = (p) =>
                p && p.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : oq.call(navigator.permissions, p);
        }
    } catch (e) {}
})();
"""


def apply_stealth(page):
    """页面加载后注入，抹掉基础自动化指纹。"""
    try:
        page.add_init_script(STEALTH_JS)
    except Exception:
        pass
    return page
