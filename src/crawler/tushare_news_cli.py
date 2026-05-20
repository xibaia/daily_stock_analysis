# -*- coding: utf-8 -*-
"""
===================================
Tushare 新闻爬虫 CLI
===================================

用法：
    python -m src.crawler.tushare_news --setup          # 自动填表登录配置
    python -m src.crawler.tushare_news --check          # 检查登录态
    python -m src.crawler.tushare_news --run            # 执行爬取并保存
    python -m src.crawler.tushare_news --test           # 测试爬取（不保存）
    python -m src.crawler.tushare_news --cleanup        # 清理旧数据
    python -m src.crawler.tushare_news --help           # 显示帮助

环境变量（从 .env 加载）：
    TUSHARE_NEWS_ENABLED       - 功能开关
    TUSHARE_NEWS_USERNAME      - 登录用户名
    TUSHARE_NEWS_PASSWORD      - 登录密码
    TUSHARE_NEWS_STATE_DIR     - 登录态保存目录
    TUSHARE_NEWS_MAX_PAGES     - 最大爬取页数
    TUSHARE_NEWS_MAX_AGE_DAYS  - 数据保留天数
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

from .config import TushareNewsConfig
from .storage import TushareNewsStorage
from .sync import export_news, _default_sync_file
from .tushare_news import TushareNewsScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _load_config() -> TushareNewsConfig:
    """加载配置"""
    return TushareNewsConfig.load()


def cmd_setup(args):
    """自动填表登录配置"""
    config = _load_config()

    print("=" * 60)
    print("Tushare 新闻爬虫 — 首次登录配置")
    print("=" * 60)
    print(f"目标网站: {config.base_url}")
    print(f"新闻页面: {config.data_url}")
    print()

    if not config.username or not config.password:
        print("⚠️  未配置用户名/密码，请在 .env 中设置:")
        print("    TUSHARE_NEWS_USERNAME=你的手机号/邮箱")
        print("    TUSHARE_NEWS_PASSWORD=你的密码")
        print()
        print("将打开浏览器，请完全人工完成登录...")
    else:
        print(f"用户名: {config.username}")
        print("将自动填入用户名和密码，你只需:")
        print("  1. 处理验证码（如有）")
        print("  2. 点击登录按钮")
        print()

    input("按 Enter 键开始...")

    try:
        import cloakbrowser
    except ImportError:
        logger.error("cloakbrowser 未安装，请先执行: pip install cloakbrowser")
        sys.exit(1)

    state_path = config.state_dir / "persistent_context"
    state_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"启动 CloakBrowser headed 模式，登录页: {config.login_url}")

    try:
        context = cloakbrowser.launch_persistent_context(
            str(state_path),
            headless=False,
            humanize=True,
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        # 导航到登录页
        page.goto(config.login_url, wait_until="networkidle", timeout=30000)
        print(f"\n浏览器已打开: {config.login_url}")

        # 自动填表
        if config.username and config.password:
            try:
                # 等待 Vue 渲染
                import time
                time.sleep(2)

                # 填入用户名/手机号
                username_input = page.locator("input[placeholder*='手机号'], input[placeholder*='邮箱']").first
                if username_input.is_visible():
                    username_input.fill(config.username)
                    print(f"✅ 已填入用户名: {config.username}")

                # 填入密码
                password_input = page.locator("input[type='password']").first
                if password_input.is_visible():
                    password_input.fill(config.password)
                    print("✅ 已填入密码")

                # 尝试自动触发按钮可用状态
                page.evaluate("""
                    const inputs = document.querySelectorAll('input');
                    inputs.forEach(i => {
                        i.dispatchEvent(new Event('input', { bubbles: true }));
                        i.dispatchEvent(new Event('change', { bubbles: true }));
                    });
                """)
                time.sleep(1)

                # 检查登录按钮是否可用
                login_btn = page.locator(".login_btn").first
                if login_btn.is_visible():
                    is_disabled = login_btn.is_disabled()
                    if is_disabled:
                        print("⚠️  登录按钮仍被禁用，可能需要手动触发输入事件")
                    else:
                        print("✅ 登录按钮已可用，请点击登录")

            except Exception as e:
                print(f"⚠️  自动填表失败（将完全人工操作）: {e}")
        else:
            print("请在浏览器中手动输入用户名和密码...")

        print("\n请完成登录，然后关闭浏览器窗口...")
        print("登录态将自动保存。")

        # 等待浏览器关闭
        try:
            while True:
                page.wait_for_timeout(1000)
        except Exception:
            pass

        context.close()
        logger.info(f"登录态已保存到: {state_path}")
        print(f"\n✅ 登录态已保存到: {state_path}")
        print(f"   可以复制此目录到服务器用于 headless 运行。")
        return True

    finally:
        pass


def cmd_check(args):
    """检查登录态"""
    config = _load_config()
    state_path = config.state_dir / "persistent_context"
    git_state_path = Path("state/tushare/persistent_context")
    cookie_db = state_path / "Default" / "Cookies"
    git_cookie_db = git_state_path / "Default" / "Cookies"

    found = False

    if cookie_db.exists():
        print(f"✅ 登录态文件存在: {state_path}")
        print(f"   Cookie 数据库: {cookie_db}")
        found = True
    elif git_cookie_db.exists():
        print(f"✅ Git 登录态文件存在: {git_state_path}")
        print(f"   Cookie 数据库: {git_cookie_db}")
        print(f"   服务器运行时将自动复制到: {state_path}")
        found = True

    if found:
        # 尝试验证登录态是否有效
        try:
            scraper = TushareNewsScraper(config)
            if scraper._ensure_browser() and scraper._create_context():
                is_logged_in = scraper._check_login_status()
                if is_logged_in:
                    print("✅ 登录态验证通过")
                else:
                    print("⚠️  登录态可能已过期（页面非登录态）")
                scraper.close()
            else:
                print("⚠️  无法启动浏览器验证")
        except Exception as e:
            print(f"⚠️  验证时出错: {e}")

        sys.exit(0)
    else:
        print(f"❌ 未找到有效登录态")
        print(f"   运行时目录: {state_path}")
        print(f"   Git 同步目录: {git_state_path}")
        print(f"   请执行: python -m src.crawler.tushare_news --setup")
        sys.exit(1)


def cmd_run(args):
    """执行爬取并保存（可选导出同步文件）"""
    config = _load_config()

    if not config.enabled:
        print("⚠️  TUSHARE_NEWS_ENABLED=false，功能未启用")
        print("   在 .env 中设置 TUSHARE_NEWS_ENABLED=true 以启用")
        sys.exit(1)

    print(f"开始爬取 Tushare 新浪财经新闻...")
    print(f"目标: {config.data_url}")
    print(f"最大页数: {config.max_pages}")

    scraper = TushareNewsScraper(config)
    saved = scraper.run()

    if saved > 0:
        print(f"\n✅ 爬取完成，保存 {saved} 条新闻")
    else:
        print(f"\n⚠️  未保存任何新闻（可能已存在或爬取失败）")

    # 导出同步文件（供手动 scp 到服务器）
    if getattr(args, "export", False):
        from pathlib import Path
        import os

        db_path = os.getenv("DATABASE_PATH", "./data/stock_analysis.db")
        output = _default_sync_file()

        print(f"\n📦 正在导出同步文件...")
        count = export_news(db_path, output)

        if count > 0:
            sync_file = Path(output).resolve()
            print(f"✅ 导出完成: {count} 条 -> {sync_file}")
            print(f"\n👉 请手动 scp 到服务器:")
            print(f"   scp {sync_file} user@server:/path/to/data/")
            print(f"   然后在服务器执行: python -m src.crawler.sync import -i /path/to/data/tushare_news_sync.db")
        elif count == 0:
            print("⚠️  无可导出数据")
        else:
            print("❌ 导出失败")

    sys.exit(0 if saved >= 0 else 1)


def cmd_test(args):
    """测试爬取（不保存）"""
    config = _load_config()

    print(f"测试爬取 Tushare 新浪财经新闻（不保存）...")
    print(f"目标: {config.data_url}")

    scraper = TushareNewsScraper(config)
    try:
        records = scraper.crawl()
        print(f"\n爬取结果: {len(records)} 条新闻")

        for i, record in enumerate(records[:10]):
            print(f"\n[{i+1}] {record.title}")
            print(f"    来源: {record.source}")
            print(f"    时间: {record.published_date}")
            print(f"    链接: {record.url}")
            print(f"    关联股票: {record.related_stocks}")
            print(f"    Code: {record.code}")

        if len(records) > 10:
            print(f"\n... 还有 {len(records) - 10} 条")

    finally:
        scraper.close()


def cmd_cleanup(args):
    """清理旧数据"""
    config = _load_config()
    storage = TushareNewsStorage()

    print(f"清理超过 {config.max_age_days} 天的新闻数据...")
    deleted = storage.cleanup_old_news(config.max_age_days)
    print(f"✅ 已清理 {deleted} 条旧数据")


def main():
    parser = argparse.ArgumentParser(
        prog="python -m src.crawler.tushare_news",
        description="Tushare Pro 新浪财经新闻爬虫",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="自动填表登录配置（打开浏览器，人工完成验证码）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="检查已保存的登录态是否有效",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="执行爬取并保存到数据库",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="爬取完成后导出同步文件到固定目录（供手动 scp 到服务器）",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="测试爬取（不保存，只打印结果）",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="清理超过保留天数的新闻数据",
    )

    args = parser.parse_args()

    if args.setup:
        success = cmd_setup(args)
        sys.exit(0 if success else 1)
    elif args.check:
        cmd_check(args)
    elif args.run:
        cmd_run(args)
    elif args.test:
        cmd_test(args)
    elif args.cleanup:
        cmd_cleanup(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
