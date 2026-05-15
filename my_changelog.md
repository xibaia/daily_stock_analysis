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
