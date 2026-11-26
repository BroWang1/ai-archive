# 任务接口

## 获取任务列表

```
GET /api/job/list
```

**Query 参数：**

| 参数 | 类型 | 说明 |
|---|---|---|
| `page` / `page_size` | int | 分页 |
| `cur_id` | int | 游标分页 |
| `project_id` | int | 按项目筛选 |
| `id` | int | 按任务 ID 精确查询 (同时返回子任务列表) |
| `name__icontains` | string | 任务名模糊搜索 |
| `status` | int | 任务状态筛选 |
| `creator_id` | int | 按创建人筛选 |
| `language` | int | 按语言筛选 |
| `created_begin_at` | string | 创建时间起始 |
| `created_end_at` | string | 创建时间结束 |
| `is_parent` | int | `0` 只返回普通任务, `1` 只返回回归任务 |
| `info_type` | int | `0` 简略信息 (不含扩展字段), 其他含扩展字段 |

**响应 data:**

```json
{
  "list": [
    {
      "id": 10,
      "project_id": 2,
      "name": "2024-01 全量还原",
      "languages": [2, 3],
      "status": 2,
      "reason": "",
      "created_at": "...",
      "updated_at": "...",
      "parent_id": 0,
      "regress_num": 1,
      "bug_num": 5
    }
  ],
  "total": 20,
  "page": 1,
  "page_size": 20
}
```

**任务状态 (status) 枚举:**

| 值 | 说明 |
|---|---|
| `1` | 未执行 |
| `2` | 执行中 |
| `3` | 已完成 |
| `4` | 异常终止 |

---

## 获取任务详情

```
GET /api/job/entity?job_id=<id>[&progress=1][&fields=f1,f2][&mappings=1]
```

| 参数 | 说明 |
|---|---|
| `job_id` | 任务 ID |
| `progress` | `1` 时额外返回识别进度 (`progress_rate`、`all_count`、`ai_signed_count`) |
| `fields` | 逗号分隔，只返回指定字段 |
| `mappings` | `1` 时额外返回语言/缺陷类型/状态的枚举映射 |

**响应 data:**

```json
{
  "job": {
    "id": 10,
    "project_id": 2,
    "name": "2024-01 全量还原",
    "languages": [2, 3],
    "status": 2,
    "progress_rate": "15/20",
    ...
  }
}
```

---

## 创建任务

```
POST /api/job/entity
Content-Type: application/json
```

需要项目成员权限

**请求体 (主要字段):**

```json
{
  "project_id": 2,
  "name": "2024-01 全量还原",
  "languages": [2, 3],
  "plan_start_at": "2024-01-10T09:00:00",
  "plan_end_at": "2024-01-12T18:00:00"
}
```

**响应 data:**

```json
{ "job": { "id": 10, ... } }
```

---

## 修改任务

```
PATCH /api/job/entity
Content-Type: application/json
```

需要项目成员权限, 请求体同创建, 额外传 `"id": <job_id>`

---

## 任务操作 (启动 / 重试 / 回调 / 停止)

```
POST /api/job/action
Content-Type: application/json
```

**请求体:**

```json
{
  "job_id": 10,
  "action": "start",
  "build_id": "",
  "regression": 0
}
```

**`action` 取值:**

| action | 说明 | 返回内容 |
|---|---|---|
| `start` | 启动任务: 返回渲染好的 Webhook 请求, 由浏览器发起调用 | `trigger` 对象 |
| `retry` | 重试: 补提未识别的截图, 并返回 Webhook 请求 | `trigger` 对象 |
| `started` | 浏览器调用 Webhook 成功后回调, 将任务置为执行中 | 无 |
| `stop` | 结束任务 | 无 |

`started` 时需额外传 `build_id` (Webhook 响应中的构建 ID) 和 `regression` (`0` 普通, `1` 回归, `2` 重试)

**`start`/`retry` 响应 data:**

```json
{
  "job_id": 10,
  "regression": 0,
  "trigger": {
    "url": "https://jenkins.example.com/job/...",
    "method": "POST",
    "headers": { "Authorization": "..." },
    "body": "..."
  }
}
```

---

## 创建回归任务

```
POST /api/job/bug_regress
Content-Type: application/json
```

基于已有缺陷创建回归任务, 创建后调用 `/api/job/action` 的 `start` action 触发执行

**请求体:**

```json
{
  "project_id": 2,
  "parent_id": 10,
  "bug_ids": [101, 102, 103],
  "languages": [2, 3]
}
```

---

## 获取任务进度

```
GET /api/job/progress?job_id=<id>
```

返回各语言的截图上传进度

**响应 data:**

```json
{
  "all_data_count": 100,
  "all_imaged_count": 45,
  "languges": [
    {
      "language": 2,
      "imaged_count": 25,
      "imaged_count_per": "25%"
    }
  ]
}
```

---

## 获取任务测试数据 (还原端调用)

```
GET /api/job/datas
LQA-Authorization: <access_token>
```

还原端拉取本次任务需要还原的数据列表

**Query 参数:**

| 参数 | 类型 | 说明 |
|---|---|---|
| `job_id` | int | 必填 |
| `language` | int | 语言值, 必填 |
| `regression` | int | `0` 普通, `1` 回归 |
| `count` | int | 本次拉取条数, 默认全部 |
| `minID` | int | 增量拉取: 只返回 `id > minID` 的数据 |
| `module_ids` | string | 逗号分隔的模块 ID, 按模块筛选 |
| `iteration` | int | 迭代轮次 |
| `use_cache` | int | `1` 使用缓存 |

**响应 data:**

```json
{
  "datas": [
    {
      "id": 501,
      "file_path": "/media/...",
      "module_id": 10
    }
  ],
  "bug_ids": []
}
```

回归任务时 `bug_ids` 中包含需要回归验证的缺陷 ID 列表

---

## 上报设备与进度 (还原端调用)

```
POST /api/job/device
Content-Type: application/json
LQA-Authorization: <access_token>
```

还原端上报执行设备信息和当前进度

**请求体:**

```json
{
  "job_id": 10,
  "execute_pc": "PC-001",
  "language": 2,
  "status": 2,
  "progress": 50,
  "total": 100
}
```

**GET 查询设备列表:**

```
GET /api/job/device?job_id=<id>
```

返回该任务下所有设备的执行状态列表

---