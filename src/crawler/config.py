# -*- coding: utf-8 -*-
"""
===================================
Tushare 新闻爬虫配置模块
===================================

独立读取环境变量，不依赖主项目的 Config 系统。
配置项前缀统一为 TUSHARE_NEWS_*
"""

import os
from pathlib import Path
from typing import Optional


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, "")
    if not val:
        return default
    return val.lower() in ("true", "1", "yes", "on")


def _env_int(key: str, default: int = 0) -> int:
    val = os.getenv(key, "")
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_float(key: str, default: float = 0.0) -> float:
    val = os.getenv(key, "")
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


class TushareNewsConfig:
    """Tushare 新闻爬虫配置"""

    def __init__(self):
        # 每次实例化时重新读取环境变量
        self.enabled: bool = _env_bool("TUSHARE_NEWS_ENABLED", False)
        self.schedule_time: str = _env("TUSHARE_NEWS_SCHEDULE_TIME", "08:00")
        self.state_dir: Path = Path(_env("TUSHARE_NEWS_STATE_DIR", "./data/tushare_news_state"))
        self.request_interval: float = _env_float("TUSHARE_NEWS_REQUEST_INTERVAL", 2.0)
        self.max_retries: int = _env_int("TUSHARE_NEWS_MAX_RETRIES", 3)
        self.max_age_days: int = _env_int("TUSHARE_NEWS_MAX_AGE_DAYS", 30)
        self.max_pages: int = _env_int("TUSHARE_NEWS_MAX_PAGES", 10)
        self.username: str = _env("TUSHARE_NEWS_USERNAME", "")
        self.password: str = _env("TUSHARE_NEWS_PASSWORD", "")
        self.base_url: str = "https://tushare.pro"
        self.login_url: str = "https://tushare.pro/weborder/#/login"
        self.data_url: str = "https://tushare.pro/news/sina"

    @classmethod
    def load(cls) -> "TushareNewsConfig":
        """加载配置（每次调用重新读取环境变量）"""
        return cls()

    def __repr__(self) -> str:
        return (
            f"TushareNewsConfig(enabled={self.enabled}, "
            f"schedule_time={self.schedule_time}, "
            f"state_dir={self.state_dir}, "
            f"max_pages={self.max_pages})"
        )
