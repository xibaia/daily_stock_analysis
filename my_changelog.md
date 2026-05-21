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

## DeepEar 集成记录（2026-05-21）

### 接入方式

- 已将 `DeepEar` 以 `git submodule` 形式接入到 `vendor/DeepEar`。
- 已新增独立开发分支：`feat/deepear-submodule-integration`。
- 当前方案采用“DSA 站内入口 + DeepEar 独立服务 + 默认服务账号桥接登录”的最小入侵接法。

### DSA 后端改动

- 新增 DeepEar 桥接服务：`src/services/deepear_auth_service.py`。
- 新增桥接接口：`GET /api/v1/deepear/session`。
- 接口职责：
  - 读取 `DEEPEAR_*` 配置；
  - 使用默认服务账号登录 DeepEar；
  - 首次登录失败时按邀请码自动注册后重试；
  - 返回 `public_url`、`token`、`user` 给前端桥接页使用。
- `api/deps.py` 已改为对 `SystemConfigService` 懒加载，减少无关依赖对轻量接口和测试的影响。
- `api/v1/__init__.py` 与 `api/v1/endpoints/__init__.py` 已改为懒加载导出，避免导入单个 endpoint 时把整套路由和数据源一起拉起。

### DSA 前端改动

- 侧边栏已新增 `DeepEar` 导航入口：路由为 `/deepear`。
- 新增页面：`apps/dsa-web/src/pages/DeepEarPage.tsx`。
- 页面行为：
  - 先请求 `/api/v1/deepear/session`；
  - 成功后以 iframe 打开 DeepEar；
  - 通过 `postMessage` 将 token 和用户信息发送给 DeepEar；
  - 提供“刷新连接”和“新标签页打开”兜底入口。

### DeepEar 最小补丁

- 仅在 `vendor/DeepEar/dashboard/frontend/src/main.tsx` 接入了一个很薄的 SSO bridge。
- 新增 `vendor/DeepEar/dashboard/frontend/src/ssoBridge.ts`。
- 补丁行为：
  - 监听父页面发来的 `DSA_DEEPEAR_SSO` 消息；
  - 校验来源 origin；
  - 调用 DeepEar 现有 zustand store 的 `login()` 写入登录态；
  - 若当前位于 `/login` 或 `/register`，自动跳转回首页。
- 未修改 DeepEar 后端认证协议，尽量降低后续同步上游时的冲突面。

### Docker 与配置

- 新增 DeepEar 独立镜像：`docker/Dockerfile.deepear`。
- 新增启动脚本：`docker/deepear-entrypoint.sh`。
- 新增独立配置模板：`docker/deepear.env.example`。
- `docker/docker-compose.yml` 已新增 `deepear` 服务。
- `.env.example` 已补充 DSA 侧桥接所需配置：
  - `DEEPEAR_ENABLED`
  - `DEEPEAR_INTERNAL_URL`
  - `DEEPEAR_PUBLIC_URL`
  - `DEEPEAR_PORT`
  - `DEEPEAR_SERVICE_USERNAME`
  - `DEEPEAR_SERVICE_PASSWORD`
  - `DEEPEAR_INVITATION_CODE`
  - `DEEPEAR_REQUEST_TIMEOUT`
- `.gitignore` 已忽略 `docker/deepear.env`。

### 文档改动

- `README.md` 已补充 DeepEar 子模块初始化、本机联调和服务器下拉部署说明。
- `docs/DEPLOY.md` 已补充：
  - `git submodule update --init --recursive`
  - `docker/deepear.env` 配置
  - 本机开发与服务器部署统一使用 `docker compose -f docker/docker-compose.yml up -d --build server deepear`

### 验证记录

- 前端测试通过：
  - `npm run test -- --run src/pages/__tests__/DeepEarPage.test.tsx src/components/layout/__tests__/SidebarNav.test.tsx`
- 后端测试通过：
  - `./.venv/bin/python -m pytest tests/test_deepear_auth_service.py tests/test_deepear_api.py -q`
- 前端生产构建通过：
  - `npm run build`
- Docker Compose 配置解析通过：
  - `docker compose -f docker/docker-compose.yml config`

### 服务器部署步骤

- 服务器只需要执行：
  - `git pull`
  - `git submodule update --init --recursive`
  - 准备 `.env`
  - 准备 `docker/deepear.env`
  - `docker compose -f docker/docker-compose.yml up -d --build server deepear`

### 备注

- 我误把一条变更摘要先写进了 `docs/CHANGELOG.md` 的 `Unreleased` 段。
- 本次你指定需要记录到 `my_changelog.md`，因此这里已经补齐完整记录。
