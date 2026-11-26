# 缺陷接口

## 获取缺陷系统信息及提单选项

```
GET /api/bug/tracker_meta?project_id=<id>
```

返回当前项目配置的缺陷系统类型, 以及提单时需要的下拉选项 (版本列表等), 需要项目成员权限

**响应 data:**

```json
{
  "type": "bugzilla",
  "label": "Bugzilla",
  "remote": true,
  "enabled": true,
  "version_report_list": ["1.0", "1.1"],
  "version_fix_list": ["1.2"],
  "release_id_list": [],
  "error": ""
}
```

`type` 取值: `none`（平台内记录）、`bugzilla`、`zentao`

---

## 获取缺陷系统自定义字段

```
GET /api/bug/tracker_fields?project_id=<id>
```

返回缺陷系统中可作为 "自定义提单字段" 的字段及其选项 (Bugzilla/禅道专用), 需要项目成员权限

**响应 data:**

```json
{
  "type": "bugzilla",
  "fields": [
    {
      "name": "cf_game_version",
      "label": "游戏版本",
      "options": ["1.0", "1.1"]
    }
  ]
}
```

---

## 测试缺陷系统连接

```
POST /api/bug/tracker_test
Content-Type: application/json
```

需要项目管理员权限, 用于保存配置前验证连接, `api_key` 传 `******` 时使用已保存的密钥

**请求体 (Bugzilla 示例):**

```json
{
  "project_id": 2,
  "tracker_type": "bugzilla",
  "url": "https://bugzilla.example.com",
  "api_key": "abc123",
  "product": "MyGame",
  "component": "本地化"
}
```

---

## 获取单条提单预览

```
GET /api/bug/build_info?project_id=<id>&image_id=<id>&bug_types=1,2
```

提单前预览将要填入缺陷系统的标题、描述等内容, 需要项目成员权限

**Query 参数:**

| 参数 | 类型 | 说明 |
|---|---|---|
| `project_id` | int | 项目 ID |
| `image_id` | int | 截图 ID |
| `bug_types` | string | 逗号分隔的缺陷类型 ID |

**响应 data:**

```json
{
  "title": "[漏译][主界面] ui_main_zh.png",
  "description": "...",
  "bug_keys": [...],
  "current_owner": "dev_user",
  "title_pre": "",
  "version_report": "1.0"
}
```

---

## 提交单个缺陷

```
POST /api/bug/entity
Content-Type: application/json
```

需要项目成员权限, 提单为异步操作, 返回 Celery 任务 ID

**请求体:**

```json
{
  "project_id": 2,
  "image_id": 200,
  "bug_types": [1, 2],
  "title": "[漏译] ui_main_zh.png",
  "description": "详细描述...",
  "current_owner": "dev_user",
  "version_report": "1.0",
  "version_fix": "1.2",
  "priority": "P2",
  "severity": "normal"
}
```

**响应 data:**

```json
{ "task": "celery-task-id-abc123" }
```

---

## 获取缺陷列表

```
GET /api/bug/list?job_id=<id>
```

`job_id` 和 `image_id` 二选一, 返回时会同步查询外部缺陷系统的最新状态 (`tracker_status`、`tracker_open`)

**Query 参数:**

| 参数 | 类型 | 说明 |
|---|---|---|
| `job_id` | int | 按任务查询 |
| `image_id` | int | 按截图查询 |
| `page` / `page_size` | int | 分页 |
| `title__contains` | string | 标题模糊搜索 |
| `info_type` | int | `1` 简略信息 (不同步缺陷系统) |

**响应 data:**

```json
{
  "list": [
    {
      "id": 300,
      "project_id": 2,
      "job_id": 10,
      "image_id": 200,
      "title": "[漏译] ui_main_zh.png",
      "priority": "P2",
      "severity": "normal",
      "reporter": "test_user",
      "current_owner": "dev_user",
      "version_report": "1.0",
      "version_fix": "1.2",
      "tracker": "bugzilla",
      "external_id": "1234",
      "external_url": "https://bugzilla.example.com/show_bug.cgi?id=1234",
      "status": "open",
      "bill_status": 1,
      "tracker_status": "NEW",
      "tracker_open": true,
      "is_delete": 0,
      "regress_status": 0,
      "regress_job_ids": []
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 20
}
```

---

## 批量提交缺陷

```
POST /api/bug/list
Content-Type: application/json
```

需要项目成员权限, 批量异步提单

**请求体:**

```json
{
  "project_id": 2,
  "job_id": 10,
  "image_ids": [200, 201, 202],
  "bug_types": [1, 2],
  "version_report": "1.0",
  "version_fix": "1.2"
}
```

**响应 data:**

```json
{
  "success": [200, 201],
  "failed": [[202, "错误原因"]]
}
```

---

## 批量更新缺陷

```
PATCH /api/bug/list
Content-Type: application/json
```

目前主要用于批量更新回归状态

**请求体:**

```json
{
  "bug_ids": [300, 301],
  "regress_status": 1
}
```

---