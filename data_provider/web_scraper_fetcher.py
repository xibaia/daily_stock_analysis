# -*- coding: utf-8 -*-
"""
===================================
Web 爬虫数据源适配器
===================================

职责：
- 将 CloakBrowser 爬虫接入现有数据源架构
- 遵循 BaseFetcher 接口规范
- 从目标网站爬取股票日线数据

使用方式：
1. 先执行 `python -m src.crawler --setup` 完成登录配置
2. 在 .env 中设置 CRAWLER_ENABLED=true 启用本数据源
3. DataFetcherManager 会自动将其纳入 fallback 链路

TODO: 目标网站确定后，调整 _parse_data 中的选择器和解析逻辑
"""

import logging
import os
from typing import Optional

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class WebScraperFetcher(BaseFetcher):
    """
    Web 登录爬虫数据源

    特性：
    - 基于 CloakBrowser，源码级反检测
    - Cookie/State 持久化，配置一次运行数月
    - 作为 fallback 数据源，当其他免费源不可用时启用
    """

    name: str = "WebScraperFetcher"
    # 优先级设较低（数字较大），作为兜底数据源
    # 当 efinance/akshare 等免费源失败后才启用
    priority: int = 5

    def __init__(self):
        """
        初始化爬虫数据源

        从环境变量读取配置，按需创建 CrawlerAuth 和 WebScraper 实例
        """
        super().__init__()

        self._base_url = (os.getenv("CRAWLER_BASE_URL") or "").strip()
        self._login_url = (os.getenv("CRAWLER_LOGIN_URL") or "").strip() or None
        self._data_url = (os.getenv("CRAWLER_DATA_URL") or "").strip()
        self._state_dir = (os.getenv("CRAWLER_STATE_DIR") or "").strip() or None
        self._enabled = os.getenv("CRAWLER_ENABLED", "false").lower() == "true"
        self._request_interval = float(os.getenv("CRAWLER_REQUEST_INTERVAL", "2.0"))
        self._max_retries = int(os.getenv("CRAWLER_MAX_RETRIES", "3"))

        # 延迟初始化：避免导入时创建浏览器实例
        self._auth = None
        self._scraper = None

    def _lazy_init(self) -> bool:
        """
        延迟初始化爬虫组件

        Returns:
            bool: 初始化是否成功
        """
        if self._scraper is not None:
            return True

        if not self._enabled:
            logger.debug("[WebScraperFetcher] 未启用 (CRAWLER_ENABLED=false)")
            return False

        if not self._base_url:
            logger.debug("[WebScraperFetcher] 未配置 CRAWLER_BASE_URL")
            return False

        try:
            from src.crawler.auth import CrawlerAuth
            from src.crawler.scraper import WebScraper
        except ImportError as e:
            logger.warning(f"[WebScraperFetcher] 导入爬虫模块失败: {e}")
            return False

        self._auth = CrawlerAuth(
            base_url=self._base_url,
            login_url=self._login_url,
            state_dir=self._state_dir,
        )

        if not self._auth.has_valid_state():
            logger.warning(
                f"[WebScraperFetcher] 登录态无效: {self._auth.state_path}\n"
                f"  请先执行: python -m src.crawler --setup"
            )
            return False

        self._scraper = WebScraper(
            auth=self._auth,
            data_url=self._data_url,
            request_interval=self._request_interval,
            max_retries=self._max_retries,
        )

        logger.info("[WebScraperFetcher] 爬虫组件初始化完成")
        return True

    # ------------------------------------------------------------------
    # BaseFetcher 抽象方法实现
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True,
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从目标网站爬取原始数据

        Args:
            stock_code: 股票代码（标准化后的格式）
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD

        Returns:
            pd.DataFrame: 原始数据
        """
        if not self._lazy_init():
            raise RuntimeError("WebScraperFetcher 未初始化或登录态无效")

        logger.info(f"[WebScraperFetcher] 开始爬取 {stock_code} ({start_date} ~ {end_date})")

        try:
            # TODO: 目标网站确定后，根据实际 URL 规则构建带日期参数的数据页地址
            # 示例：data_url_with_params = f"{self._data_url}?code={stock_code}&start={start_date}&end={end_date}"
            batch = self._scraper.crawl_all_pages()

            if batch.is_empty():
                logger.warning(f"[WebScraperFetcher] {stock_code} 未爬取到数据")
                return pd.DataFrame()

            df = batch.to_dataframe()

            # 按日期范围过滤
            if "date" in df.columns and not df.empty:
                df["date"] = pd.to_datetime(df["date"])
                mask = (df["date"] >= pd.to_datetime(start_date)) & (df["date"] <= pd.to_datetime(end_date))
                df = df.loc[mask].copy()

            logger.info(f"[WebScraperFetcher] {stock_code} 爬取完成: {len(df)} 条")
            return df

        except Exception as e:
            logger.error(f"[WebScraperFetcher] 爬取失败: {e}")
            raise

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化数据列名

        将爬取的数据列名统一为 STANDARD_COLUMNS：
        ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']

        Args:
            df: 原始数据 DataFrame
            stock_code: 股票代码

        Returns:
            pd.DataFrame: 标准化后的数据
        """
        if df.empty:
            return df

        # 确保 date 列为 datetime 类型
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

        # 数值列类型转换
        numeric_cols = ["open", "high", "low", "close", "volume", "amount", "pct_chg"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 按日期排序
        if "date" in df.columns:
            df = df.sort_values("date").reset_index(drop=True)

        return df

    # ------------------------------------------------------------------
    # 可用性探测
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """
        检查数据源是否可用

        条件：
        1. CRAWLER_ENABLED=true
        2. CRAWLER_BASE_URL 已配置
        3. 登录态文件存在
        """
        if not self._enabled:
            return False
        if not self._base_url:
            return False

        try:
            from src.crawler.auth import CrawlerAuth
            auth = CrawlerAuth(
                base_url=self._base_url,
                login_url=self._login_url,
                state_dir=self._state_dir,
            )
            return auth.has_valid_state()
        except Exception:
            return False
