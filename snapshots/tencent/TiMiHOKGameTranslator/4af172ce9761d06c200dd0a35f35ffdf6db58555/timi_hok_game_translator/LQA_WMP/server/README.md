# LQA 后端服务

![License](https://img.shields.io/badge/license-Apache%202.0-blue)

Python 3.12 + Django 5.1 + Celery 5, 数据库 MySQL 8, 缓存/会话/任务队列 Redis

## 本地开发

```bash
cd server
python -m venv .venv
.venv/Scripts/activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env              # 修改 MYSQL_URL / REDIS_URL 等
python manage.py migrate
python manage.py init_data        # 初始化系统模板: 缺陷类型、区域语言
python manage.py init_admin --username admin --password 'Admin123456'

python manage.py runserver 0.0.0.0:8000
celery -A celery_app worker -l info -P solo   # Windows 使用 -P solo
```

配置读取顺序: 系统环境变量 > `config/env.{APP_ENV}` (`APP_ENV` 默认 `dev`) > `.env`, 全部配置项见 `.env.example`

## 管理命令

| 命令 | 说明 |
|---|---|
| `init_admin --username U --password P [--if-not-exists]` | 创建或重置超级管理员; 也可通过环境变量 `LQA_ADMIN_USERNAME` / `LQA_ADMIN_PASSWORD` 传入 |
| `init_data` | 初始化系统模板项目 (project_id=0) 的缺陷类型、区域语言, 可重复执行 |
| `update_access_token -u <uid> [-e <秒>]` | 为指定用户生成 access_token (默认 30 天有效), 用于还原端等 API 调用方 |

## 目录

```
apps/
  user/      账号、登录/注册、项目角色、access_token
  project/   项目、项目配置 (缺陷类型/语言/图片还原/还原执行 Webhook/缺陷系统/提单配置)
  job/       还原任务、Webhook 触发 (runner.py)、回归
  image/     截图上传与 AI 识别
  bug/       缺陷提单与同步
  data/      测试数据
  system/    枚举
  lqa/       健康检查、上传、管理命令
libs/
  bugtracker/  缺陷系统适配器: local (平台内记录) / bugzilla / zentao
scripts/       冒烟测试、缺陷系统适配器测试
```

## 认证

- 浏览器: `POST /api/user/login {username, password}` 登录后使用 Session Cookie; 请求头 `LQA-Authorization: web`
- API 调用方 (还原端等): 执行管理命令 `update_access_token` 生成 token; 或登录后先 `GET /api/ticket` 取一次性 ticket,
  再带请求头 `LQA-Ticket: <ticket>` 调用 `POST /api/user/access_token`,
  之后请求头带 `LQA-Authorization: <access_token>` (重新生成后旧 token 失效)
- 认证失败返回业务码 `1003`

主要接口:

| 接口 | 说明 |
|---|---|
| `GET /api/user/auth_config` | 是否开放注册 (免登录) |
| `POST /api/user/register` | 自助注册 (`ALLOW_REGISTER=true` 时可用) |
| `POST /api/user/login` / `POST /api/user/logout` | 登录 / 退出 |
| `POST /api/user/password` | 修改自己的密码 |
| `POST /api/user/reset_password` | 超管重置他人密码 |
| `GET /api/user/permission` | 当前用户可访问的项目及角色 |
| `POST /api/job/action` | `start` / `retry` 返回渲染好的 Webhook 请求; 浏览器调用成功后回调 `started`; `stop` 结束任务 |
| `GET /api/bug/tracker_meta` | 当前项目缺陷系统信息与提单下拉选项 |
| `POST /api/bug/tracker_test` | 测试缺陷系统连接 (项目管理员) |
| `GET /api/health` | 健康检查 (免登录) |

## AI 识别服务

`POST {AI_BASE_URL}/image/lqa_check/`, 请求头 `project-method: <项目的 AI 识别项目名>_lqa`

请求体:

```json
{
  "img_base64": "当前截图 base64",
  "history_img_base64": "差异识别时上一次识别成功的截图 base64，可为 null",
  "rect_locations": [/* 还原端上报的文本控件位置 */],
  "language": 2,
  "history_result": null,
  "check_type": ["1", "2-0"],
  "no_trans_marks": [],
  "error_trans_marks": [],
  "ocr_detect": 0
}
```

响应体:

```json
{
  "success": true,
  "err_msg": "",
  "result": {
    "mark_img": "标注后图片 base64",
    "rect_img": "文本框图片 base64",
    "check_detail": {}
  }
}
```

`result.check_detail` 作为识别明细保存, 用于审核页展示、提单与下一次差异识别 (`history_result`)

## 测试

```bash
# 缺陷系统适配器 (本地模拟 Bugzilla/ 禅道服务, 需要可用的 MySQL/Redis)
python scripts/test_bugtracker.py
# 提单/回归全流程
python scripts/test_bug_flow.py
# 接口冒烟测试 (需要先启动服务并初始化超管)
python scripts/smoke_test.py http://127.0.0.1:8000 admin Admin123456
```
