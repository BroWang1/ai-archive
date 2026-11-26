# 用户接口

## 获取登录页配置

```
GET /api/user/auth_config
```

免登录, 返回是否开放注册等前端需要的公开配置

**响应 data:**

```json
{
  "allow_register": true,
  "app_name": "LQA"
}
```

---

## 登录

```
POST /api/user/login
Content-Type: application/json
```

免登录, 连续失败次数过多会锁定一段时间

**请求体:**

```json
{
  "username": "admin",
  "password": "Admin123456"
}
```

**响应 data:**

```json
{
  "user": {
    "id": 1,
    "name": "admin",
    "name_zh": "管理员",
    "is_admin": 1
  }
}
```

登录成功后服务端设置 Session Cookie, 后续浏览器请求自动携带

---

## 退出登录

```
POST /api/user/logout
GET  /api/user/logout
```

清除 Session

---

## 注册

```
POST /api/user/register
Content-Type: application/json
```

免登录, 仅在 `ALLOW_REGISTER=true` 时可用, 注册后需管理员分配项目角色

**请求体:**

```json
{
  "username": "testuser",
  "password": "Password123",
  "name_zh": "测试用户",
  "email": "test@example.com"
}
```

---

## 修改自己的密码

```
POST /api/user/password
Content-Type: application/json
```

**请求体:**

```json
{
  "old_password": "OldPass123",
  "new_password": "NewPass456"
}
```

---

## 修改自己的资料

```
PATCH /api/user/profile
Content-Type: application/json
```

**请求体 (字段均可选):**

```json
{
  "name_zh": "新昵称",
  "email": "new@example.com"
}
```

---

## 重置他人密码

```
POST /api/user/reset_password
Content-Type: application/json
```

需要超级管理员权限

**请求体:**

```json
{
  "id": 5,
  "new_password": "NewPass789"
}
```

---

## 获取用户列表

```
GET /api/user/list
```

**Query 参数:**

| 参数 | 类型 | 说明 |
|---|---|---|
| `page` / `page_size` | int | 分页 |
| `cur_id` | int | 游标分页 |
| `name__icontains` | string | 用户名模糊搜索 |
| `name_zh__icontains` | string | 显示名模糊搜索 |
| `department__icontains` | string | 部门模糊搜索 |
| `status` | int | 状态: `1` 正常, `0` 禁用 |
| `project_id` | int | 筛选属于某项目的成员 |
| `is_admin` | int | `1` 只返回项目管理员, `0` 只返回非管理员 |
| `info_type` | int | `0` 基础信息, `1` 简略信息, `2` 含项目角色 |

**响应 data:**

```json
{
  "list": [
    {
      "id": 1,
      "name": "admin",
      "name_zh": "管理员",
      "email": "",
      "department": "",
      "status": 1,
      "is_admin": 1,
      "projects": [...],
      "roles": [...]
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 20
}
```

---

## 获取/创建/修改/删除用户

```
GET    /api/user/entity?id=<uid>&info_type=<0|1>
POST   /api/user/entity
PATCH  /api/user/entity
DELETE /api/user/entity
```

**GET 参数:**

| 参数 | 说明 |
|---|---|
| `id` | 用户 ID, 不传则返回当前登录用户 |
| `info_type` | `0` 基础信息, `1` 含项目角色 (默认) |

本人查询时可在响应中看到自己的 `access_token`

**POST 请求体 (创建用户):**

```json
{
  "name": "newuser",
  "password": "Pass123456",
  "name_zh": "新用户",
  "email": "new@example.com",
  "department": "QA",
  "project_id": 2,
  "roles": [[2, 2]]
}
```

超级管理员可创建任意用户; 项目管理员只能为本项目创建成员

**PATCH 请求体 (修改用户):**

```json
{
  "id": 5,
  "project_id": 2,
  "name_zh": "新名字",
  "status": 0,
  "is_admin": 0,
  "roles": [[2, 2]]
}
```

**DELETE 请求体 (软删除, 需超管):**

```json
{ "id": 5 }
```

---

## 获取当前用户权限信息

```
GET /api/user/permission
```

返回当前用户的基本信息及可访问的项目列表 (含角色), 前端用于初始化路由权限

**响应 data:**

```json
{
  "user": {
    "id": 1,
    "is_admin": 1,
    "name": "admin",
    "name_zh": "管理员"
  },
  "projects": [
    {
      "id": 2,
      "code": "game_cn",
      "name": "某游戏中文版",
      "roles": ["2_1", "2_2"]
    }
  ]
}
```

---

## 获取 access_token

```
POST /api/user/access_token
LQA-Ticket: <ticket>
```

需先通过 `GET /api/ticket` 获取一次性 ticket, 再携带 `LQA-Ticket` 请求头调用本接口, 生成新 token 后旧 token 立即失效

**响应 data:**

```json
{ "access_token": "eyJ..." }
```

---