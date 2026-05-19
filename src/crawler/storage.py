# -*- coding: utf-8 -*-
"""
===================================
Tushare 新闻独立存储层
===================================

不依赖主项目的 storage.py，使用独立的 SQLAlchemy 模型
但连接到同一个 SQLite 数据库文件，便于统一管理和备份。

表名: tushare_news
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, create_engine, UniqueConstraint, Index, inspect
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from .models import TushareNewsRecord

logger = logging.getLogger(__name__)

Base = declarative_base()


class TushareNews(Base):
    """Tushare 新浪财经新闻表"""

    __tablename__ = "tushare_news"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 新闻基本信息
    title = Column(String(300), nullable=False)
    url = Column(String(1000), nullable=False)
    source = Column(String(100), default="")
    published_date = Column(DateTime, index=True)

    # 关联股票
    code = Column(String(10), nullable=False, index=True, default="MARKET")
    related_stocks = Column(String(500), default="")  # 逗号分隔的股票代码列表

    # 内容摘要
    content_summary = Column(Text, default="")

    # 入库时间
    fetched_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint("url", name="uix_tushare_news_url"),
        Index("ix_tushare_news_code_pub", "code", "published_date"),
        Index("ix_tushare_news_fetched", "fetched_at"),
    )

    def __repr__(self) -> str:
        return f"<TushareNews(code={self.code}, title={self.title[:20]}...)>"


class TushareNewsStorage:
    """
    Tushare 新闻存储管理器

    独立管理 tushare_news 表的 CRUD 操作。
    自动复用主项目的数据库路径（从环境变量或默认路径推断）。
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        初始化存储管理器

        Args:
            db_path: 数据库文件路径（可选，默认从 DATABASE_PATH 环境变量或 ./data/stock_analysis.db）
        """
        if db_path is None:
            db_path = os.getenv("DATABASE_PATH", "./data/stock_analysis.db")

        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        db_url = f"sqlite:///{self._db_path}"
        self._engine = create_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            connect_args={"timeout": 5},
        )
        self._SessionLocal = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
        )

        # 只创建 tushare_news 表，不影响其他表
        self._create_table_if_not_exists()

        logger.info(f"TushareNewsStorage 初始化完成: {db_url}")

    def _create_table_if_not_exists(self) -> None:
        """检查并创建 tushare_news 表（如果不存在）"""
        inspector = inspect(self._engine)
        if not inspector.has_table("tushare_news"):
            Base.metadata.create_all(self._engine, tables=[TushareNews.__table__])
            logger.info("tushare_news 表已创建")

    def _get_session(self) -> Session:
        return self._SessionLocal()

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def save_news(self, records: List[TushareNewsRecord]) -> int:
        """
        批量保存新闻记录

        去重策略：按 URL 唯一约束，重复则更新。

        Returns:
            int: 实际新增/更新的记录数
        """
        if not records:
            return 0

        session = self._get_session()
        saved_count = 0

        try:
            for record in records:
                existing = (
                    session.query(TushareNews)
                    .filter(TushareNews.url == record.url)
                    .first()
                )

                if existing:
                    # 更新已有记录
                    existing.title = record.title or existing.title
                    existing.source = record.source or existing.source
                    existing.published_date = record.published_date or existing.published_date
                    existing.code = record.code or existing.code
                    existing.related_stocks = ",".join(record.related_stocks) if record.related_stocks else existing.related_stocks
                    existing.content_summary = record.content_summary or existing.content_summary
                    existing.fetched_at = datetime.now()
                else:
                    # 新增记录
                    db_record = TushareNews(
                        title=record.title,
                        url=record.url,
                        source=record.source,
                        published_date=record.published_date,
                        code=record.code,
                        related_stocks=",".join(record.related_stocks) if record.related_stocks else "",
                        content_summary=record.content_summary,
                        fetched_at=record.fetched_at,
                    )
                    session.add(db_record)

                saved_count += 1

            session.commit()
            logger.info(f"保存 tushare_news 成功: {saved_count} 条")
            return saved_count

        except Exception as e:
            session.rollback()
            logger.error(f"保存 tushare_news 失败: {e}")
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_news_by_date(
        self,
        date: datetime,
        code: Optional[str] = None,
        limit: int = 100,
    ) -> List[TushareNews]:
        """
        按日期查询新闻

        Args:
            date: 目标日期（只比较日期部分）
            code: 股票代码过滤（可选）
            limit: 最大返回条数
        """
        session = self._get_session()
        try:
            start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)

            query = session.query(TushareNews).filter(
                TushareNews.published_date >= start,
                TushareNews.published_date < end,
            )

            if code:
                query = query.filter(TushareNews.code == code)

            return query.order_by(TushareNews.published_date.desc()).limit(limit).all()
        finally:
            session.close()

    def has_news_for_date(self, date: datetime) -> bool:
        """检查指定日期是否已有新闻数据（幂等检查）"""
        session = self._get_session()
        try:
            start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)

            count = (
                session.query(TushareNews)
                .filter(
                    TushareNews.published_date >= start,
                    TushareNews.published_date < end,
                )
                .count()
            )
            return count > 0
        finally:
            session.close()

    def get_latest_news(
        self,
        code: Optional[str] = None,
        days: int = 7,
        limit: int = 100,
    ) -> List[TushareNews]:
        """
        获取最近的新闻

        Args:
            code: 股票代码过滤（可选）
            days: 最近 N 天
            limit: 最大返回条数
        """
        session = self._get_session()
        try:
            cutoff = datetime.now() - timedelta(days=days)

            query = session.query(TushareNews).filter(
                TushareNews.published_date >= cutoff,
            )

            if code:
                query = query.filter(TushareNews.code == code)

            return query.order_by(TushareNews.published_date.desc()).limit(limit).all()
        finally:
            session.close()

    def count_news(self, days: int = 1) -> int:
        """统计最近 N 天的新闻数量"""
        session = self._get_session()
        try:
            cutoff = datetime.now() - timedelta(days=days)
            return session.query(TushareNews).filter(
                TushareNews.fetched_at >= cutoff,
            ).count()
        finally:
            session.close()

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def cleanup_old_news(self, max_age_days: int = 30) -> int:
        """
        清理超过保留天数的新闻

        Returns:
            int: 删除的记录数
        """
        session = self._get_session()
        try:
            cutoff = datetime.now() - timedelta(days=max_age_days)
            deleted = (
                session.query(TushareNews)
                .filter(TushareNews.fetched_at < cutoff)
                .delete(synchronize_session=False)
            )
            session.commit()
            logger.info(f"清理 tushare_news 旧数据: {deleted} 条")
            return deleted
        except Exception as e:
            session.rollback()
            logger.error(f"清理 tushare_news 旧数据失败: {e}")
            raise
        finally:
            session.close()
