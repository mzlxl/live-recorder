# -*- coding: utf-8 -*-
"""平台注册表：新增平台在此登记即可被系统识别。"""
from app.platforms.douyin import DouyinPlatform

PLATFORMS = {
    DouyinPlatform.name: DouyinPlatform(),
}


def get_platform(name):
    p = PLATFORMS.get(name)
    if p is None:
        raise ValueError(f"不支持的平台类型: {name}")
    return p


def list_platforms():
    return [{"name": p.name, "label": p.label} for p in PLATFORMS.values()]
