# LQA AI 识别服务

![License](https://img.shields.io/badge/license-Apache%202.0-blue)

LQA 平台的 AI 识别后端, 基于 Flask, 平台通过 `AI_BASE_URL` 调用本服务完成本地化异常检测

## 功能

1. **LQA 本地化文本异常检测** `POST /image/lqa_check/`
   - 支持多语种
   - 支持多类型检测: 文本超文本框、文本超图像框、漏 key、漏译、错译及其他自定义异常类型

2. **图像前景提取** `POST /image/image_extraction/`
   - 只支持含 alpha 通道的 `.png` 格式图像

---

## 快速开始

```bash
cd lqa_service

python -m venv .venv
.venv\Scripts\activate                      # Linux/macOS: source .venv/bin/activate

pip install -r requirements.txt
pip install rapidocr-onnxruntime            # 默认 OCR 引擎, 离线可用

python portal.py                            # 监听 0.0.0.0:8086
```

自检 OCR 是否就绪:

```bash
python tests/check_ocr.py          # 检测当前配置
python tests/check_ocr.py --list   # 列出全部可选引擎
```

跑完整冒烟测试:

```bash
python tests/gen_samples.py                     # 首次需先生成测试样例
python tests/smoke_test.py 127.0.0.1:8086 lqa
```

---

## OCR 引擎选择

OCR 是**可选**能力, 未配置时服务仍可正常启动并完成大部分检测, 只会自动跳过, 必须依赖 OCR 的检测项 (见下方「OCR 不可用时的降级行为」)

依赖 OCR 的检测需要同时拿到 **文本内容 + 精确边界框**, 因此只支持能同时提供两者的 OCR, 通过环境变量 `OCR_PROVIDER` 切换, 默认 `rapidocr`

| `OCR_PROVIDER` | 类型 | 离线 | 安装 | 说明 |
|---|---|---|---|---|
| `rapidocr` | 开源 | ✅ | `pip install rapidocr-onnxruntime` | **推荐**, PaddleOCR 模型的 ONNX 推理版, 约 15MB，CPU 即可, 中英文效果好 |
| `paddleocr` | 开源 | ✅ | `pip install paddleocr paddlepaddle` | 精度最高, 中日韩支持好; 依赖较重 (约 2GB) |
| `paddleocr_http` | 开源 | ✅ | 无 | 调用独立部署的 PaddleOCR hubserving/PaddleX 服务, 适合 GPU 集中推理 |
| `easyocr` | 开源 | ✅ | `pip install easyocr` | 支持 80+ 语种, 泰文/越南文等小语种可选它 |
| `tesseract` | 开源 | ✅ | `pip install pytesseract` + 安装 tesseract | 老牌引擎; **对游戏 UI 的复杂背景、艺术字识别率明显偏低**, 仅建议简单场景 |
| `tencentcloud` | 商业 | ❌ | `pip install tencentcloud-sdk-python-ocr` | 腾讯云通用印刷体识别 |
| `baidu` | 商业 | ❌ | 无 | 百度智能云通用文字识别 (含位置) |
| `azure` | 商业 | ❌ | 无 | Azure AI Vision Read API |
| `cvtest` | 自建 | ❌ | 无 | 兼容内网自建 OCR 服务协议 |
| `none` | — | ✅ | 无 | **显式关闭 OCR**, 不产生任何识别调用 |

> 游戏本地化场景文本密集、字体特殊, 建议优先 `rapidocr` 或 `paddleocr`, 商业 API 按量计费, 批量识别需评估成本与 QPS 限制

### OCR 不可用时的降级行为

以下任一情况都视为「OCR 不可用」, 服务 **不会报错**, 而是自动降级:

- `OCR_PROVIDER=none` 或留空 (显式关闭)
- `OCR_PROVIDER` 名称写错
- 选定的引擎未安装 (如未 `pip install rapidocr-onnxruntime`)
- 云服务密钥缺失、外部 OCR 服务连不通

降级后各检测类型的可用性:

| 检测类型 | 需要 OCR | 降级后 |
|---|---|---|
| 1 漏译 (`##` 等标记) | ❌ | ✅ 正常 |
| 2-0 文本超文本框 | ✅ | ⛔ 跳过 |
| 2-1 文本框与图像框重叠 | ❌ | ✅ 正常 |
| 3 漏 key | ❌ | ✅ 正常 |
| 4 文本框重叠 | ❌ | ✅ 正常 (纯几何) |
| 5 错译 | ✅ | ⛔ 跳过 |
| 6 non_problem | ❌ | ✅ 正常 |
| 7 非标准框 | ❌ | ✅ 正常 |

降级时响应体额外返回三个字段, 便于调用方识别:

```json
{
  "success": true,
  "result": {
    "ocr_degraded": true,
    "ocr_message": "未配置 OCR (OCR_PROVIDER=none), 依赖 OCR 的检测项将跳过",
    "skipped_check_type": ["2-0", "5"]
  }
}
```

`GET /health` 始终返回 200 (服务本身健康), OCR 状态在 `ocr` 字段中体现:

```json
{"status": "ok", "ocr": {"available": false, "message": "...", "degraded": true}}
```

探测结果在进程内缓存 (成功 1 小时, 失败 60 秒后重试), 不会给每个请求带来额外开销, 可用 `python tests/check_ocr.py` 单独自检当前配置

### 配置示例

**完全不使用 OCR**

```bash
export OCR_PROVIDER=none
```

**离线 (推荐, 无任何外部依赖)**

```bash
export OCR_PROVIDER=rapidocr
```

**PaddleOCR 本地**

```bash
export OCR_PROVIDER=paddleocr
export OCR_LANG=ch          # ch / en / japan / korean / fr / german ...
export OCR_USE_GPU=false
```

**PaddleOCR 独立服务**

```bash
export OCR_PROVIDER=paddleocr_http
export OCR_URL=http://<paddle-host>:8868/predict/ocr_system
```

**腾讯云**

```bash
export OCR_PROVIDER=tencentcloud
export OCR_SECRET_ID=xxx
export OCR_SECRET_KEY=xxx
export OCR_REGION=ap-guangzhou
```

**百度**

```bash
export OCR_PROVIDER=baidu
export OCR_API_KEY=xxx
export OCR_SECRET_KEY=xxx
```

**自建 / 内网服务**

```bash
export OCR_PROVIDER=cvtest
export OCR_HOST=http://<ocr-host>:80
export OCR_DEFAULT_PROJECT=lqa     # 该服务用 project-method 头鉴权
```

### 接入自定义 OCR

实现 `common/ocr_provider/base.py` 中的 `OcrProvider`, 返回统一结构即可:

```python
[{"area": [x1, y1, x2, y2], "result": "识别出的文本"}, ...]
```

然后在 `common/ocr_provider/__init__.py` 的 `PROVIDERS` 中注册

---

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEBUG_MODE` | `True` | `True` 时 `python portal.py` 直接启动开发服务器 (容器内已置为 `False`, 由 gunicorn 托管) |
| `OCR_PROVIDER` | `rapidocr` | OCR 引擎, 见上表; `none`/留空表示不使用 OCR |
| `OCR_URL` | 空 | HTTP 型 OCR 服务地址 |
| `OCR_HOST` | 空 | 服务 endpoint (`cvtest` / `azure` 使用) |
| `OCR_LANG` | `ch` | 识别语种 (本地引擎) |
| `OCR_USE_GPU` | `false` | 本地引擎是否用 GPU |
| `OCR_TIMEOUT` | `60` | 远程 OCR 超时 (秒) |
| `OCR_API_KEY` / `OCR_SECRET_ID` / `OCR_SECRET_KEY` | 空 | 云厂商鉴权 |
| `OCR_REGION` | `ap-guangzhou` | 腾讯云地域 |
| `OCR_TESSERACT_CMD` | 空 | tesseract 可执行文件路径 |
| `OCR_DEFAULT_PROJECT` | 空 | `cvtest` 的默认项目标识 |
| `LOG_PATH` | `./log` | 日志目录 |
| `BIND` | `0.0.0.0:8086` | gunicorn 监听地址 |
| `GUNICORN_WORKERS` | `3` | gunicorn worker 数 |
| `NO_TRANS_MARK_LIST` | `["##","#N","WWWW","N/A"]` | 漏译标记 |
| `ERROR_TRANS_MARK_LIST` | `["</",["color","#"]]` | 错译标记 |

测试脚本也支持 `LQA_TEST_HOST` / `LQA_TEST_PORT` / `LQA_TEST_DATA_DIR` / `LQA_TEST_PROJECT` 覆盖

---

## 生产部署

```bash
bash deploy/run_gunicorn.sh
# 等价于: gunicorn -c config/gunicorn_config.py portal:app --preload
```

> `gunicorn` + `gevent` 不支持 Windows, Windows 下请用 `python portal.py`

### 容器部署

```bash
# 默认内置 rapidocr, 开箱即可离线运行
docker build -t lqa-ai-service .

# 内置 PaddleOCR (镜像约 +2GB, 精度更高)
docker build --build-arg OCR_ENGINE=paddleocr -t lqa-ai-service:paddle .

# 不内置任何引擎 (镜像最小; 可指向外部 OCR, 或完全不用 OCR)
docker build --build-arg OCR_ENGINE=none -t lqa-ai-service:slim .

docker run -d -p 8086:8086 -e OCR_PROVIDER=rapidocr lqa-ai-service
```

---

## 调用约定

### 请求头

```
project-method: <项目名>_lqa
```

服务会剥离 `_lqa` 后缀得到项目名, 传递给 OCR provider, `cvtest` 等依赖该标识鉴权的服务必须传; 离线引擎可省略

LQA 平台侧对应 "项目设置" 中的 **AI识别项目名**

### 请求体

```json
{
  "img_base64": "当前截图 base64",
  "rect_locations": { "text": [...], "image": [...] },
  "language": null,
  "supervised": null,
  "check_type": ["1", "2-0"],
  "history_img_base64": null,
  "history_result": null,
  "no_trans_marks": [],
  "error_trans_marks": [],
  "ocr_detect": 1
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `img_base64` | string | 必填, 待检测截图 |
| `rect_locations` | **object** | 必填, `{"text": [...], "image": [...]}`, 注意是对象不是数组 |
| `language` | int | 语种, 见下方枚举，`null` 为不限 |
| `check_type` | list[str] | 指定检测类型, `null` 为全部 |
| `ocr_detect` | int | `1` 文本框非精确位置需 OCR 定位 (默认); `0` 文本框已是最小外接矩 |
| `history_img_base64` | string | 差异识别时的上一次截图 |

> 注意: `ocr_detect=0` 分支 **同样会调用 OCR** (用于错译检测), 只是不再用 OCR 结果做位置校准

### 响应体

```json
{
  "success": true,
  "err_msg": null,
  "result": {
    "overframe": false,
    "mark_img": "标注后图片 base64",
    "rect_img": "文本框图片 base64",
    "check_detail": {}
  }
}
```

### 枚举

**检测类型 (`check_type`)**

| 值 | 说明 |
|---|---|
| `1` | 漏译 |
| `2` | 超框 (`2-0` 文本超文本框, `2-1` 文本超图像框) |
| `3` | 漏 key |
| `4` | 文本框重叠 |
| `5` | 错译 |
| `6` | non_problem 自定义 |
| `7` | 非标准框 |

**语种 (`language`)**

| 值 | 语种 |
|---|---|
| `0` | 简体中文 |
| `1` | 繁体中文 (台湾) |
| `2` | 英文 |
| `3` | 日文 |
| `4` | 泰文 |
| `5` | 越南文 |

---

## 测试样例

真实游戏截图与 UI 文案涉及版权, **未随仓库发布** (`tests/test/` 已在 `.gitignore` 中排除), 仓库提供生成器, 用 OpenCV 合成结构等价的样例:

```bash
python tests/gen_samples.py            # 生成到 tests/test/
python tests/gen_samples.py --force    # 覆盖已有样例
```

生成的场景:

| case | 场景 | 预期 |
|---|---|---|
| 0 | 正常界面 | 无异常 |
| 1 | 标准框小于文本 | 可能触发超框 (取决于 OCR 实际识别区域与阈值) |
| 2 | 含 `##` / `N/A` 标记 | 检出漏译 (类型 1) |
| 3 | `textStr` 缺失 / 空串 | 不崩溃且无异常 |
| 4 | 标准框相交 | 可能触发重叠 |
| 5 | 密集文本 | 压力场景 |
| 6 | 非中文界面混入简体中文 | 检出漏 key (类型 3) |

> 合成图使用 OpenCV 内置字体, 仅含拉丁字符, 与真实游戏的艺术字、复杂背景差异较大, 它用于验证 **服务链路与接口契约** 是否正常, 不能用来评估检测算法的实际准确率, 调优算法请使用自有的真实截图

### 关于标准数据中的空文本

`rect_locations.text[*].textStr` 允许为 `None` / 空串, 表示该文本框未提供文本内容, 此时依赖文本内容的检测项 (漏译、漏 key、错译、non_problem) 会跳过该文本框,
不依赖文本的检测项 (超框、重叠、非标准框) 仍正常进行

---

## 与 LQA 平台对接

```bash
# LQA-OSS/.env
AI_BASE_URL=http://<本服务地址>:8086
```

平台会调用 `POST {AI_BASE_URL}/image/lqa_check/`, 并自动带上 `project-method: <AI识别项目名>_lqa` 请求头

---