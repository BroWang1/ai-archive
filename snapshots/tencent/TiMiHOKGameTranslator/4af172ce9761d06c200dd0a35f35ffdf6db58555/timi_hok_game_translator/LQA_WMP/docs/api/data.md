# 测试数据接口

测试数据 (Data) 是还原任务的基础单元, 代表一个需要截图的界面/资源节点, 数据由平台管理员或通过导入工具维护

---

## 获取测试数据详情

```
GET /api/data/entity?id=<id>
```

---

## 获取测试数据列表

```
GET /api/data/list
```

**Query 参数:**

| 参数 | 类型 | 说明 |
|---|---|---|
| `page` / `page_size` | int | 分页 |
| `project_id` | int | 按项目筛选 |
| `module_id` | int | 按模块筛选 |
| `cur_id` | int | 游标分页 |

---

## 创建/修改测试数据

```
POST  /api/data/entity
PATCH /api/data/entity
Content-Type: application/json
```

**请求体 (主要字段):**

```json
{
  "project_id": 2,
  "module_id": 10,
  "file_path": "Assets/UI/main.prefab",
  "key": "ui_main_title",
  "shot_img_path": "/media/..."
}
```

修改时需额外传 `"id": <data_id>`

---

## 获取资源版本列表

```
GET /api/data/resource_version/list?project_id=<id>
```

返回当前项目所有测试数据中出现过的资源版本号列表, 用于提单时的 "报告版本" 下拉选项

---

## 图片资源管理

```
GET   /api/data/image_resource?project_id=<id>
POST  /api/data/image_resource
```

管理每个测试数据关联的参考截图资源

**GET 参数:**

| 参数 | 类型 | 说明 |
|---|---|---|
| `project_id` | int | 项目 ID |
| `data_id` | int | 测试数据 ID |

---

## 图片资源合并

```
POST /api/data/image_resource/merge
Content-Type: application/json
```

将多个图片资源合并处理

---