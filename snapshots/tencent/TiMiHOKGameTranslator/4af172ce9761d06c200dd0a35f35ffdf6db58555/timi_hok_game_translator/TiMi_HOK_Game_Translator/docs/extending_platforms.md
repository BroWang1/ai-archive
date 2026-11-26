# 扩展指南：接入一个新的翻译 / 审校平台

假设你希望把 [Lokalise](https://lokalise.com/) 接进来，让一审或二审走它的
项目工作流。本指南演示如何通过**约 100 行代码** + 一行注册把它接入 `TiMi_HOK_Game_Translator`，
无需改动框架本身。

> 本框架内置两种平台适配器可供参考：[`PhrasePlatform`](../src/TiMi_HOK_Game_Translator/platforms/phrase_platform.py)
> 与 [`CrowdinPlatform`](../src/TiMi_HOK_Game_Translator/platforms/crowdin_platform.py)，`NoopPlatform` 则是 `platform.type: none` 的最小兜底实现。

---

## 1. 继承 `TranslationPlatform`

框架为平台定义了一组极简的协议（见 [`src/TiMi_HOK_Game_Translator/platforms/base.py`](../src/TiMi_HOK_Game_Translator/platforms/base.py)）。
一个合格的平台适配器只需要实现这 5 个必覆盖方法：

| 方法 | 做什么 |
|---|---|
| `upload_source(file_path, *, remote_path)` | 把本地源文件上传成平台上的 "file / job"，返回 `UploadResult(file_id=...)` |
| `create_task(file_ids, target_locale, *, review_stage, title, description)` | 为上传的文件集创建审校任务，返回 `TaskInfo(task_id=...)` |
| `get_task_status(task_id, *, review_stage)` | 轮询任务状态，映射到 `TaskStatus.PENDING/IN_PROGRESS/APPROVED/REJECTED/UNKNOWN` |
| `import_approved(task_id, dest_path, *, review_stage)` | 下载**已批准**译文到本地文件，返回落地路径 |
| `download_translations(file_id, target_locale, dest_path, *, review_stage)` | 按文件维度下载全部译文（无论是否已批准） |
| `export_review_report(task_id, dest_path, *, review_stage)` | 导出可读的审校报告（无 Analytics 接口时可写一个简短 txt） |

另外三个方法已有默认实现，按需覆盖即可：

| 方法 | 默认行为 |
|---|---|
| `split_approved_data(task_id, ...)` | 仅返回 `import_approved` 的结果；平台若能按段级（segment）区分 approved/pending，强烈建议重写 |
| `delete_task(task_id, ...)` / `delete_file(file_id, ...)` | 空实现；若想避免平台项目堆积，覆盖它调用对应 REST DELETE |
| `get_project_name(project_id)` | 回传 `project_id`；想显示人类可读名称可覆盖 |

### 骨架代码

```python
# my_plugin/lokalise_platform.py
from __future__ import annotations

from typing import Sequence
import requests

from TiMi_HOK_Game_Translator.commons import PlatformError, ReviewStage
from TiMi_HOK_Game_Translator.platforms import (
    TranslationPlatform,
    TaskInfo,
    TaskStatus,
    UploadResult,
)


class LokalisePlatform(TranslationPlatform):
    """最小可用的 Lokalise 适配器。"""

    platform_name = "lokalise"
    # 空元组 = 不限制 review_stage；需要只支持某些阶段时填 ("first", "second")。
    supports_stages: tuple = ()

    _STATUS_MAP = {
        "queued": TaskStatus.PENDING,
        "in_progress": TaskStatus.IN_PROGRESS,
        "completed": TaskStatus.APPROVED,
        "cancelled": TaskStatus.REJECTED,
    }

    def _headers(self) -> dict:
        if not self.api_token:
            raise PlatformError("Lokalise api_token is empty")
        return {"X-Api-Token": self.api_token, "Content-Type": "application/json"}

    def _url(self, path: str) -> str:
        base = self.api_base.rstrip("/") or "https://api.lokalise.com/api2"
        return f"{base}{path}"

    # ---- 必覆盖 ----
    def upload_source(self, file_path, *, remote_path=""):
        with open(file_path, "rb") as f:
            data = f.read()
        resp = requests.post(
            self._url(f"/projects/{self.project_id}/files/upload"),
            headers=self._headers(),
            json={"data": data.decode("utf-8"), "filename": remote_path or file_path},
            timeout=60,
        )
        resp.raise_for_status()
        return UploadResult(file_id=str(resp.json()["process"]["id"]))

    def create_task(self, file_ids, target_locale, *,
                    review_stage=ReviewStage.FIRST.value, title="", description=""):
        payload = {
            "title": title or "TiMi_HOK_Game_Translator review",
            "description": description,
            "languages": [{"language_iso": target_locale, "users": []}],
            "source_language_iso": "zh_CN",
            "project_id": self.project_id,
        }
        resp = requests.post(
            self._url(f"/projects/{self.project_id}/tasks"),
            headers=self._headers(), json=payload, timeout=60,
        )
        resp.raise_for_status()
        task = resp.json()["task"]
        return TaskInfo(
            task_id=str(task["task_id"]),
            status=self._STATUS_MAP.get(task.get("status", ""), TaskStatus.UNKNOWN),
            target_locale=target_locale,
            project_id=self.project_id,
            review_stage=review_stage,
        )

    def get_task_status(self, task_id, *, review_stage=ReviewStage.FIRST.value):
        resp = requests.get(
            self._url(f"/projects/{self.project_id}/tasks/{task_id}"),
            headers=self._headers(), timeout=30,
        )
        resp.raise_for_status()
        task = resp.json()["task"]
        return TaskInfo(
            task_id=task_id,
            status=self._STATUS_MAP.get(task.get("status", ""), TaskStatus.UNKNOWN),
            percent_completed=float(task.get("progress", 0)),
            review_stage=review_stage,
        )

    def import_approved(self, task_id, dest_path, *, review_stage=ReviewStage.FIRST.value):
        # Lokalise 没有直接的 "下载 task approved 文件" 接口；
        # 这里演示：先从 task 查到关联 file，再按 file 导出 JSON。
        # 真实实现建议走 /files/download，并过滤 translation.is_reviewed=True。
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write("{}")  # 省略：真实 HTTP + JSON 落盘
        return dest_path

    def download_translations(self, file_id, target_locale, dest_path, *,
                              review_stage=ReviewStage.FIRST.value):
        # 类似 import_approved，不过不过滤 is_reviewed。
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write("{}")
        return dest_path

    def export_review_report(self, task_id, dest_path, *,
                             review_stage=ReviewStage.FIRST.value):
        info = self.get_task_status(task_id, review_stage=review_stage)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(f"task {task_id} progress={info.percent_completed}%\n")
        return dest_path
```

---

## 2. 注册平台名

在包的 `__init__.py` 里一行注册，确保 `TiMi_HOK_Game_Translator` 在工厂构造时能找到它：

```python
# my_plugin/__init__.py
from TiMi_HOK_Game_Translator.platforms import register_platform
from .lokalise_platform import LokalisePlatform

register_platform("lokalise", LokalisePlatform)
```

> 📌 名称大小写不敏感。重复 `register_platform` 以替换内置实现也是允许的
> （适合你需要**覆盖**官方 Phrase 适配器时）。

---

## 3. 让插件被 import 到

和 VCS 扩展一样，`TiMi_HOK_Game_Translator` 并不知道你的插件存在。两种常见做法：

- **自建 CLI 入口**：在自己的 console-script 里 `import my_plugin` 后再调 `TiMi_HOK_Game_Translator.cli.main`；
- **`.pth` 文件**：随 wheel 发一个 `my_plugin.pth`，内容是 `import my_plugin`，解释器启动时自动加载。

---

## 4. 在 YAML 中启用

### 方案 A：全局单一平台

```yaml
# conf/config.yaml
platform:
  type: lokalise
  api_base: https://api.lokalise.com/api2
  api_token: ""            # 走 GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN 环境变量
  project_id: "123456789"
```

然后在语种 profile 里让某阶段**显式继承**（`platform` 字段省略或填 `""`）：

```yaml
# conf/languages/vi.yaml
reviews:
  first:
    platform: ""          # 空 → 回退到全局 platform.type=lokalise
    project_name: VI First
```

### 方案 B：一审 + 二审走不同后端（最常用）

框架为**每个 `review_stage` 独立选择平台**，这是 `build_review_tool` 的核心机制
（见 [`src/TiMi_HOK_Game_Translator/platforms/factory.py`](../src/TiMi_HOK_Game_Translator/platforms/factory.py)）：

```yaml
reviews:
  first:
    platform: phrase          # 一审走 Phrase
    project_id: "<phrase-uid>"
    target_language_id: vi
    extra:
      region: eu
  second:
    platform: lokalise        # 二审走你新接的 Lokalise
    project_id: "123456789"
    target_language_id: vi
```

框架会分别用两个工厂实例，互不干扰。**跨平台保护**：
`build_review_tool` 在回退到全局 `platform` 时，仅当全局 `type` 与阶段
`platform` 相同时才共享 `api_base/api_token/project_id`，避免 "Phrase 用了 Crowdin
token / 请求打到对方 nginx" 这种污染。

### 方案 C：阶段级 fallback（内部状态机使用）

工作流状态可以给 `build_review_tool` 传 `fallback` 参数——当阶段级 `platform`
填 `"none"` 时才启用 fallback 名称。多数业务不需要关心。

---

## 5. 可选：覆盖 `split_approved_data`

默认实现只把 `import_approved` 的结果塞进 `approved_path`，`pending_path` 为空。
如果你的平台能按段级（segment）区分 approved/pending（比如 Crowdin 的
`ApprovalStatus` 列），强烈建议重写：

```python
from TiMi_HOK_Game_Translator.platforms import SplitResult


class LokalisePlatform(TranslationPlatform):
    ...

    def split_approved_data(self, task_id, *,
                            save_approved_path, save_pending_path="",
                            review_stage=ReviewStage.FIRST.value):
        # 1. 拉取 task 全部译文 + 每段 is_reviewed 标记
        rows = self._fetch_task_rows(task_id)
        approved_rows = [r for r in rows if r["is_reviewed"]]
        pending_rows = [r for r in rows if not r["is_reviewed"]]

        self._write_rows(save_approved_path, approved_rows)
        if save_pending_path:
            self._write_rows(save_pending_path, pending_rows)

        return SplitResult(
            approved_path=save_approved_path,
            pending_path=save_pending_path if pending_rows else "",
            should_continue=bool(approved_rows),
            is_complete=not pending_rows,
        )
```

状态机 `FirstReviewState` / `SecondReviewState` 根据 `is_complete` 判断是否
需要**跨天续审**，`should_continue` 决定要不要把当批已 approved 合并回主表。

---

## 6. 可选：删除平台残留文件 / 任务

`delete_task` 和 `delete_file` 默认都是空实现。生产长时间运行时，平台项目目录
很容易被几百份已 split 掉的 xlsx / xml 塞满——建议至少实现 `delete_file`：

```python
def delete_file(self, file_id, *, review_stage=ReviewStage.FIRST.value):
    requests.delete(
        self._url(f"/projects/{self.project_id}/files/{file_id}"),
        headers=self._headers(), timeout=30,
    ).raise_for_status()
```

> ⚠️ **调用顺序**：删 task 之后再删 file。顺序颠倒容易触发平台的
> "文件被 task 引用无法删除" 409 响应。

---

## 7. 测试你的平台

参考 [`tests/unit/test_platform_phrase.py`](../tests/unit/test_platform_phrase.py)
与 [`tests/unit/test_platform_crowdin.py`](../tests/unit/test_platform_crowdin.py)：

- **不要调真实 API**：通过 `extra["session_factory"] = lambda: FakeSession(...)` 注入自定义
  `requests.Session`，`FakeSession` 用 `MagicMock` 返回构造好的响应；
- 至少覆盖：鉴权（含 401 自动刷新）、`upload_source` 成功路径、`get_task_status`
  状态映射、`import_approved` 文件落地、`split_approved_data` 的 approved/pending 拆分、
  网络错误重试；
- 用 `tests/unit/test_platform_factory.py` 的模式检查**工厂级跨平台保护逻辑**
  （全局 Crowdin + 阶段 Lokalise 时不污染 `api_base`）。

---

## 8. 其它参考

- 协议细节：[`src/TiMi_HOK_Game_Translator/platforms/base.py`](../src/TiMi_HOK_Game_Translator/platforms/base.py)
- 工厂与注册表：[`src/TiMi_HOK_Game_Translator/platforms/factory.py`](../src/TiMi_HOK_Game_Translator/platforms/factory.py)
- 内置实现：[`phrase_platform.py`](../src/TiMi_HOK_Game_Translator/platforms/phrase_platform.py) / [`crowdin_platform.py`](../src/TiMi_HOK_Game_Translator/platforms/crowdin_platform.py)
- 平台专项：[Phrase TMS 快速接入](./platforms/phrase.md)
- 快速验证令牌：[`scripts/probe_platform.py`](../scripts/probe_platform.py) 的 `--whoami` 探针