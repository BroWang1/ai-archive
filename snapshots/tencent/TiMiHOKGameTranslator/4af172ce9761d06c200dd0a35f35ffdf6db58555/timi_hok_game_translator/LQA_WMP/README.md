# LQA — 本地化质量检查平台

![License](https://img.shields.io/badge/license-Apache%202.0-blue)

LQA (Localization Quality Assurance) 是一个面向游戏 / 应用多语言版本的本地化质量检查平台, 还原端 (如 UE/Unity 编辑器插件) 按任务批量生成各语言截图并上传, 平台调用 AI 识别服务检测 **漏译、错译、超框** 等问题, 测试人员审核结果后一键提交到缺陷系统, 并支持修复后的 **回归验证**

---

## 功能

- **账号体系** — 账号密码登录、自助注册 (注册后由管理员分配项目)、管理员创建用户 / 重置密码 / 禁用账号、API access_token
- **项目与角色** — 多项目隔离, 项目管理员 / 测试人员 / 开发人员三种角色, 超级管理员管理全局
- **还原任务** — 创建任务、选择语言与测试数据; 开始 / 重试时由浏览器直接调用项目配置的 Webhook (Jenkins / GitLab CI / 自建服务) 触发还原端
- **AI 识别** — 截图上传后异步调用 AI 识别服务, 支持全量识别与差异识别
- **缺陷管理** — 每个项目可选择 平台内记录 / Bugzilla 5.x / 禅道(开源版 REST API v1), 支持单个 / 批量 / 自动提单与回归验证

---

## 技术栈

| 层次 | 技术 |
|---|---|
| 后端语言与框架 | Python 3.12 + Django 5.1 |
| 异步任务 | Celery 5 + Redis |
| 数据库 | MySQL 8 |
| 缓存 / 会话 | Redis 7 |
| 后端服务器 | Gunicorn |
| 前端框架 | Vue 3 + Vite 5 + TypeScript |
| UI 组件库 | Element Plus + fast-crud |
| 前端状态管理 | Pinia |
| 前端基础模板 | [v3-admin-vite](https://github.com/un-pany/v3-admin-vite) |
| 容器化部署 | Docker Compose |

---

## 目录结构

```
LQA-WMP/
├── server/                  后端 (Python / Django)
│   ├── apps/
│   │   ├── user/            账号、登录/注册、项目角色、access_token
│   │   ├── project/         项目、项目配置 (缺陷类型/语言/Webhook/缺陷系统)
│   │   ├── job/             还原任务、Webhook 触发、回归
│   │   ├── image/           截图上传与 AI 识别
│   │   ├── bug/             缺陷提单与同步
│   │   ├── data/            测试数据
│   │   ├── system/          枚举
│   │   └── lqa/             健康检查、上传、管理命令
│   ├── libs/
│   │   └── bugtracker/      缺陷系统适配器: none(平台内记录) / bugzilla / zentao
│   ├── scripts/             冒烟测试、缺陷系统适配器测试
│   ├── requirements.txt
│   └── README.md            后端开发文档
├── web/                     前端 (Vue 3)
│   └── README.md            前端开发文档
├── lqa_service/             AI 识别服务 (Flask)
│   ├── common/ocr_provider/ 可插拔 OCR 适配层 (9 种实现)
│   ├── task/                检测算法: 漏译/超框/漏key/重叠/错译
│   └── README.md            识别服务文档
├── docker-compose.yml       一键部署
└── .env.example             环境变量模板
```

---

## 文档

### API 协议

| 文档 | 说明 |
|---|---|
| [通用约定](docs/api/overview.md) | 认证方式、响应格式、错误码 |
| [用户接口](docs/api/user.md) | 登录、注册、账号管理、access_token |
| [项目接口](docs/api/project.md) | 项目管理、项目配置、模块 |
| [任务接口](docs/api/job.md) | 还原任务创建、启停、进度 |
| [截图接口](docs/api/image.md) | 截图上传、AI 识别、审核 |
| [缺陷接口](docs/api/bug.md) | 提单、批量提单、缺陷系统信息 |
| [测试数据接口](docs/api/data.md) | 测试数据管理 |
| [系统工具接口](docs/api/system.md) | 健康检查、枚举、文件上传 |

### 使用指南

| 文档 | 说明 |
|---|---|
| [Web 平台使用文档](docs/web-guide.md) | 面向测试 / 项目管理员 / 开发的 Web 平台操作手册 |
| [平台部署指南](docs/deploy-guide.md) | 全新电脑 / 服务器从零把平台跑起来的操作手册（Docker 一键部署 + 本地源码部署） |

### 集成指南

| 文档 | 说明 |
|---|---|
| [还原端集成指南](docs/integration/restorer.md) | 还原端（Unity 插件等）与平台对接的完整流程 |

### 快速索引: 还原端需要的接口

还原端只需关注以下三个接口, 认证使用 `LQA-Authorization: <access_token>` 请求头:

| 接口 | 说明 |
|---|---|
| `GET /api/job/datas` | 拉取任务测试数据 |
| `POST /api/image/entity` | 上传截图 (multipart/form-data) |
| `POST /api/job/device` | 上报设备信息与执行进度 |

详见 [还原端集成指南](docs/integration/restorer.md)。

---

## 贡献

欢迎提交 Issue 和 Pull Request，详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 许可证

本项目后端代码以 **Apache-2.0** 开源，详见 [LICENSE](LICENSE)。

---