# -*- coding: utf-8 -*-
"""
Tushare 新闻爬虫单元测试
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

# 确保项目根目录在路径中
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.crawler.config import TushareNewsConfig
from src.crawler.models import TushareNewsRecord
from src.crawler.storage import TushareNewsStorage
from src.crawler.tushare_news import TushareNewsScraper


class TestTushareNewsConfig(unittest.TestCase):
    """测试配置模块"""

    def setUp(self):
        self._orig_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_default_values(self):
        config = TushareNewsConfig.load()
        self.assertFalse(config.enabled)
        self.assertEqual(config.schedule_time, "08:00")
        self.assertEqual(config.max_pages, 10)
        self.assertEqual(config.max_age_days, 30)
        self.assertEqual(config.request_interval, 2.0)

    def test_env_override(self):
        os.environ["TUSHARE_NEWS_ENABLED"] = "true"
        os.environ["TUSHARE_NEWS_SCHEDULE_TIME"] = "09:30"
        os.environ["TUSHARE_NEWS_MAX_PAGES"] = "20"

        config = TushareNewsConfig.load()
        self.assertTrue(config.enabled)
        self.assertEqual(config.schedule_time, "09:30")
        self.assertEqual(config.max_pages, 20)


class TestTushareNewsRecord(unittest.TestCase):
    """测试数据模型"""

    def test_basic_creation(self):
        record = TushareNewsRecord(
            title="测试新闻",
            url="https://example.com/news/1",
            source="新浪财经",
            code="600519",
            related_stocks=["600519", "000001"],
        )
        self.assertEqual(record.title, "测试新闻")
        self.assertEqual(record.code, "600519")
        self.assertEqual(record.related_stocks, ["600519", "000001"])

    def test_market_news_default_code(self):
        record = TushareNewsRecord(
            title="市场新闻",
            url="https://example.com/news/2",
        )
        self.assertEqual(record.code, "MARKET")
        self.assertEqual(record.related_stocks, [])

    def test_to_dict(self):
        now = datetime.now()
        record = TushareNewsRecord(
            title="测试",
            url="https://example.com",
            published_date=now,
            related_stocks=["600519"],
        )
        d = record.to_dict()
        self.assertEqual(d["title"], "测试")
        self.assertEqual(d["code"], "MARKET")
        self.assertEqual(d["related_stocks"], "600519")


class TestTushareNewsStorage(unittest.TestCase):
    """测试存储层"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.storage = TushareNewsStorage(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_query(self):
        records = [
            TushareNewsRecord(
                title="新闻1",
                url="https://example.com/1",
                source="新浪财经",
                published_date=datetime(2024, 1, 15, 10, 0, 0),
                code="600519",
            ),
            TushareNewsRecord(
                title="新闻2",
                url="https://example.com/2",
                source="新浪财经",
                published_date=datetime(2024, 1, 15, 11, 0, 0),
                code="MARKET",
            ),
        ]

        saved = self.storage.save_news(records)
        self.assertEqual(saved, 2)

        # 查询当天新闻
        results = self.storage.get_news_by_date(datetime(2024, 1, 15))
        self.assertEqual(len(results), 2)

        # 按 code 过滤
        results = self.storage.get_news_by_date(datetime(2024, 1, 15), code="600519")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "新闻1")

    def test_duplicate_handling(self):
        record = TushareNewsRecord(
            title="原始标题",
            url="https://example.com/duplicate",
            source="新浪财经",
            published_date=datetime.now(),
        )

        self.storage.save_news([record])

        # 重复保存应更新而非报错
        updated = TushareNewsRecord(
            title="更新标题",
            url="https://example.com/duplicate",
            source="东方财富",
            published_date=datetime.now(),
        )
        self.storage.save_news([updated])

        results = self.storage.get_latest_news(days=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "更新标题")
        self.assertEqual(results[0].source, "东方财富")

    def test_has_news_for_date(self):
        self.assertFalse(self.storage.has_news_for_date(datetime(2024, 1, 15)))

        self.storage.save_news([
            TushareNewsRecord(
                title="新闻",
                url="https://example.com/1",
                published_date=datetime(2024, 1, 15, 10, 0, 0),
            )
        ])

        self.assertTrue(self.storage.has_news_for_date(datetime(2024, 1, 15)))

    def test_cleanup_old_news(self):
        old_record = TushareNewsRecord(
            title="旧新闻",
            url="https://example.com/old",
            fetched_at=datetime.now() - timedelta(days=60),
        )
        new_record = TushareNewsRecord(
            title="新新闻",
            url="https://example.com/new",
            fetched_at=datetime.now(),
        )

        self.storage.save_news([old_record, new_record])
        self.assertEqual(self.storage.count_news(days=90), 2)

        deleted = self.storage.cleanup_old_news(max_age_days=30)
        self.assertEqual(deleted, 1)
        self.assertEqual(self.storage.count_news(days=90), 1)


class TestTushareNewsScraperParse(unittest.TestCase):
    """测试爬虫解析逻辑"""

    def setUp(self):
        self.scraper = TushareNewsScraper()

    def test_parse_news_api_response_list(self):
        data = {"data": [{"title": "新闻1"}, {"title": "新闻2"}]}
        result = self.scraper._parse_news_api_response(data)
        self.assertEqual(len(result), 2)

    def test_parse_news_api_response_nested(self):
        data = {"data": {"list": [{"title": "新闻1"}]}}
        result = self.scraper._parse_news_api_response(data)
        self.assertEqual(len(result), 1)

    def test_parse_news_api_response_empty(self):
        self.assertEqual(self.scraper._parse_news_api_response({}), [])
        self.assertEqual(self.scraper._parse_news_api_response("string"), [])

    def test_extract_related_stocks_from_list(self):
        item = {"stocks": ["600519", "000001"]}
        result = self.scraper._extract_related_stocks(item)
        self.assertEqual(result, ["600519", "000001"])

    def test_extract_related_stocks_from_string(self):
        item = {"stock_codes": "600519,000001"}
        result = self.scraper._extract_related_stocks(item)
        self.assertEqual(result, ["600519", "000001"])

    def test_extract_related_stocks_from_title(self):
        item = {"title": "贵州茅台(600519)发布年报"}
        result = self.scraper._extract_related_stocks(item)
        self.assertIn("600519", result)

    def test_normalize_news_item(self):
        item = {
            "title": "测试新闻",
            "url": "/news/1",
            "source": "新浪财经",
            "published_date": "2024-01-15 10:00:00",
            "stocks": ["600519"],
            "summary": "摘要内容",
        }
        record = self.scraper._normalize_news_item(item)
        self.assertIsNotNone(record)
        self.assertEqual(record.title, "测试新闻")
        self.assertEqual(record.code, "600519")
        self.assertEqual(record.published_date, datetime(2024, 1, 15, 10, 0, 0))

    def test_normalize_news_item_missing_title(self):
        record = self.scraper._normalize_news_item({"url": "/news/1"})
        self.assertIsNone(record)

    def test_extract_datetime_iso(self):
        item = {"time": "2024-01-15T10:00:00Z"}
        result = self.scraper._extract_datetime(item, ["time"])
        self.assertIsNotNone(result)

    def test_extract_datetime_timestamp(self):
        item = {"ts": "1705312800"}
        result = self.scraper._extract_datetime(item, ["ts"])
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
