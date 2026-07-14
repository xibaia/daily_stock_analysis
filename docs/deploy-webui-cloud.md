# 云服务器 Web 界面访问指南

如果你已经把项目部署到云服务器，但不知道在浏览器里输入什么地址才能打开 Web 管理界面，这篇教程就是为你准备的。

> 其实就两步：让服务监听外网，再在浏览器里输入地址。

---

## 目录

- [方式一：直接部署（pip + python）](#方式一直接部署pip--python)
- [方式二：Docker Compose](#方式二docker-compose)
- [可选：低内存一次性调度](#可选低内存一次性调度)
- [如何在浏览器里打开界面](#如何在浏览器里打开界面)
- [如何确认 Docker 重建已生效](#如何确认-docker-重建已生效)
- [访问不了？先检查这几项](#访问不了先检查这几项)
- [可选：Nginx 反向代理（绑定域名 / 80 端口）](#可选nginx-反向代理绑定域名--80-端口)
- [安全建议](#安全建议)

---

## 方式一：直接部署（pip + python）

### 第一步：修改 .env 中的监听地址

用编辑器打开 `.env`（在项目根目录，即包含 `main.py` 的目录），找到这一行：

```env
WEBUI_HOST=127.0.0.1
```

把 `127.0.0.1` 改成 `0.0.0.0`：

```env
WEBUI_HOST=0.0.0.0
```

> `127.0.0.1` 表示只有本机能访问，`0.0.0.0` 表示允许任何来源访问。云服务器需要把 `.env` 中的 `WEBUI_HOST` 改成 `0.0.0.0`，或在启动命令里显式传入 `--host 0.0.0.0`，才能从外网打开界面。

### 第二步：启动服务

在项目根目录执行：

```bash
# 只启动 Web 界面（不自动执行分析）
python main.py --webui-only

# 或者：启动 Web 界面（启动时执行一次分析；需每日定时分析请加 --schedule 或设 SCHEDULE_ENABLED=true）
python main.py --webui
```

启动成功后，终端会输出类似：

```
FastAPI 服务已启动: http://0.0.0.0:8000
```

如果你想让服务在退出终端后继续运行，可以用 `nohup`：

```bash
nohup python main.py --webui-only > /dev/null 2>&1 &
```

> 日志文件会由程序自动写入 `logs/` 目录，用 `tail -f logs/stock_analysis_*.log` 查看。

### 修改端口（可选）

默认端口是 8000。如果想改用其他端口，在 `.env` 里设置：

```env
WEBUI_PORT=8888
```

然后重启服务。

---

## 方式二：Docker Compose

### 第一步：确认已有 .env 配置

项目的 `docker/docker-compose.yml` 在容器内部已经自动设置了 `WEBUI_HOST=0.0.0.0`，你不需要在 `.env` 里再改监听地址，Docker 会自动处理。

Docker Compose 中的 `env_file: ../.env` 会把 `.env` 作为**基础启动环境变量**注入容器；Compose 同时把可选的 `../data/runtime.env` 作为后置覆盖层，并通过 `ENV_FILE=/app/data/runtime.env` 让 WebUI 把保存值写入数据卷。新版 WebUI 会在活跃 `.env` 文件缺少某些键时展示启动注入的同名环境变量作为兜底，因此页面上能看到 Docker 启动时注入的配置；“导出 `.env`”仍只导出当前活跃配置文件内容。

如果使用的 Compose 文件尚未包含上述运行时覆盖层，请把活跃配置文件放到已挂载的数据卷中，例如在 Compose 的 `environment` 中增加：

```yaml
- ENV_FILE=/app/data/runtime.env
```

同时保留 `../data:/app/data` 挂载，并将 `../data/runtime.env` 放在基础 `../.env` 之后作为第二个 `env_file`。首次部署时该文件可以不存在，首次保存配置时会自动创建。若使用 `docker run` 或其他手工启动方式，仍需移除或更新启动环境中的同名配置，避免其覆盖运行时文件中的保存值。

`API_PORT`、`API_BIND_ADDRESS` 等决定宿主机端口映射的 Compose 拓扑项仍以根目录 `.env` 为准，因为 Compose 在加载服务容器环境之前就会解析 `${...}`。这类部署参数应继续由运维修改根 `.env`，不属于 Web 持久化覆盖层的接管范围。

### 第二步：启动服务

在项目根目录执行：

```bash
# 同时启动定时分析 + Web 界面（推荐）
docker-compose -f ./docker/docker-compose.yml up -d

# 或者只启动 Web 界面服务
docker-compose -f ./docker/docker-compose.yml up -d server
```

启动后查看状态：

```bash
docker-compose -f ./docker/docker-compose.yml ps
```

看到 `server` 服务状态为 `running` 就说明 Web 界面已经在运行了。

### 修改端口（可选）

默认端口是 8000。如果想改用其他端口，在 `.env` 里设置：

```env
API_PORT=8888
```

Docker Compose 默认只把该端口发布到宿主机回环地址，适合由同机 Nginx 反向代理访问。如果确实需要通过服务器公网 IP 直接访问，还需显式设置：

```env
API_BIND_ADDRESS=0.0.0.0
```

公网直连时请同时启用云安全组、防火墙和 Web 登录认证。使用 Nginx 的部署无需修改默认 `API_BIND_ADDRESS=127.0.0.1`。

然后重新启动容器：

```bash
docker-compose -f ./docker/docker-compose.yml down
docker-compose -f ./docker/docker-compose.yml up -d
```

---

## 可选：低内存一次性调度

正常部署优先使用 Web/API 进程内置的 runtime scheduler。只有需要在空闲期完全释放 analyzer 容器内存时，才启用本节的宿主机 systemd timer；两种调度方式不要同时负责同一批任务，否则会重复分析和通知。

`analyzer` 位于 opt-in 的 `scheduler` Compose profile，默认 `docker compose up -d` 不会启动它。先用不修改 systemd 的渲染模式检查当前 `.env` 中的 `SCHEDULE_TIMES`（逗号分隔）或 `SCHEDULE_TIME`：

```bash
DSA_SYSTEMD_DIR=/tmp/dsa-systemd scripts/install_systemd_analysis_timer.sh --render-only
```

确认生成的 unit 后再安装：

```bash
sudo scripts/install_systemd_analysis_timer.sh
systemctl status dsa-analysis.timer
```

每次触发会执行 `scripts/run_scheduled_analysis_once.sh`，通过互斥目录防止重叠，并运行 `docker compose --profile scheduler run --rm --no-deps analyzer python main.py`。容器内会显式关闭嵌套 scheduler，只执行当前这一轮。修改 Web 设置中的调度时间后需重新运行安装脚本，因为 systemd 不会自动监听 `.env`。

回滚时执行：

```bash
sudo systemctl disable --now dsa-analysis.timer
sudo rm -f /etc/systemd/system/dsa-analysis.service /etc/systemd/system/dsa-analysis.timer
sudo systemctl daemon-reload
```

之后可重新启用 Web/API runtime scheduler。

---

## 如何在浏览器里打开界面

服务启动后，在浏览器地址栏输入：

```
http://你的服务器公网IP:8000
```

例如，如果你的服务器 IP 是 `1.2.3.4`，就输入：

```
http://1.2.3.4:8000
```

如果你的域名已经解析到这台服务器，也可以直接用域名访问：

```
http://your-domain.com:8000
```

> **在哪里查公网 IP？** 登录你的云服务器控制台（阿里云/腾讯云/AWS 等），在实例列表里可以看到「公网 IP」或「弹性 IP」。

---

## 如何确认 Docker 重建已生效

先区分两件事：

1. **Docker 镜像发布版本**：看你部署时使用的镜像 tag，例如 `ghcr.io/zhulinsen/daily_stock_analysis:v3.12.0`。仓库的 Docker 发布由 `.github/workflows/docker-publish.yml` 按 `v*.*.*` Git tag 触发，所以 Docker 版本应以镜像 tag / GitHub Releases 为准。
2. **当前页面加载的前端构建**：看 WebUI “系统设置”页里的版本信息卡片，用来确认浏览器拿到的静态资源是否已经更新。

也就是说，**“系统设置”里的版本信息更适合判断前端是否重建成功，不等同于 Docker 镜像发布版本**。

WebUI 现在会在“系统设置”页展示只读的“版本信息”卡片，包含：

- `WebUI 版本`
- `构建标识`
- `构建时间`

如果 `apps/dsa-web/package.json` 里的版本号仍是占位值 `0.0.0`，页面会自动回退展示本次前端构建生成的 `构建标识`，避免你误把占位版本当成真实发布版本。

当你重新执行 `docker-compose -f ./docker/docker-compose.yml up -d --build`，或者单独重新执行前端 `npm run build` 后，可以刷新浏览器并进入“系统设置”，优先确认“构建时间”是否已经变化；若变化，通常就说明当前加载的静态资源已经切换到最新构建。

如果你想确认“我现在到底部署的是哪个正式版本”，优先用下面这些方式：

```yaml
# 方式 1：看 docker-compose / 部署脚本里的 image tag
image: ghcr.io/zhulinsen/daily_stock_analysis:v3.12.0
```

```bash
# 方式 2：回看你的拉取命令
docker pull ghcr.io/zhulinsen/daily_stock_analysis:v3.12.0
```

如果你一直使用 `latest`，建议改成显式版本 tag；否则很难仅凭容器内页面信息判断自己是否已经重复更新到同一版本。

在确认本地前端打包链路时，建议执行以下命令作为最小验证闭环：

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run build
```

其中 `build` 成功后，`static` 下生成的 `index.html`/JS/CSS 资源会包含本次构建时间与构建版本信息；刷新后在“版本信息”卡片中应能见到变化。

---

## 访问不了？先检查这几项

### 1. 安全组 / 防火墙没有放行端口

这是最常见的原因。云服务器默认只开放 22（SSH）端口，需要手动放行 8000（或你改的端口）。

**操作方法**（以阿里云为例）：
1. 登录阿里云控制台 → 云服务器 ECS → 找到你的实例
2. 点击「安全组」→「配置规则」→「添加安全组规则」
3. 方向选「入方向」，端口范围填 `8000/8000`，授权对象填 `0.0.0.0/0`，点击「确定」

腾讯云、AWS 等云厂商操作类似，找到「安全组」或「防火墙规则」，新增一条允许 TCP 8000 端口的入站规则即可。

### 2. 服务器系统防火墙拦截了

如果你的系统开启了 `ufw` 或 `firewalld`，也需要放行端口：

```bash
# Ubuntu / Debian（ufw）
sudo ufw allow 8000

# CentOS / RHEL（firewalld）
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### 3. 直接部署时 .env 里的 WEBUI_HOST 没改

这是第二常见原因。`.env` 里默认是 `WEBUI_HOST=127.0.0.1`，这样服务只监听本机，外网根本连不上。

改法：打开 `.env`，把 `WEBUI_HOST=127.0.0.1` 改成 `WEBUI_HOST=0.0.0.0`，然后重启服务；也可以在启动命令里显式添加 `--host 0.0.0.0`。

> Docker 方式不需要改这个，可以跳过。

### 4. 端口号对不上

检查访问地址里的端口是否和 `.env` / 启动命令里设置的端口一致。

- 直接部署：默认 8000，可通过 `WEBUI_PORT=xxxx` 修改
- Docker：默认在 `127.0.0.1:8000` 发布，可通过 `API_PORT=xxxx` 修改端口；公网直连还需设置 `API_BIND_ADDRESS=0.0.0.0`

### 5. 页面能打开，但 UI 元素异常变大 / 布局错乱

**症状**：浏览器能访问到 8000 端口，页面有内容，但文字、按钮、卡片尺寸异常大，没有正常布局与配色。

**根因**：`static/index.html` 存在但 CSS/JS 资源缺失（`static/assets/` 为空或不存在），浏览器加载了 HTML 框架但无法拿到样式与脚本，退化为裸 HTML 渲染。

可先用浏览器开发者工具（F12 → Network 标签页）检查是否有 `/assets/index-*.js`、`/assets/index-*.css` 的 **404** 错误。若有，按以下方式修复：

**Docker 用户**：

```bash
docker-compose -f ./docker/docker-compose.yml down
docker-compose -f ./docker/docker-compose.yml build --no-cache
docker-compose -f ./docker/docker-compose.yml up -d
```

重建完成后，用 `Ctrl+Shift+R` 强制刷新浏览器缓存，再访问页面。

**直接部署用户**：先确保已安装 Node.js 18+（推荐 20+），然后手动构建前端：

```bash
cd apps/dsa-web
npm ci
npm run build
cd ../..
python main.py --webui-only
```

---

## 可选：回填已有股票的近期日线

`stock_daily` 已有股票可以通过审核过的回填命令补齐近期数据。先预览股票范围，不访问数据源或写数据库：

```bash
python3 scripts/backfill_stock_daily.py --dry-run
python3 scripts/backfill_stock_daily.py --dry-run --codes 600519,000001
```

执行回填时 `days` 和 `workers` 必须大于 0；默认执行前使用 SQLite 在线备份 API 生成一致性备份：

```bash
python3 scripts/backfill_stock_daily.py --days 15 --workers 3
```

Docker 镜像只包含该审核过的运维脚本，不会复制整个本地 `scripts/` 目录：

```bash
docker compose -f docker/docker-compose.yml run --rm analyzer \
  python scripts/backfill_stock_daily.py --days 15 --workers 3
```

单个股票失败会在最终摘要中列出并使命令返回非零，但不会回滚其他股票已经完成的幂等 UPSERT。需要数据回滚时，先停止所有应用进程，再用命令输出的 `.backup.<时间>` 文件替换原 SQLite 数据库；不要在服务运行中直接覆盖数据库文件。

如果第三方库还需要额外的运行时缓存目录，可在 `.env` 中通过冒号分隔配置 `DSA_RUNTIME_CACHE_DIRS`。容器入口仅接受 `/app/*`、`/home/dsa/*`、`/tmp/*` 下的路径并在启动时修复为 `dsa` 可写；其他根路径会被拒绝。efinance 的包内数据目录由入口动态发现，无需写死 Python 安装路径。

---

## 可选：Nginx 反向代理（绑定域名 / 80 端口）

如果你有域名，或者不想在地址里带 `:8000`，可以用 Nginx 做反向代理，把 80/443 端口流量转发给后端服务。

### 安装 Nginx

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y nginx

# CentOS
sudo yum install -y nginx
```

### 配置文件示例

新建文件 `/etc/nginx/conf.d/stock-analyzer.conf`，内容如下（把 `your-domain.com` 改成你的域名或 IP）：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 支持 WebSocket（Agent 对话页面需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 启用配置并重启 Nginx

```bash
sudo nginx -t            # 检查配置有没有语法错误
sudo systemctl reload nginx
```

配置成功后，直接用 `http://your-domain.com` 访问即可，不需要带端口号。

> **使用 Nginx 后的注意事项**：
> - 如果你开启了 Web 登录认证（`ADMIN_AUTH_ENABLED=true`），建议在 `.env` 中把 `TRUST_X_FORWARDED_FOR=true` 一并打开，否则系统可能无法正确识别真实 IP。该选项适用于**单层可信反向代理**（Nginx → App）部署；如果使用多级代理或 CDN（CDN → Nginx → App），登录限流的 key 可能退化为边缘代理 IP 而非真实客户端 IP，需根据实际拓扑评估。
> - 如需 HTTPS，可以用 [Certbot](https://certbot.eff.org/) 自动申请免费的 Let's Encrypt 证书。

---

## 安全建议

把 Web 界面暴露到公网之前，强烈建议开启登录密码保护：

在 `.env` 中设置：

```env
ADMIN_AUTH_ENABLED=true
```

重启服务后，第一次访问网页时会要求设置初始密码。设置完成后，每次打开设置页面都需要输入密码，可以防止 API Key 等敏感配置被他人看到。

> 如果忘了密码，可以在服务器上执行：`python -m src.auth reset_password`

---

遇到其他问题？欢迎 [提交 Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)。
