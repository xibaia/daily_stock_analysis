# -*- coding: utf-8 -*-
"""
===================================
Tushare 新浪财经新闻爬虫
===================================

基于 CloakBrowser 实现：
1. 自动填表登录（手机号/邮箱 + 密码）
2. API 拦截优先提取新闻数据
3. DOM 解析兜底
4. 分页爬取所有新闻

目标页面: https://tushare.pro/news/sina
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from urllib.parse import urljoin

from .auth import CrawlerAuth
from .config import TushareNewsConfig
from .models import TushareNewsRecord
from .storage import TushareNewsStorage

logger = logging.getLogger(__name__)


class TushareNewsScraper:
    """
    Tushare 新浪财经新闻爬虫

    特性：
    - 自动填表登录（减少人工操作）
    - API 拦截优先提取 JSON 数据
    - DOM 解析兜底
    - 分页爬取
    - 请求间隔控制
    """

    def __init__(self, config: Optional[TushareNewsConfig] = None):
        self.config = config or TushareNewsConfig.load()
        self.storage = TushareNewsStorage()

        # 运行时状态
        self._browser = None
        self._context = None
        self._page = None
        self._intercepted_data: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 浏览器生命周期
    # ------------------------------------------------------------------

    def _ensure_browser(self) -> bool:
        """确保浏览器已启动"""
        if self._browser is not None:
            return True

        try:
            import cloakbrowser
        except ImportError:
            logger.error("cloakbrowser 未安装")
            return False

        logger.info(f"启动 CloakBrowser (headless={True})")
        self._browser = cloakbrowser.launch(
            headless=True,
            humanize=True,
        )
        return True

    def _create_context(self) -> bool:
        """创建 persistent context（复用登录态）"""
        if self._context is not None:
            return True

        state_path = self.config.state_dir / "persistent_context"

        if not state_path.exists():
            # 尝试从 git 追踪的 state/tushare/ 复制登录态
            git_state_path = Path("state/tushare/persistent_context")
            if git_state_path.exists():
                import shutil
                state_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(git_state_path, state_path)
                logger.info(f"已从 git state 复制登录态: {git_state_path} -> {state_path}")
            else:
                logger.error(
                    f"未找到登录态: {state_path}\n"
                    f"也未找到 git state: {git_state_path}\n"
                    f"请先执行: python -m src.crawler.tushare_news --setup"
                )
                return False

        try:
            self._context = self._browser.launch_persistent_context(
                str(state_path),
                viewport={"width": 1920, "height": 1080},
            )
            self._page = self._context.new_page()
            return True
        except Exception as e:
            logger.error(f"创建 context 失败: {e}")
            return False

    def _setup_api_interception(self) -> None:
        """设置 API 拦截，捕获新闻数据"""
        self._intercepted_data = []

        def handle_response(response):
            url = response.url
            # 拦截新闻相关 API
            if "/wctapi/" in url and ("news" in url or "sina" in url):
                try:
                    body = response.body()
                    if body:
                        data = json.loads(body.decode("utf-8", errors="ignore"))
                        self._intercepted_data.append({
                            "url": url,
                            "data": data,
                        })
                        logger.debug(f"拦截 API 响应: {url}")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

        self._page.on("response", handle_response)

    # ------------------------------------------------------------------
    # 登录检测
    # ------------------------------------------------------------------

    def _is_login_page(self) -> bool:
        """检测当前页面是否为登录页"""
        try:
            current_url = self._page.url
            if "/login" in current_url.lower():
                return True

            # 检测登录表单
            login_inputs = self._page.locator("input[placeholder*='手机号'], input[placeholder*='邮箱']").count()
            password_input = self._page.locator("input[type='password']").count()

            return login_inputs > 0 and password_input > 0
        except Exception:
            return False

    def _check_login_status(self) -> bool:
        """检查是否处于登录态"""
        if self._is_login_page():
            return False

        try:
            # 检测页面上是否有用户相关元素（登录态标识）
            # 尝试访问个人信息 API
            response = self._page.evaluate("""
                async () => {
                    try {
                        const res = await fetch('/wctapi/user_center/info');
                        return res.ok;
                    } catch {
                        return false;
                    }
                }
            """)
            return bool(response)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 核心爬取逻辑
    # ------------------------------------------------------------------

    def crawl(self) -> List[TushareNewsRecord]:
        """
        爬取 tushare.pro/news/sina 的所有新闻

        Returns:
            List[TushareNewsRecord]: 爬取到的新闻记录
        """
        if not self._ensure_browser():
            logger.error("浏览器启动失败")
            return []

        if not self._create_context():
            logger.error("登录态无效，请先执行 setup")
            return []

        all_records: List[TushareNewsRecord] = []

        for attempt in range(1, self.config.max_retries + 1):
            try:
                logger.info(f"开始爬取新闻 (尝试 {attempt}/{self.config.max_retries})")

                # 设置 API 拦截
                self._setup_api_interception()

                # 导航到新闻页
                self._page.goto(
                    self.config.data_url,
                    wait_until="networkidle",
                    timeout=30000,
                )

                # 等待 Vue 渲染
                time.sleep(3)

                # 检查是否被踢到登录页
                if self._is_login_page():
                    logger.error("登录态已过期，被重定向到登录页")
                    return []

                # 等待更多数据加载（滚动或分页）
                records = self._crawl_all_pages()
                all_records.extend(records)

                logger.info(f"爬取完成: {len(all_records)} 条新闻")
                break

            except Exception as e:
                logger.warning(f"爬取失败 (尝试 {attempt}/{self.config.max_retries}): {e}")
                if attempt == self.config.max_retries:
                    self._save_snapshot("crawl_error")
                    logger.error("爬取最终失败")
                    return []
                time.sleep(self.config.request_interval)

        return all_records

    def _crawl_all_pages(self) -> List[TushareNewsRecord]:
        """爬取所有分页数据"""
        all_records: List[TushareNewsRecord] = []

        for page_num in range(1, self.config.max_pages + 1):
            logger.info(f"爬取第 {page_num} 页...")

            # 尝试从拦截的 API 数据中提取
            records = self._extract_from_api_interception()
            if records:
                all_records.extend(records)
                logger.info(f"第 {page_num} 页: API 拦截提取 {len(records)} 条")

            # 尝试 DOM 解析兜底
            if not records:
                records = self._extract_from_dom()
                if records:
                    all_records.extend(records)
                    logger.info(f"第 {page_num} 页: DOM 解析提取 {len(records)} 条")

            # 尝试触发下一页
            has_more = self._goto_next_page()
            if not has_more:
                logger.info("没有更多页面")
                break

            time.sleep(self.config.request_interval)

        # 去重
        seen_urls = set()
        unique_records = []
        for r in all_records:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                unique_records.append(r)

        return unique_records

    # ------------------------------------------------------------------
    # 数据提取：API 拦截
    # ------------------------------------------------------------------

    def _extract_from_api_interception(self) -> List[TushareNewsRecord]:
        """从拦截的 API 响应中提取新闻数据"""
        records: List[TushareNewsRecord] = []

        for item in self._intercepted_data:
            data = item.get("data", {})

            # 尝试多种可能的响应结构
            news_list = self._parse_news_api_response(data)
            for news in news_list:
                record = self._normalize_news_item(news)
                if record:
                    records.append(record)

        return records

    def _parse_news_api_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        解析新闻 API 响应，尝试多种常见结构

        可能的结构：
        - {"data": {"list": [...]}}
        - {"data": {"items": [...]}}
        - {"data": [...]}
        - {"result": [...]}
        - [...] (直接数组)
        """
        if not isinstance(data, dict):
            return []

        # 尝试嵌套结构
        for key in ["data", "result", "items", "list", "records", "rows"]:
            if key in data:
                val = data[key]
                if isinstance(val, list):
                    return val
                elif isinstance(val, dict):
                    # 再嵌套一层
                    for sub_key in ["list", "items", "records", "rows", "data"]:
                        if sub_key in val and isinstance(val[sub_key], list):
                            return val[sub_key]

        # 如果 data 本身包含 list/items 键且值是列表
        for key in ["list", "items", "records"]:
            if key in data and isinstance(data[key], list):
                return data[key]

        return []

    def _normalize_news_item(self, item: Dict[str, Any]) -> Optional[TushareNewsRecord]:
        """将 API/DOM 中的原始数据标准化为 TushareNewsRecord"""
        if not isinstance(item, dict):
            return None

        # 尝试提取标题
        title = self._extract_field(item, [
            "title", "news_title", "headline", "subject", "name", "text"
        ])
        if not title:
            return None

        # 尝试提取 URL
        url = self._extract_field(item, [
            "url", "link", "href", "news_url", "detail_url", "source_url"
        ])
        if url and not url.startswith(("http://", "https://")):
            url = urljoin(self.config.base_url, url)

        # 尝试提取来源
        source = self._extract_field(item, [
            "source", "news_source", "media", "publisher", "site", "from"
        ]) or "新浪财经"

        # 尝试提取发布时间
        pub_date = self._extract_datetime(item, [
            "published_date", "pub_date", "publish_time", "time", "datetime",
            "date", "created_at", "updated_at", "ts", "timestamp"
        ])

        # 尝试提取关联股票
        related_stocks = self._extract_related_stocks(item)

        # 尝试提取摘要
        summary = self._extract_field(item, [
            "summary", "abstract", "description", "content", "snippet", "brief"
        ]) or ""

        # 确定主 code
        code = related_stocks[0] if related_stocks else "MARKET"

        return TushareNewsRecord(
            title=str(title).strip(),
            url=str(url).strip() if url else "",
            source=str(source).strip(),
            published_date=pub_date,
            related_stocks=related_stocks,
            code=code,
            content_summary=str(summary).strip()[:500],
        )

    def _extract_field(self, item: Dict[str, Any], keys: List[str]) -> Optional[str]:
        """从字典中提取第一个存在的字段值"""
        for key in keys:
            if key in item and item[key] is not None:
                val = item[key]
                if isinstance(val, str) and val.strip():
                    return val.strip()
                elif not isinstance(val, (dict, list)):
                    return str(val)
        return None

    def _extract_datetime(self, item: Dict[str, Any], keys: List[str]) -> Optional[datetime]:
        """从字典中提取并解析日期时间"""
        raw = self._extract_field(item, keys)
        if not raw:
            return None

        # 尝试多种格式
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d",
            "%d/%m/%Y %H:%M:%S",
            "%m-%d %H:%M",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue

        # 尝试 ISO 格式
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass

        # 尝试时间戳
        try:
            ts = float(raw)
            if ts > 1e12:  # 毫秒时间戳
                ts = ts / 1000
            return datetime.fromtimestamp(ts)
        except (ValueError, OSError, OverflowError):
            pass

        return None

    def _extract_related_stocks(self, item: Dict[str, Any]) -> List[str]:
        """提取关联股票代码"""
        related = []

        # 常见字段名
        for key in ["stocks", "stock_codes", "related_stocks", "symbols", "codes"]:
            if key in item:
                val = item[key]
                if isinstance(val, list):
                    for s in val:
                        if isinstance(s, str):
                            related.append(s.strip().upper())
                elif isinstance(val, str):
                    # 逗号或空格分隔
                    for s in re.split(r"[,;\s]+", val):
                        s = s.strip().upper()
                        if s:
                            related.append(s)

        # 从标题中提取股票代码（A股格式：6位数字）
        title = self._extract_field(item, ["title", "news_title", "headline"]) or ""
        codes_in_title = re.findall(r"\b(\d{6})\b", title)
        related.extend([c for c in codes_in_title if c not in related])

        # 去重
        return list(dict.fromkeys(related))

    # ------------------------------------------------------------------
    # 数据提取：DOM 解析兜底
    # ------------------------------------------------------------------

    def _extract_from_dom(self) -> List[TushareNewsRecord]:
        """从页面 DOM 中提取新闻数据（API 拦截失败时的兜底方案）"""
        records: List[TushareNewsRecord] = []

        try:
            # 尝试多种常见的新闻列表选择器
            selectors = [
                # Element UI 表格
                ".el-table__row",
                # 常见新闻列表
                ".news-item", ".news-list-item", ".article-item",
                ".news-card", ".info-item", ".list-item",
                # 更通用的
                "[class*='news']", "[class*='article']",
            ]

            for selector in selectors:
                elements = self._page.locator(selector).all()
                if elements:
                    logger.debug(f"DOM 解析找到 {len(elements)} 个元素 (selector: {selector})")
                    for el in elements:
                        record = self._parse_dom_element(el)
                        if record:
                            records.append(record)
                    break

        except Exception as e:
            logger.warning(f"DOM 解析失败: {e}")

        return records

    def _parse_dom_element(self, element) -> Optional[TushareNewsRecord]:
        """解析单个 DOM 元素为新闻记录"""
        try:
            # 尝试提取标题
            title_selectors = [
                "a", ".title", "h3", "h4", "h2", ".news-title",
                "[class*='title']", "[class*='headline']"
            ]
            title = None
            for sel in title_selectors:
                try:
                    el = element.locator(sel).first
                    if el.is_visible():
                        title = el.text_content().strip()
                        if title:
                            break
                except:
                    continue

            if not title:
                return None

            # 尝试提取链接
            url = None
            try:
                link_el = element.locator("a").first
                if link_el.is_visible():
                    href = link_el.get_attribute("href") or ""
                    url = urljoin(self.config.base_url, href) if href else ""
            except:
                pass

            # 尝试提取时间
            pub_date = None
            time_selectors = [".time", ".date", ".pub-time", "[class*='time']", "[class*='date']"]
            for sel in time_selectors:
                try:
                    el = element.locator(sel).first
                    if el.is_visible():
                        raw = el.text_content().strip()
                        pub_date = self._parse_date_string(raw)
                        if pub_date:
                            break
                except:
                    continue

            # 尝试提取来源
            source = "新浪财经"
            source_selectors = [".source", ".from", ".media", "[class*='source']"]
            for sel in source_selectors:
                try:
                    el = element.locator(sel).first
                    if el.is_visible():
                        src = el.text_content().strip()
                        if src:
                            source = src
                            break
                except:
                    continue

            # 提取关联股票
            related = self._extract_related_stocks({"title": title})
            code = related[0] if related else "MARKET"

            return TushareNewsRecord(
                title=title,
                url=url or "",
                source=source,
                published_date=pub_date,
                related_stocks=related,
                code=code,
            )

        except Exception as e:
            logger.debug(f"解析 DOM 元素失败: {e}")
            return None

    def _parse_date_string(self, raw: str) -> Optional[datetime]:
        """解析日期字符串"""
        if not raw:
            return None

        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%m-%d %H:%M",
            "%H:%M",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(raw, fmt)
                # 补充年份（如果只给了月日）
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return dt
            except ValueError:
                continue

        return None

    # ------------------------------------------------------------------
    # 分页处理
    # ------------------------------------------------------------------

    def _goto_next_page(self) -> bool:
        """
        尝试触发下一页加载

        Returns:
            bool: 是否成功触发（不保证有数据）
        """
        try:
            # 尝试 1: 点击分页按钮
            next_selectors = [
                ".el-pagination .btn-next:not(.disabled)",
                ".pagination .next:not(.disabled)",
                "a.next-page", "button.next",
                "[class*='next']",
            ]
            for selector in next_selectors:
                try:
                    btn = self._page.locator(selector).first
                    if btn.is_visible() and btn.is_enabled():
                        btn.click()
                        time.sleep(2)
                        return True
                except:
                    continue

            # 尝试 2: 滚动加载
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            return True

        except Exception as e:
            logger.debug(f"触发下一页失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 快照与调试
    # ------------------------------------------------------------------

    def _save_snapshot(self, prefix: str = "debug") -> str:
        """保存页面快照用于调试"""
        if not self._page:
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_dir = Path("./data/crawler_state/snapshots")
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        html_path = snapshot_dir / f"{prefix}_{timestamp}.html"
        png_path = snapshot_dir / f"{prefix}_{timestamp}.png"

        try:
            html = self._page.content()
            html_path.write_text(html, encoding="utf-8")
            self._page.screenshot(path=str(png_path), full_page=True)
            logger.info(f"快照已保存: {html_path}, {png_path}")
            return str(html_path)
        except Exception as e:
            logger.warning(f"保存快照失败: {e}")
            return ""

    # ------------------------------------------------------------------
    # 资源释放
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # 便捷方法：一键爬取并保存
    # ------------------------------------------------------------------

    def run(self) -> int:
        """
        执行完整爬取流程：爬取 -> 保存 -> 清理旧数据

        Returns:
            int: 保存的新闻条数
        """
        try:
            # 幂等检查：今天是否已爬取
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if self.storage.has_news_for_date(today):
                logger.info(f"{today.date()} 的新闻已存在，跳过爬取")
                return 0

            records = self.crawl()
            if not records:
                logger.warning("未爬取到任何新闻")
                return 0

            saved = self.storage.save_news(records)
            logger.info(f"保存成功: {saved} 条新闻")

            # 清理旧数据
            cleaned = self.storage.cleanup_old_news(self.config.max_age_days)
            if cleaned > 0:
                logger.info(f"清理旧数据: {cleaned} 条")

            return saved

        finally:
            self.close()
