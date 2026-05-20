# -*- coding: utf-8 -*-
"""
===================================
Tushare 新闻数据同步模块
===================================

职责：
1. 本机导出：将 tushare_news 表导出为精简 SQLite 文件
2. 服务器导入：将导出的 SQLite ATTACH 到主库，按 URL 去重合并

用法（本机导出）:
    python -m src.crawler.sync export [--db PATH] [--since YYYY-MM-DD] [--output PATH]

用法（服务器导入合并）:
    python -m src.crawler.sync import --input PATH [--db PATH]
"""

import argparse
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, inspect, text

from .storage import Base, TushareNews

logger = logging.getLogger(__name__)

DEFAULT_SYNC_FILE = "data/tushare_news_sync.db"


def _get_engine(db_path: str):
    """创建 SQLAlchemy engine"""
    db_url = f"sqlite:///{db_path}"
    return create_engine(
        db_url,
        echo=False,
        connect_args={"timeout": 5},
    )


def export_news(
    source_db: str,
    output_path: str,
    since: Optional[datetime] = None,
    days: Optional[int] = None,
) -> int:
    """
    从源数据库导出 tushare_news 表到独立的 SQLite 文件。

    Args:
        source_db: 源数据库路径（本机）
        output_path: 输出同步文件路径
        since: 只导出发布时间 >= 此日期的记录
        days: 只导出最近 N 天的记录（与 since 互斥，优先 since）

    Returns:
        int: 导出的记录数
    """
    source_path = Path(source_db)
    if not source_path.exists():
        logger.error(f"源数据库不存在: {source_db}")
        return -1

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 如果输出文件已存在，先删除（确保干净）
    if out.exists():
        out.unlink()

    source_engine = _get_engine(str(source_path))
    output_engine = _get_engine(str(out))

    # 检查源库是否有 tushare_news 表
    inspector = inspect(source_engine)
    if not inspector.has_table("tushare_news"):
        logger.warning(f"源数据库没有 tushare_news 表: {source_db}")
        return 0

    # 在输出库创建表结构
    Base.metadata.create_all(output_engine, tables=[TushareNews.__table__])

    # 构建查询条件
    where_clause = ""
    params = {}
    if since:
        where_clause = "WHERE published_date >= :since"
        params["since"] = since
    elif days:
        since = datetime.now() - timedelta(days=days)
        where_clause = "WHERE published_date >= :since"
        params["since"] = since

    # 跨库复制数据（显式列，排除 id，避免主键冲突）
    columns = [
        "title", "url", "source", "published_date",
        "code", "related_stocks", "content_summary", "fetched_at",
    ]
    col_str = ", ".join(columns)

    with source_engine.connect() as src_conn:
        # 先统计
        count_sql = text(f"SELECT COUNT(*) FROM tushare_news {where_clause}")
        total = src_conn.execute(count_sql, params).scalar()
        logger.info(f"源库共 {total} 条记录待导出")

        # 分批读取并写入
        batch_size = 500
        exported = 0
        offset = 0

        with output_engine.connect() as dst_conn:
            while True:
                sql = text(
                    f"SELECT {col_str} FROM tushare_news {where_clause} "
                    f"ORDER BY id LIMIT {batch_size} OFFSET {offset}"
                )
                rows = src_conn.execute(sql, params).fetchall()
                if not rows:
                    break

                insert_sql = text(
                    f"INSERT INTO tushare_news ({col_str}) VALUES "
                    f"({', '.join([':' + c for c in columns])})"
                )
                for row in rows:
                    row_dict = dict(row._mapping)
                    dst_conn.execute(insert_sql, row_dict)

                exported += len(rows)
                offset += batch_size
                logger.debug(f"已导出 {exported}/{total} 条")

            dst_conn.commit()

    logger.info(f"导出完成: {exported} 条 -> {out}")
    return exported


