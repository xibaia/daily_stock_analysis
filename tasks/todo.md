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

- 不修改 `src/storage.py`、`src/config.py`、`src/core/config_registry.py`
- 不修改 `docs/` 下任何文件
- 配置隔离在 `src/crawler/config.py`

---

## 方案调整：本机抓取 + 手动同步到服务器

### 调整原因
- 服务器环境缺少浏览器/桌面环境，难以运行 CloakBrowser 爬虫
- 改为：本机执行抓取，导出为精简 SQLite，手动 scp 到服务器，服务器执行 import 合并

### 任务清单

- [x] 1. 固定同步目录配置 (`src/crawler/config.py`) — 增加 `TUSHARE_NEWS_SYNC_DIR`
- [x] 2. 导出命令默认指向固定目录 (`src/crawler/sync.py`) — `DEFAULT_SYNC_FILE` 指向 `./data/sync/`
- [x] 3. 抓取 CLI 增加 `--export` 参数 (`src/crawler/tushare_news_cli.py`) — 抓取后自动导出
- [x] 4. 环境变量模板更新 (`.env.example`) — 增加 Tushare 新闻爬虫全套配置
- [x] 5. 验证：语法检查 + 导入测试（py_compile通过，AST结构验证通过）

### 使用方式

```bash
# 本机执行（抓取 + 导出）
python -m src.crawler.tushare_news --run --export

# 导出文件位置：./data/sync/tushare_news_sync.db
# 然后手动 scp 到服务器
scp ./data/sync/tushare_news_sync.db user@server:/path/to/data/

# 服务器执行导入合并
python -m src.crawler.sync import -i /path/to/data/tushare_news_sync.db

# 也可以单独执行某个步骤
python -m src.crawler.tushare_news --run       # 仅抓取
python -m src.crawler.sync export               # 仅导出
python -m src.crawler.sync status               # 查看数据库状态
```
