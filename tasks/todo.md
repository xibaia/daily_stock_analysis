# Tushare Pro 新浪财经新闻爬取 — 开发任务

## 任务清单

- [x] 1. 独立配置模块 (`src/crawler/config.py`)
- [x] 2. 数据模型扩展 (`src/crawler/models.py`)
- [x] 3. 独立存储层 (`src/crawler/storage.py`)
- [x] 4. 核心爬虫 (`src/crawler/tushare_news.py`)
- [x] 5. CLI 入口 (`src/crawler/tushare_news_cli.py`)
- [x] 6. 单元测试 (`tests/test_tushare_news.py`) — 19 passed
- [x] 7. Schedule 集成 (`main.py`)
- [x] 8. 变更记录 (`my_changelog.md`)
- [x] 9. 验证：语法检查 + 导入测试 + 单元测试

## 设计约束

- 不修改 `src/storage.py`、`src/config.py`、`.env.example`、`src/core/config_registry.py`
- 不修改 `docs/` 下任何文件
- 变更记录写到 `my_changelog.md`
- 配置隔离在 `src/crawler/config.py`
