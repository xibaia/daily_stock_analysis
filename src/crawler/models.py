# -*- coding: utf-8 -*-
"""
===================================
爬虫数据模型
===================================

定义爬取数据的结构，以及转换为 pandas DataFrame 的方法。
目标网站确定后，根据实际页面结构扩展字段。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd


@dataclass
class ScrapedStockRecord:
    """
    单条股票数据记录

    字段命名与 STANDARD_COLUMNS 对齐：
    date, open, high, low, close, volume, amount, pct_chg
    """
    date: str           # 日期 YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: float       # 成交量（股）
    amount: float       # 成交额（元）
    pct_chg: float      # 涨跌幅（%）

    # 可选扩展字段（目标网站确定后填充）
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        base = {
            "date": self.date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
            "pct_chg": self.pct_chg,
        }
        base.update(self.extra)
        return base


@dataclass
class ScrapedDataBatch:
    """
    一批爬取结果

    Attributes:
        records: 数据记录列表
        source_url: 数据来源 URL
        crawl_time: 爬取时间
        raw_html_snapshot: 原始 HTML 快照（用于调试）
    """
    records: List[ScrapedStockRecord]
    source_url: str
    crawl_time: datetime = field(default_factory=datetime.now)
    raw_html_snapshot: Optional[str] = None

    def to_dataframe(self) -> pd.DataFrame:
        """转换为 pandas DataFrame，列名标准化"""
        if not self.records:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount", "pct_chg"])
        data = [r.to_dict() for r in self.records]
        return pd.DataFrame(data)

    def is_empty(self) -> bool:
        return len(self.records) == 0

    def __len__(self) -> int:
        return len(self.records)


@dataclass
class TushareNewsRecord:
    """
    Tushare 新浪财经单条新闻记录

    Fields:
        title: 新闻标题
        url: 新闻链接
        source: 新闻来源（如"新浪财经"）
        published_date: 发布时间
        related_stocks: 关联股票代码列表
        code: 主关联股票代码或 "MARKET"
        content_summary: 内容摘要
        fetched_at: 爬取时间
    """
    title: str
    url: str
    source: str = ""
    published_date: Optional[datetime] = None
    related_stocks: List[str] = field(default_factory=list)
    code: str = "MARKET"
    content_summary: str = ""
    fetched_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "related_stocks": ",".join(self.related_stocks) if self.related_stocks else "",
            "code": self.code,
            "content_summary": self.content_summary,
            "fetched_at": self.fetched_at.isoformat(),
        }