def import_news(
    sync_db: str,
    target_db: str,
):
    """
    将同步文件中的 tushare_news 数据合并到目标数据库。

    合并策略：
    - URL 不存在于目标库 -> INSERT
    - URL 存在但 sync.fetched_at 更新 -> UPDATE（覆盖）
    - URL 存在且 sync.fetched_at 更旧或相同 -> SKIP

    Args:
        sync_db: 同步文件路径（从本机传过来的精简 SQLite）
        target_db: 目标数据库路径（服务器主库）

    Returns:
        tuple: (inserted, updated, skipped) 或 None（表示错误）
    """
    sync_path = Path(sync_db)
    target_path = Path(target_db)

    if not sync_path.exists():
        logger.error(f"同步文件不存在: {sync_db}")
        return None

    if not target_path.exists():
        logger.error(f"目标数据库不存在: {target_db}")
        return None

    # 检查同步文件有效性
    sync_engine = _get_engine(str(sync_path))
    inspector = inspect(sync_engine)
    if not inspector.has_table("tushare_news"):
        logger.error(f"同步文件没有 tushare_news 表: {sync_db}")
        return -1

    # 确保目标库有表
    target_engine = _get_engine(str(target_path))
    target_inspector = inspect(target_engine)
    if not target_inspector.has_table("tushare_news"):
        Base.metadata.create_all(target_engine, tables=[TushareNews.__table__])
        logger.info("目标库 tushare_news 表已创建")

    columns = [
        "title", "url", "source", "published_date",
        "code", "related_stocks", "content_summary", "fetched_at",
    ]
    col_str = ", ".join(columns)
    placeholders = ", ".join(["?"] * len(columns))
    set_clause = ", ".join([f"{c} = ?" for c in columns])

    # 使用原生 sqlite3
    target_conn = sqlite3.connect(str(target_path))
    sync_conn = sqlite3.connect(str(sync_path))

    # 预加载目标库的 (url, fetched_at) 映射
    target_map = {
        row[0]: row[1]
        for row in target_conn.execute("SELECT url, fetched_at FROM tushare_news")
    }

    total_in_sync = sync_conn.execute(
        "SELECT COUNT(*) FROM tushare_news"
    ).fetchone()[0]
    logger.info(f"同步文件共 {total_in_sync} 条记录")

    inserted = 0
    updated = 0
    skipped = 0

    for row in sync_conn.execute(f"SELECT {col_str} FROM tushare_news"):
        row_dict = dict(zip(columns, row))
        url = row_dict["url"]
        sync_fetched = row_dict["fetched_at"]

        try:
            if url not in target_map:
                # 新记录，直接插入
                target_conn.execute(
                    f"INSERT INTO tushare_news ({col_str}) VALUES ({placeholders})",
                    tuple(row),
                )
                inserted += 1
            elif sync_fetched and sync_fetched > target_map[url]:
                # 同步数据更新，执行 UPDATE
                target_conn.execute(
                    f"UPDATE tushare_news SET {set_clause} WHERE url = ?",
                    tuple(row) + (url,),
                )
                updated += 1
            else:
                # 同步数据更旧或相同，跳过
                skipped += 1
        except sqlite3.Error as e:
            logger.debug(f"处理 {url} 时出错: {e}")
            skipped += 1

    target_conn.commit()
    target_conn.close()
    sync_conn.close()

    logger.info(f"合并完成: 新增 {inserted} 条, 更新 {updated} 条, 跳过 {skipped} 条")
    return inserted, updated, skipped


def _resolve_db_path(args_db: Optional[str]) -> str:
    """解析数据库路径"""
    if args_db:
        return args_db
    return os.getenv("DATABASE_PATH", "./data/stock_analysis.db")


def cmd_export(args):
    """执行导出"""
    source_db = _resolve_db_path(args.db)
    output = args.output or DEFAULT_SYNC_FILE

    since = None
    if args.since:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            logger.error(f"--since 格式错误，应为 YYYY-MM-DD: {args.since}")
            sys.exit(1)

    logger.info(f"导出 tushare_news: {source_db} -> {output}")
    count = export_news(source_db, output, since=since, days=args.days)

    if count < 0:
        sys.exit(1)

    print(f"\n导出完成: {count} 条新闻")
    print(f"同步文件: {Path(output).resolve()}")
    print(f"\n下一步：将此文件上传到服务器，例如:")
    print(f"  scp {output} user@server:/path/to/data/")


