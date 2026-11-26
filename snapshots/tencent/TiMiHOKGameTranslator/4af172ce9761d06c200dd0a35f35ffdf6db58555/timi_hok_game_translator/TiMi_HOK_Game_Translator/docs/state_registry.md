# 17 个通用状态族

`TiMi_HOK_Game_Translator` 内置 17 个通用状态，覆盖游戏本地化管线的绝大多数环节。每个状态都是**通用的**——不假设具体产品/游戏、不硬编码 Excel 列名、不绑死某个翻译平台。你可以只挑选自己需要的状态，通过 `configs/languages/<lang>.json` 的 `workflow` 字段自由编排。

## 状态一览

| 状态名（配置里用） | 类 | 职责摘要 |
|---|---|---|
| `pull_vcs` | `PullVcsState` | 从 VCS 拉/更新工作副本；调用 `source.load()` 载入 entries |
| `last_first_review` | `LastFirstReviewState` | 处理上一轮遗留的一审 pending 数据 |
| `last_second_review` | `LastSecondReviewState` | 处理上一轮遗留的二审 pending 数据 |
| `last_merge_data` | `LastMergeDataState` | 合并上一轮已通过的数据 |
| `translate` | `TranslateState` | 调用注册到语种的 `BaseTranslationStrategy` 翻译所有 entries |
| `light_review` | `LightReviewState` | 轻量校对—— 未配置时自动跳过 |
| `update_tm` | `UpdateTmState` | 更新本地 TM —— 默认 no-op，用户替换实现 |
| `update_grn_tm` | `UpdateGrnTmState` | 更新伙伴/远端 TM —— 默认 no-op |
| `increment_match` | `IncrementMatchState` | 当日增量字符超阈值时触发的 TM 匹配 sweep |
| `first_review` | `FirstReviewState` | 第一轮正式审校（`review_stage="first"`）|
| `second_review` | `SecondReviewState` | 第二轮正式审校（`review_stage="second"`）—— 未配置平台时跳过 |
| `merge_data` | `MergeDataState` | 汇总两轮审校的 approved 数据 |
| `validate_data` | `ValidateDataState` | 基础质量校验：非空 key、非空 target_text、去重 |
| `push_vcs` | `PushVcsState` | 把 entries dump 回源文件并 commit 到 VCS |
| `push_multi_vcs` | `PushMultiVcsState` | 遍历 `profile.multi_publish_targets` 多路径发布 |
| `finished` | `FinishedState` | 终态：flush AutoSaveDict + StatesManager，触发 `vcs.cleanup()` + notify |
| `pending` / `failed` | (无对应类) | 生命周期枚举保留字，不作为可编排状态 |

## 配置样例：完整双轮审校

```json
{
  "id": "example_vi",
  "workflow": [
    "pull_vcs",
    "last_first_review",
    "last_second_review",
    "last_merge_data",
    "translate",
    "light_review",
    "first_review",
    "second_review",
    "validate_data",
    "push_vcs",
    "push_multi_vcs"
  ]
}
```

## 配置样例：轻量单轮

```json
{
  "id": "example_ja",
  "workflow": [
    "pull_vcs",
    "translate",
    "first_review",
    "validate_data",
    "push_vcs"
  ]
}
```

## 断点续跑约定

每个状态在 `execute()` 首行都会调用 `self._already_completed(ctx)`：如果 `StatesManager` 已把它标记为完成，就直接 `return None` 跳过。这意味着：

- 崩溃后 `python main.py run`（不带 `--fresh`）会自动从上次未完成状态继续；
- Task id / approved_path 等业务字段由 `AutoSaveDict` 存进 `project_run_data.json`，`FirstReviewState` 检测到 `first_review.task_id` 已存在时会**复用**该任务而不是新建。

## 自定义状态

通过 `register_state`（支持 `replace=True`）替换任一内置状态：

```python
from TiMi_HOK_Game_Translator.workflow import register_state, WorkflowStateBase
from TiMi_HOK_Game_Translator.commons import WorkflowState


class MyMergeData(WorkflowStateBase):
    name = WorkflowState.MERGE_DATA.value

    def execute(self, ctx):
        # 用 pandas 做业务专属的 DataFrame 合并
        ...
        self._mark_completed(ctx)


register_state(WorkflowState.MERGE_DATA.value, MyMergeData, replace=True)
```

新增自定义状态：

```python
register_state("my_glossary_check", GlossaryCheckState)
# 然后在 <lang>.json 的 workflow 里插入 "my_glossary_check"
```
