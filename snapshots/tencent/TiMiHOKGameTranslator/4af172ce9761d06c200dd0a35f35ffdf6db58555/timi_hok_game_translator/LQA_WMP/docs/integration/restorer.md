# 还原端集成指南

本文档面向还原端开发者 (Unity/UE 编辑器插件、自动化脚本等), 描述与 LQA 平台交互的完整流程

---

## 概述

还原端的职责:
1. 被 Webhook 触发后启动
2. 从平台拉取本次任务的测试数据列表
3. 按数据逐一生成各语言截图, 上传到平台
4. 上报设备信息与进度

平台侧的职责:
- 在浏览器中调用还原端配置的 Webhook, 触发还原
- 接收截图、异步调用 AI 识别服务、生成缺陷报告

---

## 认证

还原端使用 **access_token** 认证, 每个请求携带请求头:

```
LQA-Authorization: <access_token>
```

**获取 access_token (由平台管理员操作):**

```bash
# 在后端服务器上执行
python manage.py update_access_token -u <user_id> -e 2592000
# -e 指定有效期 (秒), 默认 30 天
```

也可以通过接口方式获取, 详见 [API 通用约定 - 认证](../api/overview.md)

---

## 交互流程

```
平台（浏览器）          还原端
     │                    │
     │── Webhook 触发 ──→  │  携带 job_id、languages、lqa_server 等参数
     │                    │
     │                    │── GET /api/job/datas ──→ 平台
     │                    │←── 测试数据列表 ─────────
     │                    │
     │  (循环处理每个数据)  │
     │                    │── POST /api/image/entity ──→ 平台 (上传截图)
     │                    │←── image_id ─────────────
     │                    │
     │                    │── POST /api/job/device ──→ 平台 (上报进度)
     │                    │←── 确认 ────────────────
     │                    │
```

Webhook 参数由平台在 "项目设置 > 基础配置 > 还原执行" 中配置, 可用变量:

| 变量 | 说明 |
|---|---|
| `{{job_id}}` | 任务 ID |
| `{{languages}}` | 语言列表 (逗号分隔的平台标准编码, 如 `LAN_EN_US,LAN_JA_JP`) |
| `{{language_values}}` | 平台标准语言编码数组 (JSON), 如 `["LAN_EN_US","LAN_JA_JP"]` |
| `{{ue_languages}}` | UE 还原插件专用语言编码 (逗号分隔), 如 `LAN_EU_EN,LAN_JP_JP`; 拉起 UE 时命令行 `-Language=` 应使用此值 |
| `{{ue_language_values}}` | UE 还原插件专用语言编码数组（JSON） |
| `{{regression}}` | `0` 普通, `1` 回归 |
| `{{lqa_server}}` | 平台访问地址 (来自 `PUBLIC_URL` 配置) |

> **UE 还原插件语言编码说明**
> 平台内部统一使用 ISO 国家码 (如韩语 `LAN_KO_KR`、日语 `LAN_JA_JP`), 而 UE 还原插件 `ConfigManager.cpp` 的 `LanguageMap` 使用另一套命名 (如韩语 `LAN_KO_KO`、日语 `LAN_JP_JP`)  
> 当还原端直接拼接 UE 启动命令时, 请优先使用 `{{ue_languages}}` / `{{ue_language_values}}` 变量, 平台已完成反向翻译; 否则 UE 命令行 `-Language=` 传入平台标准编码将无法被插件识别, 还原会降级到默认语言 (英语)

---

## 接口说明

### 1. 拉取测试数据

```
GET /api/job/datas?job_id=<id>&language=<lang>&regression=<0|1>
LQA-Authorization: <access_token>
```

建议分语言分批拉取

**完整请求示例:**

```
GET https://lqa.example.com/api/job/datas?job_id=10&language=2&regression=0&count=500
LQA-Authorization: eyJ...
```

**响应示例:**

```json
{
  "code": 0,
  "data": {
    "datas": [
      { "id": 501, "file_path": "Assets/UI/main.prefab", "module_id": 10 },
      { "id": 502, "file_path": "Assets/UI/shop.prefab", "module_id": 11 }
    ],
    "bug_ids": []
  }
}
```

回归任务时 `bug_ids` 包含需要回归的缺陷 ID, 还原端在上传截图时需要传回这些 `bug_ids`

**增量拉取 (分批):**

```
GET /api/job/datas?job_id=10&language=2&count=100&minID=0
GET /api/job/datas?job_id=10&language=2&count=100&minID=502
```

---

### 2. 上传截图

