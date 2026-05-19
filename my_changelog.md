# My Changelog

## Docker Compose 默认安全化部署

- Docker Compose 的 `server` 服务默认端口映射已从全网卡暴露改为仅绑定宿主机回环地址：`127.0.0.1:${API_PORT:-8000}:${API_PORT:-8000}`。
- 容器内部仍然使用 `--host 0.0.0.0` 监听，保证宿主机上的 Nginx/Caddy 可以访问容器服务。
- `.env.example` 增加了公网部署提示：Docker Compose 场景推荐通过 `Nginx/Caddy -> 127.0.0.1:${API_PORT:-8000} -> FastAPI` 访问。
- `.env.example` 保持 `ADMIN_AUTH_ENABLED=false` 默认值不变，但提示公网部署应开启管理员认证。

## 本机已完成的线上配置

- 已新增 Nginx 反向代理配置：`/etc/nginx/conf.d/stock-analyzer.conf`。
- Nginx 监听公网 `80`，并转发到本机 `127.0.0.1:8000`。
- 已启动 Nginx 并设置开机自启。
- 已将 `stock-server` 容器重建为只暴露 `127.0.0.1:8000->8000/tcp`。
- 已在真实 `.env` 中开启：
  - `ADMIN_AUTH_ENABLED=true`
  - `TRUST_X_FORWARDED_FOR=true`

## 验证记录

- `docker compose -f docker/docker-compose.yml ps` 显示 `stock-server` 端口为 `127.0.0.1:8000->8000/tcp`。
- `curl http://127.0.0.1:8000/api/health` 返回 `{"status":"ok",...}`。
- `curl http://127.0.0.1/api/health` 经 Nginx 反代返回 `{"status":"ok",...}`。
- `curl http://127.0.0.1/api/v1/auth/status` 显示 `authEnabled=true`。
- 外网访问 `http://公网IP` 已由人工确认可用。

## 后续事项

- 云安全组保持开放 `80`，关闭公网 `8000`。
- 购买域名后，将 DNS A 记录指向服务器公网 IP。
- 域名生效后，把 Nginx `server_name` 从临时值改为正式域名。
- 配置 HTTPS 证书后再开放 `443`，长期避免使用纯 HTTP 登录。

## 回滚方式

- 如需恢复公网直连应用端口，可将 `docker/docker-compose.yml` 的端口映射改回 `${API_PORT:-8000}:${API_PORT:-8000}`。
- 回滚直连前仍建议保留 `ADMIN_AUTH_ENABLED=true`，并在云安全组限制访问来源。

---

## docs 本次改动记录（2026-05-15）

### docs/CHANGELOG.md

- `[Unreleased]` 段新增两条：
  - `[修复]` 修正双角色 Web 认证中 session 校验返回值兼容问题，避免无效 Cookie 被受保护 API 或配置备份接口误判为有效；配置备份接口现在要求管理员会话。
  - `[文档]` 补充 Web 认证双角色与访客密码 CLI 说明，注明角色化 session 会使旧登录 Cookie 失效。

### docs/full-guide.md

- `ADMIN_AUTH_ENABLED` 环境变量说明扩展：
  - 补充「管理员密码」与「访客密码」的区分描述。
  - 新增 `python -m src.auth set_user_password` CLI 说明。
  - 注明角色化 session 会使旧版本登录 Cookie 失效，重新登录即可。
  - 明确 Web 的 `.env` 备份导入导出需要管理员会话。

### docs/full-guide_EN.md

- 新增 `ADMIN_AUTH_ENABLED` 环境变量完整英文说明（该变量此前缺失英文文档）。
  - 涵盖管理员密码设置、重置方式、访客密码设置、角色化 session 使旧 Cookie 失效、`.env` 备份权限限制。

---

## Tushare Pro 新浪财经新闻爬取（2026-05-19）

### 新增模块

在 `src/crawler/` 下新增独立的新闻爬取模块，不修改主项目任何配置和数据库模型：

- **`src/crawler/config.py`** — 独立配置读取（`TUSHARE_NEWS_*` 环境变量）
- **`src/crawler/storage.py`** — 独立 SQLAlchemy 存储层，表名 `tushare_news`
- **`src/crawler/tushare_news.py`** — 核心爬虫（API 拦截优先 + DOM 兜底 + 分页 + 自动填表）
- **`src/crawler/tushare_news_cli.py`** — CLI 入口（`--setup` / `--check` / `--run` / `--test` / `--cleanup`）
- **`tests/test_tushare_news.py`** — 19 个单元测试全部通过

### 数据模型

- 表名: `tushare_news`
- 字段: `title`, `url`, `source`, `published_date`, `code`, `related_stocks`, `content_summary`, `fetched_at`
- 市场新闻 `code = MARKET`，个股新闻 `code = 对应股票代码`
- URL 唯一约束去重

### 配置项（`.env` 中设置）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `TUSHARE_NEWS_ENABLED` | `false` | 功能开关 |
| `TUSHARE_NEWS_SCHEDULE_TIME` | `08:00` | 每日执行时间 |
| `TUSHARE_NEWS_STATE_DIR` | `./data/tushare_news_state` | 登录态目录 |
| `TUSHARE_NEWS_REQUEST_INTERVAL` | `2.0` | 请求间隔 |
| `TUSHARE_NEWS_MAX_RETRIES` | `3` | 重试次数 |
| `TUSHARE_NEWS_MAX_PAGES` | `10` | 最大页数 |
| `TUSHARE_NEWS_MAX_AGE_DAYS` | `30` | 数据保留天数 |
| `TUSHARE_NEWS_USERNAME` | `""` | 登录用户名（自动填表） |
| `TUSHARE_NEWS_PASSWORD` | `""` | 登录密码（自动填表） |

### Schedule 集成

- `main.py` 的 `--schedule` 模式已集成 Tushare 新闻后台任务
- 每小时检查一次，到达设定时间后执行爬取
- 幂等：同一天不会重复爬取

### 使用方式

```bash
# 首次登录（需在本地 headed 环境运行）
python -m src.crawler.tushare_news --setup

# 检查登录态
python -m src.crawler.tushare_news --check

# 执行爬取
python -m src.crawler.tushare_news --run

# 测试爬取（不保存）
python -m src.crawler.tushare_news --test

# 清理旧数据
python -m src.crawler.tushare_news --cleanup
```

### 技术要点

- **API 拦截优先**：Vue.js SPA 的数据通过 XHR 加载，优先拦截 `/wctapi/` 响应提取 JSON
- **DOM 兜底**：API 拦截失败时自动降级为 DOM 解析，保存快照供调试
- **自动填表**：`--setup` 时自动填入 `TUSHARE_NEWS_USERNAME` / `TUSHARE_NEWS_PASSWORD`
- **状态持久化**：CloakBrowser `persistent_context` 保存 Cookie/LocalStorage，配置一次运行数月
