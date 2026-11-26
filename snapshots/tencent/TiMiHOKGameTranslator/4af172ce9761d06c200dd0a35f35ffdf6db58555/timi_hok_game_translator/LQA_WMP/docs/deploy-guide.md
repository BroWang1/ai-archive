# LQA 平台部署指南

> 适用对象: 需要在一台 **全新电脑 / 全新服务器** 上从零把 LQA (本地化质量检查) 平台跑起来的人
>
> 适用版本: Docker Compose 一键部署 (推荐) 或 本地源码开发部署, 
> 本文档基于仓库根目录的 `README.md`、`docker-compose.yml`、`.env.example` 及 `server/README.md`、`web/README.md` 整理

---

## 一、平台简介与组件

LQA 平台由以下服务组成, 部署时它们要么打包进容器, 要么在本地分别启动:

| 组件 | 作用 | 技术 |
|---|---|---|
| MySQL 8 | 主数据库 | 容器 / 本地 |
| Redis 7 | 缓存、Session、Celery 消息队列 | 容器 / 本地 |
| server | 后端 API (Django + Gunicorn) | Python 3.12 |
| worker | Celery 异步任务 (AI 识别、自动提单、回归) | Python 3.12 |
| ai | AI 识别服务 (Flask, 内置离线 OCR) | 容器 / 外部服务 |
| web | 前端静态资源 + 反向代理 (Nginx) | Vue 3 + Vite |

**对外访问端口**: 默认 `8080` (容器部署), 本地开发前端 `3333`、后端 `8000`

---

## 二、两种部署方式对比

| 方式 | 适合场景 | 难度 | 依赖 |
|---|---|---|---|
| **A. Docker Compose 一键部署 (推荐)** | 生产 / 演示 / 给不懂 Python 的人 | ⭐ 简单 | 只需装 Docker |
| **B. 本地源码开发部署** | 二次开发、调试 | ⭐⭐⭐ 需配环境 | Python 3.12、Node 20、MySQL、Redis |

下面分别说明

---

## 三、方式 A: Docker Compose 一键部署 (推荐)

### 3.1 前置准备: 安装 Docker

