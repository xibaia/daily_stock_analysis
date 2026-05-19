# -*- coding: utf-8 -*-
"""
===================================
页面爬取模块
===================================

职责：
1. 使用 CloakBrowser 打开已登录的页面
2. 分页爬取数据
3. 解析 HTML/JSON 提取结构化数据

TODO: 目标网站确定后，填充具体的选择器和解析逻辑
"""

import logging
import time
import random
from typing import List, Optional, Dict, Any
from datetime import datetime

from .auth import CrawlerAuth
from .models import ScrapedStockRecord, ScrapedDataBatch

logger = logging.getLogger(__name__)


class WebScraper:
    """
    Web 页面爬虫

    基于 CloakBrowser 实现数据爬取，支持：
    - 登录态自动复用
    - 分页爬取
    - 请求间隔控制
    - 错误重试
    - 页面快照保存（用于调试）
    """

    def __init__(
        self,
        auth: CrawlerAuth,
        data_url: Optional[str] = None,
        request_interval: float = 2.0,
        max_retries: int = 3,
    ):
        """
        初始化爬虫

        Args:
            auth: CrawlerAuth 实例，提供登录态
            data_url: 数据列表页地址
            request_interval: 页面间请求间隔（秒）
            max_retries: 单页最大重试次数
        """
        self.auth = auth
        self.data_url = data_url
        self.request_interval = request_interval
        self.max_retries = max_retries

        # 运行时状态
        self._browser = None
        self._context = None
        self._page = None

    def _ensure_browser(self) -> bool:
        """
        确保浏览器上下文已创建且登录态有效

        Returns:
            bool: 是否成功
        """
        if self._browser is not None and self._context is not None:
            return True

        browser, context = self.auth.create_context(headless=True)
        if browser is None or context is None:
            return False

        self._browser = browser
        self._context = context
        self._page = context.new_page()
        return True

    def _random_delay(self) -> None:
        """随机延迟，模拟人类行为"""
        delay = self.request_interval + random.uniform(0.5, 1.5)
        time.sleep(delay)

    def _is_login_page(self, url: str) -> bool:
        """检测是否被重定向到登录页"""
        return "/login" in url.lower() or "signin" in url.lower()

    def _save_snapshot(self, page, prefix: str = "error") -> str:
        """
        保存页面快照（HTML + 截图）用于调试

        Returns:
            str: 快照保存路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_dir = self.auth.state_dir / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        html_path = snapshot_dir / f"{prefix}_{timestamp}.html"
        png_path = snapshot_dir / f"{prefix}_{timestamp}.png"

        try:
            html = page.content()
            html_path.write_text(html, encoding="utf-8")
            page.screenshot(path=str(png_path), full_page=True)
            logger.info(f"页面快照已保存: {html_path}, {png_path}")
            return str(html_path)
        except Exception as e:
            logger.warning(f"保存快照失败: {e}")
            return ""

    def crawl_page(self, url: Optional[str] = None) -> ScrapedDataBatch:
        """
        爬取单个页面

        Args:
            url: 要爬取的页面地址（留空使用 self.data_url）

        Returns:
            ScrapedDataBatch: 爬取结果
        """
        target_url = url or self.data_url
        if not target_url:
            raise ValueError("未配置 data_url")

        if not self._ensure_browser():
            logger.error("浏览器启动失败，可能登录态无效")
            return ScrapedDataBatch(records=[], source_url=target_url)

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"正在爬取: {target_url} (尝试 {attempt}/{self.max_retries})")

                self._page.goto(target_url, wait_until="networkidle", timeout=30000)

                # 检测是否被踢到登录页
                if self._is_login_page(self._page.url):
                    logger.error("登录态已过期，被重定向到登录页")
                    self.auth.notify_state_expired()
                    return ScrapedDataBatch(records=[], source_url=target_url)

                # 等待页面数据加载完成
                # TODO: 目标网站确定后，根据实际加载特征调整等待条件
                # 示例：等待表格加载
                # self._page.wait_for_selector("table.data-table", timeout=10000)

                # TODO: 目标网站确定后，实现具体的数据提取逻辑
                records = self._parse_data(self._page)

                batch = ScrapedDataBatch(
                    records=records,
                    source_url=target_url,
                    raw_html_snapshot=None,  # 成功时不保存快照，节省空间
                )

                logger.info(f"爬取完成: {len(batch)} 条记录")
                return batch

            except Exception as e:
                logger.warning(f"爬取失败 (尝试 {attempt}/{self.max_retries}): {e}")
                if attempt == self.max_retries:
                    # 最后一次尝试，保存快照用于排查
                    snapshot_path = self._save_snapshot(self._page, prefix="crawl_error")
                    logger.error(f"爬取最终失败，快照: {snapshot_path}")
                    return ScrapedDataBatch(records=[], source_url=target_url)

                self._random_delay()

        return ScrapedDataBatch(records=[], source_url=target_url)

    def _parse_data(self, page) -> List[ScrapedStockRecord]:
        """
        解析页面数据

        TODO: 目标网站确定后，根据实际页面 DOM 结构实现解析逻辑

        Args:
            page: CloakBrowser page 对象

        Returns:
            List[ScrapedStockRecord]: 解析后的数据记录
        """
        records: List[ScrapedStockRecord] = []

        # ============================================================
        # 占位实现：目标网站确定后替换为实际解析逻辑
        # ============================================================
        # 示例：从表格解析数据
        # rows = page.locator("table.data-table tbody tr").all()
        # for row in rows:
        #     cells = row.locator("td").all()
        #     if len(cells) < 8:
        #         continue
        #     record = ScrapedStockRecord(
        #         date=cells[0].text_content().strip(),
        #         open=float(cells[1].text_content().strip()),
        #         high=float(cells[2].text_content().strip()),
        #         low=float(cells[3].text_content().strip()),
        #         close=float(cells[4].text_content().strip()),
        #         volume=float(cells[5].text_content().strip().replace(",", "")),
        #         amount=float(cells[6].text_content().strip().replace(",", "")),
        #         pct_chg=float(cells[7].text_content().strip().replace("%", "")),
        #     )
        #     records.append(record)
        # ============================================================

        logger.warning("_parse_data 为占位实现，目标网站确定后需实现具体解析逻辑")
        return records

    def crawl_all_pages(self) -> ScrapedDataBatch:
        """
        爬取所有分页数据

        TODO: 目标网站确定后，根据分页方式实现（点击下一页/滚动加载/URL 参数）

        Returns:
            ScrapedDataBatch: 合并后的所有数据
        """
        all_records: List[ScrapedStockRecord] = []
        current_url = self.data_url

        # TODO: 目标网站确定后实现分页逻辑
        # 示例：点击下一页直到没有更多数据
        # while True:
        #     batch = self.crawl_page(current_url)
        #     all_records.extend(batch.records)
        #
        #     next_btn = self._page.locator("a.next-page").first
        #     if not next_btn.is_visible() or "disabled" in (next_btn.get_attribute("class") or ""):
        #         break
        #
        #     next_btn.click()
        #     self._random_delay()

        # 占位：只爬取第一页
        batch = self.crawl_page(current_url)
        all_records.extend(batch.records)

        return ScrapedDataBatch(
            records=all_records,
            source_url=self.data_url or "",
        )

    def close(self) -> None:
        """关闭浏览器，释放资源"""
        if self._context:
            try:
                self._context.close()
            except Exception as e:
                logger.debug(f"关闭 context 时出错: {e}")
            self._context = None

        if self._browser:
            try:
                self._browser.close()
            except Exception as e:
                logger.debug(f"关闭 browser 时出错: {e}")
            self._browser = None

        self._page = None
        logger.info("爬虫资源已释放")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
