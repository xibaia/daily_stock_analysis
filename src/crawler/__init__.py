# -*- coding: utf-8 -*-
"""
===================================
Web 登录爬虫模块
===================================

职责：
1. 使用 CloakBrowser 实现登录态管理
2. 支持首次人工配置 + 后续自动复用 cookie
3. 提供统一的页面爬取接口

依赖：
- cloakbrowser: 源码级反检测 Chromium
"""

from .auth import CrawlerAuth
from .scraper import WebScraper

__all__ = ["CrawlerAuth", "WebScraper"]
