# 项目接口

## 获取项目信息

```
GET /api/project/entity?project_id=<id>
```

**响应 data:**

```json
{
  "project": {
    "id": 2,
    "code": "game_cn",
    "name": "某游戏中文版",
    "label": "",
    "team": "QA团队",
    "game_type": 1,
    "project_type": 2,
    "project_phase": 1
  }
}
```

---

## 创建/修改项目

```
POST  /api/project/entity
PATCH /api/project/entity
Content-Type: application/json
```

需要超级管理员权限, 创建时会自动初始化项目的缺陷类型、语言等配置 (从系统模板复制)

**请求体:**

```json
{
  "code": "game_cn",
  "name": "某游戏中文版",
  "label": "",
  "team": "QA团队",
  "game_type": 1,
  "project_type": 2,
  "project_phase": 1
}
```

修改时需额外传 `"project_id": <id>`

**`game_type` 枚举:**

| 值 | 说明 |
|---|---|
| `1` | 手游 |
| `2` | 端游 |
| `3` | 页游 |
| `4` | App |
| `5` | 小游戏 |

**`project_type` 枚举:** `1` 平台级, `2` 项目级

**`project_phase` 枚举:** `1` 上线运营, `2` 下线, `3` 研发期, `4` 保密

---

## 获取项目列表

```
GET /api/project/list
```

**Query 参数:**

| 参数 | 类型 | 说明 |
|---|---|---|
| `page` / `page_size` | int | 分页 |
| `project_id` | int | 按 ID 精确查询 |
| `name__icontains` | string | 名称模糊搜索 |
| `team__icontains` | string | 团队模糊搜索 |
| `game_type` | int | 游戏类型筛选 |
| `project_type` | int | 项目类型筛选 |
| `project_phase` | int | 项目阶段筛选 |

---

## 获取项目角色树

```
GET /api/project/roles?project_id=<id>
```

`project_id=0` 时返回所有项目的角色树, 用于用户管理表单的角色下拉选项

---

## 项目配置

```
GET    /api/project/config?project_id=<id>&cate=<cate>
POST   /api/project/config?cate=<cate>
PATCH  /api/project/config?cate=<cate>
DELETE /api/project/config?cate=<cate>
Content-Type: application/json
```

POST/PATCH/DELETE 需要 **项目管理员** 权限

**`cate` 取值:**

| cate | 说明 |
|---|---|
| `BugType` | 缺陷类型配置 (多条) |
| `Language` | 区域语言配置 (多条) |
| `ImgRevert` | 图片还原配置 (单条): `GET` 时加 `&editor=1` 返回还原端格式 |
| `BugBillMethod` | 提单配置 (单条) |
| `BugBillUser` | 提单人员配置 |
| `BugTracker` | 缺陷系统配置 (单条), `api_key` 字段返回时以 `******` 掩码 |
| `CustomField` | 自定义提单字段 |
| `Other` | 其他配置 (单条) |

**GET 响应 data:**

```json
{ "list": [...] }
```

**PATCH 响应 data:**

```json
{ "config": { ... } }
```

---

## 模块管理

```
GET    /api/project/module/list?project_id=<id>[&all=1]
POST   /api/project/module
PATCH  /api/project/module
DELETE /api/project/module
Content-Type: application/json
```

需要项目成员权限 (增删改需项目管理员)

**创建/修改请求体:**

```json
{
  "project_id": 2,
  "name": "ui_main",
  "show_name": "主界面"
}
```

修改时需额外传 `"id": <module_id>`

**删除请求体:**

```json
{
  "project_id": 2,
  "module_id": 10
}
```

**GET 带 `all=1`** 时返回项目下所有模块 (不分页), 格式为 `{"modules": [...], "total": N}`

---