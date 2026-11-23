# -*- coding: utf-8 -*-
"""系统类型（直播平台）抽象层。

约定：每个平台实现一个「主播主页 → 检测是否开播 → 进入直播间」的流程。
新增平台（B站/快手等）只需继承 BasePlatform 并在 __init__.py 注册。
"""
from abc import ABC, abstractmethod


class BasePlatform(ABC):
    #: 平台标识，需与注册表 key、数据库 platform 字段一致
    name = "base"
    #: 展示名
    label = "基础平台"

    @abstractmethod
    def is_live(self, page) -> bool:
        """给定已打开主播主页的 page，判断当前是否开播。"""

    @abstractmethod
    def enter_live(self, page) -> str:
        """从主播主页进入直播间，返回直播间 URL（或 None 表示进不去）。"""

    @abstractmethod
    def live_still_on(self, page) -> bool:
        """给定直播间 page，判断直播是否仍在进行（用于录制中轮询下播）。"""
