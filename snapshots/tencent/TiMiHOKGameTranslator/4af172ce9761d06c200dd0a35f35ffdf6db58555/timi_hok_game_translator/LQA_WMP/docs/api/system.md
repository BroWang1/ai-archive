# 系统工具接口

## 健康检查

```
GET /api/health
```

免登录, 用于容器健康检查、监控探活

**响应 data:**

```json
{ "status": "ok" }
```

---

## 获取一次性 Ticket

```
GET /api/ticket
```

需要登录, 获取一个 5 分钟有效的一次性 ticket, 用于换取 `access_token` (详见[用户接口 - 获取 access_token](user.md#获取-access_token))

**响应 data:**

```json
{ "ticket": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" }
```

---

## 磁盘使用情况

```
GET /api/disk_usage
```

需要登录, 返回媒体文件目录的磁盘用量

**响应 data:**

```json
{
  "total": 107374182400,
  "used": 21474836480,
  "free": 85899345920
}
```

单位: 字节

---

## 上传文件

```
POST /api/upload_file
Content-Type: multipart/form-data
```

通用文件上传, 用于上传项目配置相关的附件 (如还原配置文件)

**响应 data:**

```json
{
  "file_name": "config.json",
  "file_path": "/media/tmp/..."
}
```

---

## 获取枚举值

```
GET /api/system/enums/<cate>
```

获取系统内置枚举的标签与值, 用于前端下拉选项

**`cate` 取值示例:**

| cate | 说明 |
|---|---|
| `game_type` | 游戏类型 |
| `project_type` | 项目类型 |
| `project_phase` | 项目阶段 |
| `role` | 项目角色 |
| `user_status` | 用户状态 |
| `job_status` | 任务状态 |

**响应 data (示例):**

```json
{
  "list": [
    { "value": 1, "label": "手游" },
    { "value": 2, "label": "端游" }
  ]
}
```

---

## 媒体文件访问

```
GET /media/<path>
```

截图等上传文件的访问路径

- `MEDIA_PUBLIC=false` (默认): 需要登录认证 (由登录中间件鉴权)
- `MEDIA_PUBLIC=true`: 允许匿名访问, 适用于禅道需要内嵌显示截图的场景

生产环境建议由 Nginx 直接提供 `APP_MEDIA_ROOT/media/` 目录, 避免经过 Django 处理

---