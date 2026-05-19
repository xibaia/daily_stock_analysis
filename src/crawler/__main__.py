# -*- coding: utf-8 -*-
"""
===================================
爬虫 CLI 工具
===================================

用法：
    python -m src.crawler --setup          # 交互式登录配置
    python -m src.crawler --check          # 检查登录态是否有效
    python -m src.crawler --test-crawl     # 测试爬取（需先 setup）
    python -m src.crawler --help           # 显示帮助

环境变量（从 .env 加载）：
    CRAWLER_BASE_URL       - 目标网站地址
    CRAWLER_LOGIN_URL      - 登录页地址（可选）
    CRAWLER_USERNAME       - 用户名（可选）
    CRAWLER_PASSWORD       - 密码（可选）
    CRAWLER_DATA_URL       - 数据页地址
    CRAWLER_STATE_DIR      - state 保存目录（可选）
"""

import argparse
import logging
import sys
from pathlib import Path

# 加载项目根目录的环境变量
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass

from src.crawler.auth import CrawlerAuth, DEFAULT_STATE_DIR
from src.crawler.scraper import WebScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _load_auth_from_env() -> CrawlerAuth:
    """从环境变量创建 CrawlerAuth 实例"""
    import os

    base_url = os.getenv("CRAWLER_BASE_URL", "").strip()
    if not base_url:
        print("错误: 未配置 CRAWLER_BASE_URL，请在 .env 中设置目标网站地址")
        sys.exit(1)

    return CrawlerAuth(
        base_url=base_url,
        login_url=os.getenv("CRAWLER_LOGIN_URL") or None,
        username=os.getenv("CRAWLER_USERNAME") or None,
        password=os.getenv("CRAWLER_PASSWORD") or None,
        state_dir=os.getenv("CRAWLER_STATE_DIR") or DEFAULT_STATE_DIR,
    )


def cmd_setup(args):
    """交互式登录配置"""
    auth = _load_auth_from_env()
    success = auth.setup_interactive()
    sys.exit(0 if success else 1)


def cmd_check(args):
    """检查登录态"""
    auth = _load_auth_from_env()

    if auth.has_valid_state():
        print(f"✅ 登录态有效: {auth.state_path}")
        sys.exit(0)
    else:
        print(f"❌ 未找到有效登录态: {auth.state_path}")
        print(f"   请执行: python -m src.crawler --setup")
        sys.exit(1)


def cmd_test_crawl(args):
    """测试爬取"""
    import os

    auth = _load_auth_from_env()
    data_url = os.getenv("CRAWLER_DATA_URL", "").strip()

    if not auth.has_valid_state():
        print("❌ 登录态无效，请先执行 setup")
        sys.exit(1)

    if not data_url:
        print("错误: 未配置 CRAWLER_DATA_URL")
        sys.exit(1)

    scraper = WebScraper(
        auth=auth,
        data_url=data_url,
        request_interval=float(os.getenv("CRAWLER_REQUEST_INTERVAL", "2.0")),
        max_retries=int(os.getenv("CRAWLER_MAX_RETRIES", "3")),
    )

    try:
        batch = scraper.crawl_all_pages()
        print(f"\n爬取结果: {len(batch)} 条记录")
        if not batch.is_empty():
            df = batch.to_dataframe()
            print(df.head())
        else:
            print("(数据为空 - _parse_data 为占位实现，需等目标网站确定后实现)")
    finally:
        scraper.close()


def main():
    parser = argparse.ArgumentParser(
        prog="python -m src.crawler",
        description="Web 登录爬虫管理工具",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="交互式首次登录配置（打开浏览器，人工输入验证码）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="检查已保存的登录态是否有效",
    )
    parser.add_argument(
        "--test-crawl",
        action="store_true",
        help="测试爬取（需先完成 setup）",
    )

    args = parser.parse_args()

    if args.setup:
        cmd_setup(args)
    elif args.check:
        cmd_check(args)
    elif args.test_crawl:
        cmd_test_crawl(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