def cmd_import(args):
    """执行导入合并"""
    if not args.input:
        logger.error("--input 参数必填")
        sys.exit(1)

    target_db = _resolve_db_path(args.db)
    sync_db = args.input

    logger.info(f"导入合并: {sync_db} -> {target_db}")
    result = import_news(sync_db, target_db)

    if result is None:
        sys.exit(1)

    inserted, updated, skipped = result
    print(f"\n合并完成: 新增 {inserted} 条, 更新 {updated} 条, 跳过 {skipped} 条")


def main():
    parser = argparse.ArgumentParser(
        prog="python -m src.crawler.sync",
        description="Tushare 新闻数据同步工具（本机导出 -> 服务器导入合并）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # export 子命令
    export_parser = subparsers.add_parser(
        "export",
        help="从本机数据库导出 tushare_news 数据为同步文件",
    )
    export_parser.add_argument(
        "--db",
        help="源数据库路径（默认从 DATABASE_PATH 环境变量或 ./data/stock_analysis.db）",
    )
    export_parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="只导出发布日期 >= 此日期的记录",
    )
    export_parser.add_argument(
        "--days",
        type=int,
        metavar="N",
        help="只导出最近 N 天的记录",
    )
    export_parser.add_argument(
        "--output",
        "-o",
        help=f"输出文件路径（默认: {DEFAULT_SYNC_FILE}）",
    )
    export_parser.set_defaults(func=cmd_export)

    # import 子命令
    import_parser = subparsers.add_parser(
        "import",
        help="将同步文件合并到服务器数据库（在服务器上执行）",
    )
    import_parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="同步文件路径（从本机传过来的 .db 文件）",
    )
    import_parser.add_argument(
        "--db",
        help="目标数据库路径（默认从 DATABASE_PATH 环境变量或 ./data/stock_analysis.db）",
    )
    import_parser.set_defaults(func=cmd_import)

    # status 子命令（查看数据库状态）
    status_parser = subparsers.add_parser(
        "status",
        help="查看数据库中的新闻数据概览",
    )
    status_parser.add_argument(
        "--db",
        help="数据库路径",
    )
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    args.func(args)


def cmd_status(args):
    """查看数据库状态"""
    db_path = _resolve_db_path(args.db)
    path = Path(db_path)

    if not path.exists():
        print(f"数据库不存在: {db_path}")
        sys.exit(1)

    engine = _get_engine(str(path))
    inspector = inspect(engine)

    if not inspector.has_table("tushare_news"):
        print(f"数据库中没有 tushare_news 表: {db_path}")
        sys.exit(1)

    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM tushare_news")).scalar()

        # 最近 7 天
        week_ago = datetime.now() - timedelta(days=7)
        week_count = conn.execute(
            text("SELECT COUNT(*) FROM tushare_news WHERE published_date >= :since"),
            {"since": week_ago},
        ).scalar()

        # 今天
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = conn.execute(
            text("SELECT COUNT(*) FROM tushare_news WHERE published_date >= :since"),
            {"since": today},
        ).scalar()

        # 日期范围
        date_range = conn.execute(
            text(
                "SELECT MIN(published_date) as earliest, MAX(published_date) as latest "
                "FROM tushare_news WHERE published_date IS NOT NULL"
            )
        ).fetchone()

    print(f"数据库: {path.resolve()}")
    print(f"总记录数: {total}")
    print(f"最近 7 天: {week_count}")
    print(f"今天: {today_count}")
    if date_range.earliest:
        print(f"时间范围: {date_range.earliest} ~ {date_range.latest}")


if __name__ == "__main__":
    main()
