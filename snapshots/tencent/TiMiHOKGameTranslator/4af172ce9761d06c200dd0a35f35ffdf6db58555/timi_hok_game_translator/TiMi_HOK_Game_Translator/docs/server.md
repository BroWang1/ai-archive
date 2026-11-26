# TiMiHOKGameTranslator Web Console

一个基于 **FastAPI + Vue3 + Element Plus** 的可视化控制台，用于：

- 🚀 **首次初始化**：Web 向导生成 `conf/config.yaml` 与 `conf/llm.yaml`
- 🌐 **语种配置**：在页面编辑 `conf/languages/<lang>.yaml`（支持新建 / 克隆 / 删除 / 立即运行）
- ⏰ **定时任务**：类似流水线调度（cron 表达式），自动触发工作流
- 📋 **实时日志**：WebSocket 推送子进程 stdout，终端风格展示
- 📜 **运行历史**：持久化到 `workspace/server_meta/runs.json`

> ✨ **零侵入现有 CLI**：Web Console 只是在幕后调用 `python main.py run --language ...` 子进程，
> 和 `main.py` 原有的所有命令完全解耦，CLI 用户不受影响。

---

## 1. 安装

```bash
pip install -r requirements.txt
```

关键新增依赖：`fastapi` / `uvicorn[standard]` / `apscheduler`（已写入 `requirements.txt`）。

## 2. 启动

```bash
python main.py server                        # 默认 0.0.0.0:8787（同网段任意机器可访问）
python main.py server --host 127.0.0.1       # 仅本机访问
python main.py server --port 9000            # 自定义端口
python main.py server --reload               # 开发模式（热重载）
```

启动后：
- **本机访问**：浏览器打开 `http://127.0.0.1:8787/`
- **局域网访问**：同一网段的其他机器打开 `http://<本机IP>:8787/`（例如 `http://30.23.60.41:8787/`）
  - 启动日志会自动列出本机所有可用 IPv4 地址
  - 若无法访问，请在本机防火墙放通 TCP 8787 端口
    （Windows PowerShell 示例，管理员权限执行）：
    ```powershell
    New-NetFirewallRule -DisplayName "TiMiHOKGameTranslator-8787" -Direction Inbound -LocalPort 8787 -Protocol TCP -Action Allow
    ```

> ⚠️ 当前实现未内置鉴权，仅适用于**可信内网**。暴露到公网时请在前面挂反向代理（Nginx / Caddy）并追加 BasicAuth / SSO。

## 3. 使用流程

```
   ┌─────────────────┐
   │  首次访问        │
   └────────┬────────┘
            ▼
   ┌─────────────────────┐
   │  初始化向导（4 步）  │  ← 填 project_code / VCS / LLM，一键落盘
   └────────┬────────────┘
            ▼
   ┌─────────────────────┐
   │  语种配置页面        │  ← + 新建语种 / 克隆既有 / 立即运行
   └────────┬────────────┘
            ▼
   ┌─────────────────────┐
   │  定时任务（可选）    │  ← cron 调度器
   └────────┬────────────┘
            ▼
   ┌─────────────────────┐
   │  运行详情（实时日志）│  ← WebSocket 流
   └─────────────────────┘
```

## 4. 目录结构

```
src/TiMi_HOK_Game_Translator/server/
├── __init__.py
├── __main__.py                 # python -m TiMi_HOK_Game_Translator.server
├── app.py                      # FastAPI 应用工厂
├── backend/
│   ├── api/                    # REST / WebSocket 路由
│   │   ├── setup.py            # 初始化配置
│   │   ├── languages.py        # 语种 CRUD
│   │   ├── runs.py             # 启停 / 查询运行
│   │   ├── schedules.py        # 定时任务 CRUD
│   │   ├── logs.py             # 日志尾读 + WS
│   │   └── meta.py             # 枚举元数据
│   ├── services/
│   │   ├── config_service.py   # conf/*.yaml 读写（含备份）
│   │   ├── log_bus.py          # 日志环形缓冲 + 广播
│   │   ├── runner_service.py   # 子进程启停 + 持久化
│   │   └── scheduler_service.py# APScheduler cron 封装
│   └── models/schemas.py       # Pydantic 请求/响应模型
└── frontend/
    ├── index.html              # SPA 入口（CDN，无 npm 构建）
    └── static/
        ├── app.js              # Vue3 应用，所有页面组件
        └── app.css
```

## 5. 关键 API

| 方法 | 路径 | 作用 |
|---|---|---|
| GET  | `/api/setup/status`           | 查询初始化状态 |
| POST | `/api/setup/init`             | 一键写入 config.yaml + llm.yaml |
| GET/PUT | `/api/setup/global-config` | config.yaml 读写 |
| GET/PUT | `/api/setup/llm`           | llm.yaml 读写 |
| GET  | `/api/languages`              | 列出语种 |
| GET/PUT/DELETE | `/api/languages/{id}` | 单语种 CRUD |
| POST | `/api/languages/{id}/duplicate` | 克隆 |
| POST | `/api/runs`                   | 启动一次运行 |
| GET  | `/api/runs`                   | 运行历史 |
| POST | `/api/runs/{run_id}/stop`     | 停止运行 |
| GET  | `/api/schedules`              | 定时任务列表 |
| PUT  | `/api/schedules/{id}`         | 新建/更新 |
| GET  | `/api/logs/{run_id}?limit=500`| 读取日志 |
| WS   | `/api/logs/ws?run_id=xxx`     | 实时日志推送 |
| GET  | `/api/meta`                   | 所有枚举（vcs/llm/workflow 等） |

打开 `http://127.0.0.1:8787/docs` 可查看 FastAPI 自带的 Swagger 页面。

## 6. 持久化文件

| 文件 | 作用 |
|---|---|
| `conf/config.yaml` / `conf/llm.yaml` / `conf/languages/*.yaml` | 和 CLI 共享 |
| `conf/.backup/*.bak` | 每次写入前的自动备份 |
| `workspace/server_meta/runs.json` | Web 面板的运行历史 |
| `workspace/server_meta/schedules.json` | 定时任务定义 |
| `workspace/server_logs/<run_id>.log` | 每次运行的 stdout 落盘 |

## 7. 常见问题

**Q: Web 面板和 CLI 冲突吗？**
> 不冲突。Web 面板只是在前端 UI 层操作同一份 `conf/*.yaml`；运行工作流时也是通过 `subprocess` 调起同一个 `main.py run` 命令。两边可以并存使用。

**Q: 修改 YAML 时想保留原注释？**
> PyYAML 的 `safe_dump` 不保留注释。如果您对注释敏感，建议：首次由 CLI 创建带注释的 YAML（如 `conf/languages/vi.yaml`），后续在 Web 侧只调整字段值，注释丢失即不可逆。

**Q: 怎么安全传递敏感字段（api_key / password / webhook）？**
> 优先走环境变量：`GAME_TRANS_TOOLCHAIN__VCS__PASSWORD` / `GAME_TRANS_TOOLCHAIN__LLM__API_KEY` / `GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN` 等。Web 面板里保留这些字段为空即可。

**Q: 定时任务 cron 格式？**
> 标准 5 字段：`分 时 日 月 周`。示例：
> - `0 2 * * *` — 每天 02:00
> - `*/15 * * * *` — 每 15 分钟
> - `30 9 * * 1-5` — 工作日 09:30
