#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tushare 本地登录 Setup 脚本（最小化独立版）
===============================================

在本地有 GUI 的电脑上运行此脚本，自动填表后人工完成验证码，登录态保存后
上传服务器即可长期使用。

依赖安装：
    pip install cloakbrowser playwright

用法：
    python tushare_local_setup.py
    python tushare_local_setup.py --username 你的手机号 --password 你的密码
    python tushare_local_setup.py --output ~/Desktop/tushare_state.zip

步骤：
    1. 运行脚本，浏览器自动打开
    2. 人工处理验证码并点击登录
    3. 登录成功后，在终端按 Enter 确认
    4. 脚本打包登录态为 zip，上传到服务器对应目录即可
"""

import argparse
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path


TUSHARE_LOGIN_URL = "https://tushare.pro/weborder/#/login"
TUSHARE_NEWS_URL = "https://tushare.pro/news/sina"


def main():
    parser = argparse.ArgumentParser(description="Tushare 本地登录 Setup")
    parser.add_argument("--username", default=os.environ.get("TUSHARE_USERNAME", ""), help="手机号/邮箱")
    parser.add_argument("--password", default=os.environ.get("TUSHARE_PASSWORD", ""), help="密码")
    parser.add_argument("--output", default="tushare_news_state.zip", help="输出 zip 路径")
    parser.add_argument("--state-dir", default="./state/tushare", help="状态目录（默认 git 追踪目录）")
    args = parser.parse_args()

    try:
        import cloakbrowser
    except ImportError:
        print("ERROR: cloakbrowser 未安装。请执行：")
        print("    pip install cloakbrowser playwright")
        sys.exit(1)

    state_path = Path(args.state_dir) / "persistent_context"
    state_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Tushare 本地登录 Setup")
    print("=" * 60)
    print(f"用户名: {args.username}")
    print(f"状态保存目录: {state_path}")
    print()
    print("即将打开浏览器，请按以下步骤操作：")
    print("  1. 浏览器自动填入用户名和密码")
    print("  2. 人工处理验证码（如有）")
    print("  3. 点击登录按钮")
    print("  4. 确保成功进入 tushare 页面")
    print("  5. 回到终端按 Enter 保存登录态")
    print()
    input("按 Enter 键开始...")

    print("\n正在启动 CloakBrowser (headed 模式)...")

    try:
        context = cloakbrowser.launch_persistent_context(
            str(state_path),
            headless=False,
            humanize=True,
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        print(f"正在打开登录页: {TUSHARE_LOGIN_URL}")
        page.goto(TUSHARE_LOGIN_URL, wait_until="networkidle", timeout=30000)

        # 等待 Vue 渲染
        time.sleep(2)

        # 自动填表
        filled = False
        try:
            # 尝试密码登录 tab
            password_tab = page.locator("text=密码登录").first
            if password_tab.is_visible():
                password_tab.click()
                time.sleep(0.5)

            username_input = page.locator("input[placeholder*='手机号'], input[placeholder*='邮箱']").first
            if username_input.is_visible():
                username_input.fill(args.username)
                print(f"✅ 已填入用户名: {args.username}")
                filled = True

            password_input = page.locator("input[type='password']").first
            if password_input.is_visible():
                password_input.fill(args.password)
                print("✅ 已填入密码")
                filled = True

            # 触发 input 事件使登录按钮可用
            page.evaluate("""
                const inputs = document.querySelectorAll('input');
                inputs.forEach(i => {
                    i.dispatchEvent(new Event('input', { bubbles: true }));
                    i.dispatchEvent(new Event('change', { bubbles: true }));
                });
            """)
            time.sleep(0.5)

            login_btn = page.locator(".login_btn").first
            if login_btn.is_visible() and not login_btn.is_disabled():
                print("✅ 登录按钮已可用，请【在浏览器中】点击登录")
            elif login_btn.is_visible():
                print("⚠️  登录按钮仍被禁用，可能需要手动在输入框中再敲一下")
            else:
                print("⚠️  未找到登录按钮，请完全人工操作")

        except Exception as e:
            print(f"⚠️  自动填表失败: {e}")
            print("   请完全人工在浏览器中完成登录")

        if not filled:
            print("\n⚠️  自动填表未生效，请完全人工操作")

        print("\n" + "=" * 60)
        print("请在浏览器中完成登录，成功后回到这里按 Enter...")
        print("=" * 60)
        input()

        # 再访问一次新闻页确认登录态
        print("\n正在验证登录态（访问新闻页）...")
        try:
            page.goto(TUSHARE_NEWS_URL, wait_until="networkidle", timeout=15000)
            time.sleep(2)
            current_url = page.url
            if "/login" in current_url:
                print("⚠️  当前 URL 仍包含 /login，可能未登录成功")
                print(f"   当前 URL: {current_url}")
                confirm = input("是否仍要保存登录态？ (y/N): ")
                if confirm.lower() != "y":
                    print("已取消，请重新运行脚本")
                    return
            else:
                print(f"✅ 当前 URL: {current_url}")
                print("   看起来已登录成功")
        except Exception as e:
            print(f"⚠️  验证访问出错: {e}")

        context.close()
        print(f"\n✅ 登录态已保存到: {state_path}")

        # 打包为 zip
        output_path = Path(args.output)
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "state.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in state_path.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(state_path.parent)
                        zf.write(file_path, arcname)

            shutil.copy(zip_path, output_path)

        print(f"✅ 登录态已打包: {output_path.absolute()}")
        print()
        print("下一步：")
        print(f"  1. 将 {output_path.name} 上传到服务器")
        print(f"  2. 在服务器项目根目录解压：")
        print(f"       unzip -o {output_path.name}")
        print(f"  3. 确认服务器目录结构：")
        print(f"       ./data/tushare_news_state/persistent_context/")
        print(f"  4. 运行检查：python -m src.crawler.tushare_news --check")

    finally:
        try:
            context.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
