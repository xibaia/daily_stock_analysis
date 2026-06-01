#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock_daily 数据批量回填脚本

对 stock_daily 表中已有数据的所有股票，补全最近 N 个交易日的日线数据。

使用方法：
    python3 scripts/backfill_stock_daily.py
    python3 scripts/backfill_stock_daily.py --days 15 --workers 3
    python3 scripts/backfill_stock_daily.py --codes 600519,000001 --days 15
    python3 scripts/backfill_stock_daily.py --dry-run

环境要求：
    - 需要已配置数据源（.env 中的相关 TOKEN）
    - 依赖 requirements.txt 中的全部包

备份机制：
    - 执行前自动复制数据库文件到 data/stock_analysis.db.backup.YYYYMMDD_HHMMSS
    - 如需要回退：cp data/stock_analysis.db.backup.* data/stock_analysis.db
"""

import argparse
import logging
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# 确保项目根目录在路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_provider import DataFetcherManager
from src.config import get_config
from src.storage import get_db

logger = logging.getLogger(__name__)


def backup_database(db_path: Path, db) -> Path:
    """备份数据库文件，返回备份路径。"""
    # 如果是 SQLite，先执行 WAL checkpoint 确保数据完整落盘
    if str(db_path).endswith('.db') or str(db_path).endswith('.sqlite'):
        try:
            with db.get_session() as session:
                session.connection().exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
            logger.debug("WAL checkpoint 完成")
        except Exception as e:
            logger.warning(f"WAL checkpoint 失败（继续备份）: {e}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.name}.backup.{timestamp}"
    shutil.copy2(db_path, backup_path)

    # 同时复制 WAL 和 SHM 文件（如果存在），保证 WAL 模式下的备份一致性
    for suffix in ('-wal', '-shm'):
        wal_path = db_path.parent / f"{db_path.name}{suffix}"
        if wal_path.exists():
            shutil.copy2(wal_path, db_path.parent / f"{backup_path.name}{suffix}")

    logger.info(f"数据库已备份到: {backup_path}")
    return backup_path


def fetch_and_save_single(db, fetcher, code, days):
    """
    获取并保存单只股票数据。

    Returns:
        (code, status, added_count, message)
        status: 'success' | 'failed' | 'skipped'
    """
    try:
        df, source_name = fetcher.get_daily_data(code, days=days)
        if df is None or df.empty:
            return code, 'skipped', 0, '获取数据为空'
        added_count = db.save_daily_data(df, code, source_name)
        return code, 'success', added_count, f'来源: {source_name}'
    except Exception as e:
        logger.warning(f"[{code}] 获取或保存失败: {e}")
        return code, 'failed', 0, str(e)


def main():
    parser = argparse.ArgumentParser(description='批量补全 stock_daily 近 N 日数据')
    parser.add_argument('--days', type=int, default=15, help='拉取天数（默认 15）')
    parser.add_argument('--workers', type=int, default=3, help='并发数（默认 3）')
    parser.add_argument('--dry-run', action='store_true', help='只列出会处理的股票，不实际拉取')
    parser.add_argument('--codes', type=str, help='指定股票代码，逗号分隔（覆盖全部已有股票逻辑）')
    parser.add_argument('--skip-backup', action='store_true', help='跳过数据库备份')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )

    # 获取股票列表
    db = None
    if args.codes:
        codes = [c.strip().upper() for c in args.codes.split(',') if c.strip()]
        logger.info(f"指定处理 {len(codes)} 只股票")
    else:
        # 未指定代码时才初始化数据库，用于读取已有股票代码。
        db = get_db()
        codes = db.get_distinct_codes()
        logger.info(f"从 stock_daily 表发现 {len(codes)} 只已有数据的股票")

    if args.dry_run:
        logger.info("=== Dry-run 模式，仅列出股票代码 ===")
        for code in codes:
            logger.info(f"  {code}")
        logger.info(f"共 {len(codes)} 只，将拉取最近 {args.days} 天数据")
        sys.exit(0)

    # 非 dry-run 才初始化 fetcher 和执行备份，避免预览模式产生外部副作用。
    if db is None:
        db = get_db()
    fetcher = DataFetcherManager()

    # 获取数据库文件路径
    config = get_config()
    db_url = config.get_db_url()
    # db_url 格式: sqlite:///absolute/path
    db_path_str = db_url.replace('sqlite:///', '')
    db_path = Path(db_path_str)

    # 备份
    if not args.skip_backup:
        if not db_path.exists():
            logger.error(f"数据库文件不存在: {db_path}")
            sys.exit(1)
        backup_path = backup_database(db_path, db)
    else:
        backup_path = None
        logger.info("已跳过备份")

    # 并发拉取
    start_time = time.time()
    success_count = 0
    failed_count = 0
    skipped_count = 0
    total_added = 0

    logger.info(f"开始批量回填，共 {len(codes)} 只股票，workers={args.workers}，days={args.days}")

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_code = {
            executor.submit(fetch_and_save_single, db, fetcher, code, args.days): code
            for code in codes
        }
        for future in as_completed(future_to_code):
            code, status, added_count, message = future.result()
            if status == 'success':
                success_count += 1
                total_added += added_count
                logger.info(f"[{code}] 成功 - {message}，新增 {added_count} 条")
            elif status == 'skipped':
                skipped_count += 1
                logger.warning(f"[{code}] 跳过 - {message}")
            else:
                failed_count += 1
                logger.error(f"[{code}] 失败 - {message}")

    elapsed = time.time() - start_time

    logger.info("=" * 50)
    logger.info("批量回填完成")
    logger.info(f"  总股票数: {len(codes)}")
    logger.info(f"  成功: {success_count}")
    logger.info(f"  跳过: {skipped_count}")
    logger.info(f"  失败: {failed_count}")
    logger.info(f"  总新增条数: {total_added}")
    logger.info(f"  耗时: {elapsed:.1f} 秒")

    if backup_path:
        logger.info("=" * 50)
        logger.info("回退命令（如需要）:")
        logger.info(f"  cp {backup_path} {db_path}")
        # 如有 WAL/SHM 文件也打印
        for suffix in ('-wal', '-shm'):
            wal_backup = db_path.parent / f"{backup_path.name}{suffix}"
            wal_orig = db_path.parent / f"{db_path.name}{suffix}"
            if wal_backup.exists():
                logger.info(f"  cp {wal_backup} {wal_orig}")

    if failed_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
