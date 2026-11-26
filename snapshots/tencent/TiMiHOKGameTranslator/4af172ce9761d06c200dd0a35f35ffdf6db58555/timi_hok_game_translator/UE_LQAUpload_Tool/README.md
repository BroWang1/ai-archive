# UE LQA Dump 数据上传工具

![License](https://img.shields.io/badge/license-Apache%202.0-blue)

通用、配置驱动的 LQA UI-dump 数据上传脚本, 扫描数据目录中由 LQA 采集工具产出的 dump 记录, 将快照 JSON 规整为平台所需结构后, 通过 HTTP API 逐条上传

## 目录结构

```
UE_LQAUpload_Tool/
├── ue_lqa_upload_tool.py   # 主脚本
├── LQAConfig.ini           # 配置模板
└── README.md
```

## 一条有效 dump 记录

脚本把一个「子目录」视为一条记录, 目录中需至少包含:

| 文件 | 说明 | 是否必需 |
| --- | --- | --- |
| `*.json` (`upload.json` 除外) | UI 快照数据 | 必需 |
| `LQA_ScreenShot_*.png` | 截图 | 必需 |
| `*_BG.png` | 背景图 | 可选（`require_background` 控制） |
| `Texture_*.png` | 纹理图 | 可选 (`require_texture` 控制) |

## 平台 API 契约

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/api/user/login` | dev 自动登录 (无 Token 时使用) |
| POST | `/api/data/entity` | 创建数据实体, 返回 `data_id` |
| POST | `/api/upload_file` | 上传文件, 返回远端 `file_path` |
| PATCH | `/api/data/entity` | 回填截图 / module_id / resource_version |

有 Token 时, 所有请求携带请求头 `LQA-Authorization: <token>`

## JSON 规整逻辑

对每个快照 JSON 做如下处理 (字段存在时才转换, 缺失则跳过):
1. 将 `nan` / `inf` 等非法 token 替换为 `0`, 保证严格 JSON 可解析;
2. `meta` → `gameData`;
3. `gameData.version` → `gameData.resourceVersion`;
4. `gameData.device` → `phoneType`;
5. 写入 `name` = JSON 文件名;
6. 若开启 `embed_background` 且存在背景图, 写入 `bg_data` (hex)

## 使用

### 1. 安装依赖

```bash
pip install requests
```

### 2. 修改配置

编辑 `LQAConfig.ini`, 至少填写 `host`、`project_id`、`job_id`、`root_path`

### 3. 运行

```bash
# 使用同目录下 LQAConfig.ini
python ue_lqa_upload_tool.py

# 指定配置文件
python ue_lqa_upload_tool.py -c /path/to/LQAConfig.ini

# 临时覆盖数据根目录
python ue_lqa_upload_tool.py --root /path/to/data

# 输出调试日志
python ue_lqa_upload_tool.py -v
```

## 输出

上传完成后，在 `root_path` 下生成 / 合并 `upload.json`，内容为 `data_id -> 源目录` 的映射, 便于后续反查与去重

## 配置项说明

见 `LQAConfig.ini` 内注释, 关键项:
- `server.token`: 留空则走 dev 自动登录;
- `data.scan_mode`: `recursive`（默认）或 `flat`;
- `options.require_background` / `require_texture`: 控制记录有效性判定;
- `options.embed_background`: 是否把背景图内嵌进上传数据;
- `options.retry_times`: 单条失败重试次数
