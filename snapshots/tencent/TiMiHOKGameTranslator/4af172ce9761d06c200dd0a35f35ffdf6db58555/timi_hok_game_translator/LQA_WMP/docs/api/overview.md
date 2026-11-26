# API 通用约定

## Base URL

所有接口均以 `/api/` 为前缀, Docker Compose 部署时, Nginx 将 `/api-pro/` 反向代理到后端, 前端通过 `/api-pro/` 访问; 后端本身监听 `/api/`

本文档中的路径均为 **后端实际路径** (`/api/...`)

---

## 认证

平台支持两种认证方式, 通过请求头区分:

### 浏览器 (Session Cookie)

登录后服务端颁发 Session Cookie, 后续请求自动携带, 同时需要携带请求头:

```
LQA-Authorization: web
```

### API 调用方 (access_token)

适用于还原端、脚本等非浏览器场景

```
LQA-Authorization: <access_token>
```

**获取 access_token 的两种方式:**

1. 管理命令 (推荐, 由平台管理员执行):
   ```bash
   python manage.py update_access_token -u <user_id> [-e <有效期秒数，默认30天>]
   ```

2. 接口方式:
   - `GET /api/ticket` 获取一次性 ticket (需已登录)
   - 携带请求头 `LQA-Ticket: <ticket>` 调用 `POST /api/user/access_token`
   - 返回新的 access_token (旧 token 同时失效)

**免登录接口** (无需认证):
- `GET /api/health`
- `GET /api/user/auth_config`
- `POST /api/user/login`
- `POST /api/user/register` (需 `ALLOW_REGISTER=true`)

---

## 响应格式

所有接口返回 JSON, 结构如下:

```json
{
  "code": 0,
  "msg": "",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | int | `0` 表示成功, 非 0 表示错误 |
| `msg` | string | 成功时通常为空或提示文字, 失败时为错误描述 |
| `data` | object | 业务数据, 成功时才有意义 |

---

## 错误码

| code | 常量 | 含义 |
|---|---|---|
| `0` | — | 成功 |
| `1001` | `ERROR` | 通用业务错误 |
| `1002` | `ERROR_PARAM` | 参数错误 |
| `1003` | `ERROR_AUTH` | 认证失败 (未登录或 token 失效) |
| `1004` | `ERROR_PERMISSION` | 无权限 |
| `1005` | `NOT_EXIST` | 资源不存在 |

认证失败 (`1003`) 时前端应跳转到登录页; 还原端应检查 access_token 是否过期

---

## 分页参数

列表接口通用分页参数 (Query String):

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `page` | int | `1` | 页码 (从 1 开始) |
| `page_size` | int | `20` | 每页条数 |
| `cur_id` | int | — | 游标分页: 返回 `id < cur_id` 的记录 |

分页响应体:

```json
{
  "code": 0,
  "data": {
    "list": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

---

## 角色说明

| 角色值 | 名称 | 说明 |
|---|---|---|
| `1` | 项目管理员 | 可管理项目配置、成员、缺陷系统 |
| `2` | 测试人员 | 可创建任务、审核截图、提单 |
| `3` | 开发人员 | 可查看任务、截图、缺陷 |
| — | 超级管理员 | `is_admin=1`, 管理全局用户和项目, 不受项目角色限制 |

---