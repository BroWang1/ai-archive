# 截图接口

## 上传截图 (还原端调用)

```
POST /api/image/entity
Content-Type: multipart/form-data
LQA-Authorization: <access_token>
```

还原端上传每张截图, 上传后可选择同步触发 AI 识别

**Form 字段:**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | file | 是 | 截图文件 (PNG/JPG) |
| `project_id` | int | 是 | 项目 ID |
| `job_id` | int | 是 | 任务 ID |
| `data_id` | int | 是 | 测试数据 ID (来自 `/api/job/datas`) |
| `language` | int | 是 | 语言值 |
| `rect_locations` | string | 是 | 文本控件位置信息 JSON 字符串 |
| `ai_sign` | int | 否 | `1` 上传后立即触发 AI 识别, 默认 `0` |
| `discern` | int | 否 | 识别模式: `0` 全量, `1` 差异 |
| `create_bug` | int | 否 | `1` 识别后自动提单 |
| `regression` | int | 否 | `1` 表示回归任务 |
| `bug_ids` | string | 否 | 回归时传入需回归的缺陷 ID, 逗号分隔 |

**响应 data:**

```json
{
  "image": {
    "id": 200,
    "project_id": 2,
    "job_id": 10,
    "data_id": 501,
    "language": 2,
    "file_name": "ui_main_zh.png",
    "file_path": "/media/...",
    "iteration": 1,
    "is_latest": 1,
    "ai_sign": 0
  },
  "task_id": "abc123..."
}
```

`task_id` 为 Celery 任务 ID, `ai_sign=1` 时返回; 可用于追踪异步识别进度

---

## 获取截图详情

```
GET /api/image/entity?image_id=<id>
```

**响应 data:**

```json
{
  "image": {
    "id": 200,
    "file_path": "/media/...",
    "ai_mark_img_path": "/media/...",
    "ai_rect_img_path": "/media/...",
    "ai_check_detail": {...},
    "ai_bug_types": "[1,2]",
    "will_review": 1,
    "reviewed": 0,
    "bug_num": 2,
    ...
  }
}
```

---

## 获取截图列表

```
GET /api/image/list
```

**Query 参数:**

| 参数 | 类型 | 说明 |
|---|---|---|
| `page` / `page_size` | int | 分页 |
| `job_id` | int | 按任务筛选 |
| `data_id` | int | 按测试数据筛选 (需同时传 `job_id`) |
| `language` | int | 按语言筛选 |
| `languages` | string | 逗号分隔, 多语言筛选 |
| `is_latest` | int | `1` 只返回最新截图 |
| `will_review` | int | 是否需要审核 |
| `reviewed` | int | 审核状态 |
| `err_type` | int | 错误类型 |
| `ai_bug_types` | string | 逗号分隔, 按 AI 识别出的缺陷类型筛选 |
| `module_ids` | string | 逗号分隔的模块 ID |
| `info_type` | int | `0` 简略信息 (不含大字段) |
| `pk__gte` / `pk__lte` | int | ID 范围查询 |

**PATCH 批量更新:**

```
PATCH /api/image/list
Content-Type: application/json
```

```json
{
  "ids": [200, 201, 202],
  "reviewed": 1,
  "will_review": 0
}
```

---

## 删除截图

```
DELETE /api/image/entity
Content-Type: application/json
```

```json
{
  "project_id": 2,
  "image_ids": [200, 201]
}
```

或单个: `"image_id": 200`

---

## 触发 AI 识别

```
POST /api/image/ai_sign
Content-Type: application/json
```

手动触发 AI 识别, 可针对单张或整个任务批量触发

**请求体:**

```json
{
  "image_id": 200,
  "job_id": null,
  "discern": 0,
  "languages": [2, 3]
}
```

`image_id` 和 `job_id` 二选一: 传 `image_id` 为同步识别单张; 传 `job_id` 为异步批量识别整个任务

`discern`: `0` 全量识别, `1` 差异识别

---

## 数据审核记录

```
GET   /api/image/data_review?data_id=<id>&project_id=<id>
PATCH /api/image/data_review
Content-Type: application/json
```

**GET 响应 data:**

```json
{
  "data_review": {
    "id": 50,
    "data_id": 501,
    "project_id": 2,
    "rect_location": [...],
    "check_rect_location": "{}",
    "dirty_rect_location": "{}",
    "size": "1920,1080",
    "reviewer": "system",
    "image_id": 200
  }
}
```

**PATCH 请求体 (人工审核修正文本框):**

```json
{
  "id": 50,
  "check_rect_location": "{}",
  "dirty_rect_location": "{}"
}
```

---