```
POST /api/image/entity
Content-Type: multipart/form-data
LQA-Authorization: <access_token>
```

**Form 字段:**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | file | 是 | 截图文件 (PNG 推荐) |
| `project_id` | int | 是 | 项目 ID |
| `job_id` | int | 是 | 任务 ID |
| `data_id` | int | 是 | 测试数据 ID (来自上一步) |
| `language` | int | 是 | 语言值 |
| `rect_locations` | string | 是 | 文本控件位置 JSON (见下方格式) |
| `ai_sign` | int | 否 | `1` 上传后立即触发 AI 识别 |
| `discern` | int | 否 | `0` 全量 (默认), `1` 差异识别 |
| `create_bug` | int | 否 | `1` 识别后自动提单 |
| `regression` | int | 否 | `1` 表示回归任务 |
| `bug_ids` | string | 否 | 回归时: 需回归的缺陷 ID, 逗号分隔 |

**`rect_locations` 格式:**

`rect_locations` 是一个 JSON 字符串, 描述截图中各文本控件的位置 (用于 AI 识别定位文字区域):

```json
[
  {
    "x": 100,
    "y": 200,
    "width": 300,
    "height": 50,
    "key": "ui_title",
    "text": "标题文本"
  }
]
```

字段含义:

| 字段 | 说明 |
|---|---|
| `x`, `y` | 控件左上角坐标 (像素) |
| `width`, `height` | 控件宽高 (像素) |
| `key` | 控件唯一标识 |
| `text` | 控件当前显示文本 |

**响应示例:**

```json
{
  "code": 0,
  "data": {
    "image": {
      "id": 200,
      "file_path": "/media/project/2/job/10/image/ui_main_zh.png"
    },
    "task_id": "abc123-..."
  }
}
```

---

### 3. 上报设备与进度

```
POST /api/job/device
Content-Type: application/json
LQA-Authorization: <access_token>
```

建议每完成一批截图上传后上报一次进度

**请求体:**

```json
{
  "job_id": 10,
  "execute_pc": "PC-RENDER-001",
  "language": 2,
  "status": 2,
  "progress": 45,
  "total": 100
}
```

| 字段 | 说明 |
|---|---|
| `execute_pc` | 还原设备标识 (机器名或 IP) |
| `language` | 当前正在处理的语言 |
| `status` | `1` 等待, `2` 执行中, `3` 完成, `4` 失败 |
| `progress` | 已完成数量 |
| `total` | 总数量 |

---

## 错误处理

所有接口返回 `code != 0` 时为错误, `msg` 字段包含错误描述

| code | 建议处理方式 |
|---|---|
| `1003` | access_token 失效, 需重新获取 |
| `1002` | 请求参数错误, 检查字段 |
| `1005` | 资源不存在, `job_id` 或 `data_id` 可能已被删除 |
| `1001` | 通用错误, 记录日志, 可重试 |

建议对上传失败的截图进行重试 (最多 3 次), 重试时使用相同的 `data_id` 和 `language`, 平台会自动管理 `iteration` 版本

---

## 完整示例 (Python 伪代码)

```python
import requests

LQA_SERVER = "https://lqa.example.com"
ACCESS_TOKEN = "eyJ..."
HEADERS = {"LQA-Authorization": ACCESS_TOKEN}

def run_restore(job_id, project_id, languages):
    for language in languages:
        # 1. 拉取测试数据
        resp = requests.get(
            f"{LQA_SERVER}/api/job/datas",
            params={"job_id": job_id, "language": language},
            headers=HEADERS
        )
        datas = resp.json()["data"]["datas"]

        for i, data in enumerate(datas):
            # 2. 生成截图（业务逻辑）
            screenshot, rect_locations = render_screenshot(data, language)

            # 3. 上传截图
            requests.post(
                f"{LQA_SERVER}/api/image/entity",
                data={
                    "project_id": project_id,
                    "job_id": job_id,
                    "data_id": data["id"],
                    "language": language,
                    "rect_locations": json.dumps(rect_locations),
                    "ai_sign": 1,
                },
                files={"file": ("screenshot.png", screenshot, "image/png")},
                headers=HEADERS
            )

            # 4. 上报进度
            if i % 10 == 0:
                requests.post(
                    f"{LQA_SERVER}/api/job/device",
                    json={
                        "job_id": job_id,
                        "execute_pc": "MY-PC-001",
                        "language": language,
                        "status": 2,
                        "progress": i + 1,
                        "total": len(datas)
                    },
                    headers=HEADERS
                )
```

---