- **Windows**: 下载安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/), 安装后需在设置里勾选 **"Use the WSL 2 based engine"**; 首次启动需开启 WSL2 (控制面板 → 程序 → 启用或关闭 Windows 功能 → 勾选 "虚拟机平台" 和 "适用于 Linux 的 Windows 子系统", 重启后执行 `wsl --install`)
- **macOS**: 下载 [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
- **Linux (Ubuntu 示例)**:
  ```bash
  sudo apt update
  sudo apt install -y docker.io docker-compose-plugin
  sudo usermod -aG docker $USER   # 退出重登后免 sudo 用 docker
  ```

验证:
```bash
docker --version          # 需 20.10+ (Windows/Mac 桌面版自带)
docker compose version    # 需 v2 (命令是 docker compose, 不是 docker-compose)
```

### 3.2 获取代码

```bash
git clone git@github.com:your-org/WMP.git
cd WMP
```

> 若使用 HTTPS: `git clone https://github.com/your-org/WMP.git`

### 3.3 配置环境变量

```bash
cp .env.example .env
```

**必须修改的 4 项 (否则容器会因 `${VAR:?}` 校验报错或存在安全风险)**：

```ini
MYSQL_ROOT_PASSWORD=请改成随机串
MYSQL_PASSWORD=请改成随机串
REDIS_PASSWORD=请改成随机串
SECRET_KEY=请改成随机串
```

生成随机串 (任选其一):
```bash
# 方式 1：用 Python
python -c "import secrets;print(secrets.token_urlsafe(48))"
# 方式 2：用 openssl
openssl rand -base64 48
```

**其余常用项 (按需修改)**：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LQA_ADMIN_USERNAME` | `admin` | 初始超级管理员账号, 已存在时不覆盖 |
| `LQA_ADMIN_PASSWORD` | 空 (必填) | 初始超管密码, **必须设置** |
| `LQA_HTTP_PORT` | `8080` | 平台对外 HTTP 端口 |
| `PUBLIC_URL` | `http://localhost:8080` | 缺陷截图链接与 Webhook `{{lqa_server}}` 变量使用; 部署到别的主机需改成实际域名/IP |
| `ALLOW_REGISTER` | `true` | 是否开放自助注册 |
| `SESSION_COOKIE_SECURE` | `false` | HTTPS 部署时需设为 `true`, 否则浏览器可能拒绝发送会话 Cookie |
| `AI_BASE_URL` | 空 (用内置 ai 容器) | 若已有独立识别服务, 填其地址, 并加 `--scale ai=0` 跳过本地 ai |
| `OCR_ENGINE` / `OCR_PROVIDER` | `rapidocr` | 离线 OCR, 开箱即用; `paddleocr` 精度更高但镜像 +2GB |
| `AI_WORKERS` | `2` | ai 服务进程数, 按并发识别量调整 |
| `AI_HTTP_PORT` | `127.0.0.1:8086` | 默认只本机可访问 ai, 仅供调试 |

> `OCR_ENGINE` / `OCR_PROVIDER` 完整可选项与说明见 [lqa_service/README.md](../lqa_service/README.md)

### 3.4 启动

```bash
docker compose up -d --build
```

首次会拉取/构建镜像 (ai 镜像内含 OCR, 首次构建较慢, 约几分钟到十几分钟)

查看状态:
```bash
docker compose ps          # 看各容器是否 healthy
docker compose logs -f     # 实时看日志; Ctrl+C 退出
```

### 3.5 验证与登录

浏览器打开 `http://<服务器IP>:8080` (本机即 `http://localhost:8080`), 用 `.env` 里的 `LQA_ADMIN_USERNAME` / `LQA_ADMIN_PASSWORD` 登录

> 若打不开: ① 确认防火墙放行 `8080`; ② `docker compose ps` 看 `web` / `server` 是否 `healthy`; ③ `docker compose logs web` 看 Nginx 是否起来

### 3.6 首次使用必做配置

1. **系统管理 → 项目管理**: 创建项目, 并给使用平台的账号分配项目与角色 (超管默认无项目, 需自己建)
2. **项目设置 → 基础配置 → 还原执行**: 配置 Webhook (Jenkins / GitLab CI / 自建服务), 变量如 `{{job_id}}`、`{{regression}}`、`{{lqa_server}}` 见页面提示
3. **项目设置 → 缺陷系统**: 选择 平台内记录 / Bugzilla / 禅道, 填连接信息后点 "测试连接"

### 3.7 常用运维

```bash
docker compose down                 # 停止 (不删数据)
docker compose down -v              # 停止并删除数据卷 (慎用! 会清空库)
docker compose restart server       # 只重启后端
docker compose up -d --build        # 改了 .env 或代码后重建
```

---

## 四、方式 B: 本地源码开发部署

适合需要改代码、跑测试的场景, 需要 **本机** 具备: Python 3.12、Node.js 20+、pnpm 11、MySQL 8、Redis 7

### 4.1 安装基础依赖

- **Python 3.12**: [python.org](https://www.python.org/downloads/) 或 `pyenv`; Windows 勾选 "Add to PATH"
- **Node.js 20 + pnpm 11**:
  ```bash
  # 先装 Node 20 (含 npm), 再装 pnpm
  npm install -g pnpm@11
  node -v && pnpm -v
  ```
- **MySQL 8**: Windows 可用 [MySQL Installer](https://dev.mysql.com/downloads/installer/); Linux `sudo apt install mysql-server`
  创建库与用户:
  ```sql
  CREATE DATABASE lqa CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE USER 'lqa'@'localhost' IDENTIFIED BY '你的密码';
  GRANT ALL PRIVILEGES ON lqa.* TO 'lqa'@'localhost';
  FLUSH PRIVILEGES;
  ```
- **Redis 7**: Windows 用 [Memurai](https://www.memurai.com/) 或 WSL 内装; Linux `sudo apt install redis-server`
  启动并设置密码 (与下面 `.env` 中 `REDIS_PASSWORD` 一致):
  ```bash
  redis-server --requirepass 你的Redis密码
  ```

### 4.2 后端

```bash
cd server
python -m venv .venv
.venv\Scripts\activate            # Windows 激活; Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env              # 修改 MYSQL_URL / REDIS_URL 等 (见 4.5)
python manage.py migrate          # 建表
python manage.py init_data        # 初始化系统模板 (缺陷类型、区域语言)
python manage.py init_admin --username admin --password 'Admin123456'
```

启动 (两个终端):

```bash
# 终端 1: API 服务
python manage.py runserver 0.0.0.0:8000

# 终端 2: Celery 异步任务 (Windows 必须加 -P solo)
celery -A celery_app worker -l info -P solo     # Windows
# celery -A celery_app worker -l info            # Linux/macOS
```

### 4.3 前端

```bash
cd web
pnpm install
pnpm dev            # http://localhost:3333
```

开发时接口请求 `/api-pro/*` 由 Vite 代理到后端 `http://127.0.0.1:8000/`, 
要指向别的后端地址, 在 `web/` 下新建 `.env.development.local` (已被 git 忽略):

```
VITE_PROXY_TARGET = 'http://192.168.1.10:8000/'
```

### 4.4 后端 .env 关键项 (本地开发)

`server/.env` 至少要有:

```ini
SECRET_KEY=随机串
MYSQL_URL=mysql://lqa:你的密码@127.0.0.1:3306/lqa
REDIS_URL=rediscache://:你的Redis密码@127.0.0.1:6379/1
CELERY_BROKER_URL=redis://:你的Redis密码@127.0.0.1:6379/2
CELERY_BACKEND_URL=redis://:你的Redis密码@127.0.0.1:6379/2
LQA_ADMIN_USERNAME=admin
LQA_ADMIN_PASSWORD=Admin123456
AI_BASE_URL=http://<外部AI服务地址>:8086    # 指向外部 AI 识别服务, 详见下方 "对接外部 AI 平台"
```

### 4.5 对接外部 AI 平台

平台本身不内置 AI 识别算法, 识别能力由 **外部 AI 识别服务** 提供, 二者通过 HTTP 对接:

- **容器部署**: 默认随编排启动内置的 `ai` 容器, 无需配置; 若你已有独立部署的识别服务, 在 `.env` 中设置 `AI_BASE_URL` 指向它, 并用 `docker compose up -d --scale ai=0` 跳过本地 `ai` 容器即可
- **本地源码部署**: 在 `server/.env` 中设置 `AI_BASE_URL` 指向外部识别服务地址, 重启后端生效

> 平台调用约定: 对 `POST {AI_BASE_URL}/image/lqa_check/` 发起请求, 并自动带上 `project-method: <AI识别项目名>_lqa` 请求头 ("AI识别项目名" 在 Web 端 "项目设置" 中配置), 具体的识别服务如何部署、支持哪些 OCR 引擎, 不属于本平台部署文档范畴

### 4.6 验证

1. 浏览器打开 `http://localhost:3333`, 用上面的超管账号登录
2. `GET http://127.0.0.1:8000/api/health` (免登录) 返回健康信息

---

## 五、为还原端生成 access_token (对接必做)

还原端 (Unity / UE 插件) 通过 `LQA-Authorization: <access_token>` 调用接口, 需要给对应账号生成 token:

```bash
cd server
.venv\Scripts\activate
python manage.py update_access_token -u <用户ID或用户名> [-e 2592000]   # 默认 30 天有效
```

或在 Web 端登录后: `GET /api/ticket` 取一次性 ticket → 带 `LQA-Ticket` 调 `POST /api/user/access_token` 换 token

还原端只需 3 个接口:

| 接口 | 说明 |
|---|---|
| `GET /api/job/datas` | 拉取任务测试数据 |
| `POST /api/image/entity` | 上传截图 (multipart/form-data) |
| `POST /api/job/device` | 上报设备信息与执行进度 |

详见 [还原端集成指南](../docs/integration/restorer.md)。

---

## 六、常见问题 (FAQ)

**Q1: 容器起不来, 报 `${MYSQL_PASSWORD:?请在 .env 中设置 ...}`**
→ 没复制或没填 `.env` 里的必填项, 回去执行 `cp .env.example .env` 并把 4 个必填项填好

**Q2: `docker compose` 命令找不到**
→ 用的是旧版 `docker-compose`(带横线), 装 `docker-compose-plugin` 后用 `docker compose` (空格) 即可; 或单独装 `pip install docker-compose`

**Q3: Windows 上 Celery 启动报错 / 卡死**
→ Windows 必须加 `-P solo`: `celery -A celery_app worker -l info -P solo`

**Q4: 平台能打开但 "识别" 一直没结果**
→ worker 未启动, 或 `AI_BASE_URL` 指向的 AI 识别服务不可达, 容器部署看 `docker compose logs worker` 和 `docker compose logs ai`; 本地部署确认 `server/.env` 中的 `AI_BASE_URL` 能访问、并已重启后端

**Q5: Webhook 触发失败 (CORS)**
→ 还原执行由 **浏览器** 发起, 目标服务 (Jenkins 等) 需允许平台域名跨域; Jenkins 装 CORS 插件或加反向代理

**Q6: 改了 .env 不生效**
→ 容器部署需 `docker compose up -d --build` 重建; 本地部署需重启 runserver 与 worker

---

## 七、端口速查表

| 端口 | 服务 | 说明 |
|---|---|---|
| 8080 | web (Nginx) | 容器部署对外访问入口 |
| 8000 | server | 本地开发后端 |
| 3333 | web (Vite) | 本地开发前端 |
| 8086 | ai | AI 识别服务 (默认仅本机, 容器内部 `ai:8086`) |
| 3306 | mysql | 数据库 |
| 6379 | redis | 缓存/队列 |

---