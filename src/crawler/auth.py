# -*- coding: utf-8 -*-
"""
===================================
爬虫登录认证模块
===================================

使用 CloakBrowser 实现：
1. 首次 setup：headed 浏览器，人工输入验证码，保存 persistent context
2. 日常运行：复用 state 目录，自动恢复登录态
3. 过期检测：请求返回登录页时自动识别并通知

CloakBrowser 特性：
- 源码级 57 个 C++ 补丁，反检测能力强
- humanize=True 模拟真实鼠标轨迹和键盘输入
- launch_persistent_context() 一行恢复登录态
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# State 持久化目录默认路径
DEFAULT_STATE_DIR = "./data/crawler_state"


class CrawlerAuth:
    """
    爬虫登录认证管理器

    负责：
    - 首次登录配置（人工介入输入验证码）
    - 登录态（cookie/localStorage）持久化与复用
    - 登录态过期检测
    """

    def __init__(
        self,
        base_url: str,
        login_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        state_dir: Optional[str] = None,
    ):
        """
        初始化认证管理器

        Args:
            base_url: 目标网站基础地址，如 https://example.com
            login_url: 登录页地址（留空则使用 base_url + /login）
            username: 登录用户名
            password: 登录密码
            state_dir: persistent context 保存目录
        """
        self.base_url = base_url.rstrip("/")
        self.login_url = (login_url or f"{self.base_url}/login").rstrip("/")
        self.username = username or ""
        self.password = password or ""
        self.state_dir = Path(state_dir or DEFAULT_STATE_DIR)

        # 确保 state 目录存在
        self.state_dir.mkdir(parents=True, exist_ok=True)

    @property
    def state_path(self) -> Path:
        """persistent context 目录路径"""
        return self.state_dir / "persistent_context"

    def has_valid_state(self) -> bool:
        """
        检查是否存在有效的 persistent context

        判断依据：state 目录下存在 Cookie 数据库文件
        """
        cookie_db = self.state_path / "Default" / "Cookies"
        return cookie_db.exists()

    def setup_interactive(self) -> bool:
        """
        交互式首次登录配置

        启动 headed 浏览器，由人工输入用户名+密码+验证码完成登录。
        登录成功后自动保存 persistent context。

        Returns:
            bool: 是否成功保存登录态
        """
        try:
            import cloakbrowser
        except ImportError:
            logger.error("cloakbrowser 未安装，请先执行: pip install cloakbrowser")
            return False

        print("=" * 60)
        print("爬虫首次登录配置")
        print("=" * 60)
        print(f"目标网站: {self.base_url}")
        print(f"登录页面: {self.login_url}")
        print()
        print("即将打开浏览器，请人工完成以下步骤：")
        print("  1. 在浏览器中输入用户名和密码")
        print("  2. 输入短信/邮件验证码")
        print("  3. 点击登录按钮")
        print("  4. 登录成功后，关闭浏览器窗口")
        print()
        input("按 Enter 键开始...")

        logger.info(f"启动 CloakBrowser headed 模式，登录页: {self.login_url}")

        # 启动 headed 浏览器，humanize=True 让行为更像真人
        browser = cloakbrowser.launch(
            headless=False,
            humanize=True,
        )

        try:
            # 使用 persistent context，登录后会自动保存
            context = browser.launch_persistent_context(
                str(self.state_path),
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()

            # 导航到登录页
            page.goto(self.login_url, wait_until="networkidle")
            print(f"\n浏览器已打开: {self.login_url}")
            print("请完成登录，然后关闭浏览器窗口...")

            # 等待浏览器关闭（用户手动关闭窗口）
            # 通过检测 context 是否关闭来判断
            try:
                while True:
                    page.wait_for_timeout(1000)
            except Exception:
                # 浏览器被关闭，context 终止
                pass

            context.close()
            logger.info(f"登录态已保存到: {self.state_path}")
            print(f"\n✅ 登录态已保存到: {self.state_path}")
            return True

        finally:
            browser.close()

    def create_context(self, headless: bool = True):
        """
        创建已登录的浏览器上下文

        Args:
            headless: 是否无头模式（日常爬取用 True）

        Returns:
            tuple: (browser, context) 或 (None, None) 如果 state 无效
        """
        try:
            import cloakbrowser
        except ImportError:
            logger.error("cloakbrowser 未安装")
            return None, None

        if not self.has_valid_state():
            logger.warning(
                f"未找到有效登录态: {self.state_path}\n"
                f"请先执行: python -m src.crawler --setup"
            )
            return None, None

        logger.info(f"使用已保存的登录态启动 CloakBrowser (headless={headless})")

        browser = cloakbrowser.launch(
            headless=headless,
            humanize=True,
        )

        context = browser.launch_persistent_context(
            str(self.state_path),
            viewport={"width": 1920, "height": 1080},
        )

        return browser, context

    def check_login_status(self, page) -> bool:
        """
        检查当前页面是否仍处于登录态

        通过检测页面上是否存在登录表单或特定登录态标识来判断。
        目标网站确定后，可根据实际 DOM 结构调整检测逻辑。

        Args:
            page: CloakBrowser page 对象

        Returns:
            bool: 是否已登录
        """
        # TODO: 目标网站确定后，根据实际页面特征实现检测逻辑
        # 示例检测方式（需根据实际网站调整）：
        # 1. 检查 URL 是否被重定向到登录页
        current_url = page.url
        if "/login" in current_url.lower():
            return False

        # 2. 检查页面上是否存在登录表单（通用 fallback）
        login_form = page.locator("form:has(input[type='password'])").first
        if login_form.is_visible():
            return False

        # 3. 检查是否存在用户头像/用户名等登录态标识
        # user_indicator = page.locator(".user-name, .avatar, [data-testid='user-menu']").first
        # return user_indicator.is_visible()

        return True

    def notify_state_expired(self) -> None:
        """登录态过期通知"""
        msg = (
            "爬虫登录态已过期，请重新执行登录配置:\n"
            f"  python -m src.crawler --setup\n"
            f"  或: docker-compose exec analyzer python -m src.crawler --setup"
        )
        logger.error(msg)
        # TODO: 可接入现有通知系统（企业微信/飞书/邮件等）
