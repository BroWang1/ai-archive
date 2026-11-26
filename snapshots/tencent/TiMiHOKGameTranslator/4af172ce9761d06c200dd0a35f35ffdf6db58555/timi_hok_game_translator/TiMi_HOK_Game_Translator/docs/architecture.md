# 架构

TiMi_HOK_Game_Translator 有**三大骨架**、**六个可插拔层**。任何一次运行都是它们协作的结果。

## 概览

```
                                +-----------------------------+
                                |     WorkflowRunner          |
                                |  按 profile.workflow 编排   |
                                +--------------+--------------+
                                               |
                +------------------------------+------------------------------+
                |                              |                              |
        +-------v-------+             +--------v---------+           +--------v---------+
        | StatesManager |             |  WorkflowContext |           |  AutoSaveDict    |
        | 状态位持久化   |             |  运行时上下文     |           |  业务数据自动落盘 |
        +---------------+             +------------------+           +------------------+
                                               |
      +-------------+----------+---------------+-----------+--------------+--------------+
      |             |          |               |           |              |              |
+-----v----+  +-----v----+ +---v------+  +-----v----+  +---v----+   +-----v-----+  +-----v-----+
| VcsClient|  | LocalSrc | | LLMClient|  | Trans-   |  |Trans-  |   | Notifier  |  |   ...     |
| svn/git  |  | json/... | | mock/    |  | Strategy |  |lation  |   | wecom/... |  |           |
| perforce |  | yaml/xml |  | openai  |  | (语种)   |  |Platform|   |           |  |           |
+----------+  +----------+ +----------+  +----------+  |Phrase/ |   +-----------+  +-----------+
                                                       |Crowdin |
                                                       +--------+
```

## 三大骨架

### 1. `translation/` 独立于 `llm/`：编排层 vs 调用层

- **`translation.BaseTranslationStrategy`（编排层）**：负责 `filter` + `translate` + `process` 三段式、串行/并发执行、去重、兄弟行广播、`post_translate` 钩子、进度回调；
- **`llm.LLMClient`（调用层）**：负责把 prompt 送给具体后端（Mock / OpenAI / 自定义）；
- 语种可以通过 `@register_translation_strategy("vi")` 装饰器自定义策略，也可以只在 JSON 里写 `strategy_config` 就用通用 `GenericTranslationStrategy`。

### 2. `workflow/`：17 个状态族 + JSON 驱动 workflow

- 状态由 `state_registry.register_state("name", cls)` 注册，`build_workflow(profile.workflow)` 按 profile 里的名字列表逐个实例化；
- 每个语种的 pipeline 在 [`conf/languages/<lang>.yaml`](../conf/languages/) 里声明，例如越南语走 11 步双轮审校、日语走 7 步单轮审校；
- 完整状态列表见 [state_registry.md](./state_registry.md)。

### 3. `platforms/`：`review_stage` 首次成为一等公民

- `TranslationPlatform` 的每个方法都接受关键字 `review_stage`（`light` / `first` / `second`）；
- `build_review_tool(profile, "first")` 会按 `profile.reviews["first"].platform` 选择平台实例；
- 内置两个平台：**Phrase TMS**（原 Memsource）与 **Crowdin API v2**；
- 一审二审可以走**完全不同的后端**（例如一审 Phrase、二审 Crowdin）。

## 断点续跑

两个文件承担不同的持久化职责：

| 文件 | 内容 | 由谁写 |
|---|---|---|
| `workspace/workflow_state.json` | 每个状态的完成标记（`{status: {name: True/False}, metadata: {...}}`）| `StatesManager` |
| `workspace/project_run_data.json` | 业务数据（`task_id / approved_path / stats / errors`）| `AutoSaveDict`（每次变更即落盘） |

不带 `--fresh` 再次运行时：
- 已完成状态自动跳过；
- `AutoSaveDict` 已保存的 `task_id` 会被 `FirstReviewState / SecondReviewState` 识别并复用，不会重复上传。

## 六个可插拔层

| 层 | 抽象基类 | 内置实现 | 用户如何扩展 |
|---|---|---|---|
| VCS | `vcs.VcsClient` | `svn / git / perforce / mock` | 继承基类实现 `checkout / update / commit / cleanup` |
| 源文件 | `sources.LocalizationSource` | `json / yaml / xml / csv / dtxml / xliff` | `@register_source("format")` |
| LLM | `llm.LLMClient` | `mock / openai` | `@register_llm("provider")` |
| 翻译策略 | `translation.BaseTranslationStrategy` | `GenericTranslationStrategy` | `@register_translation_strategy("lang")` |
| 审校平台 | `platforms.TranslationPlatform` | `none / phrase / crowdin` | `@register_platform("name")` |
| 通知 | `notify.Notifier` | `wecom / slack / email / console` | `@register_notifier("type")` |

## 关键约束

1. **零私密信息**：所有敏感字段（`api_token / password / webhook`）通过 `.env` 或 CLI 传入；`config dump` 自动脱敏。
2. **状态即位图**：`StatesManager` 只记录布尔完成位，不夹带业务；业务全部走 `AutoSaveDict`。
3. **`review_stage` 决定平台**：state 类通过 `build_review_tool(profile, stage)` 拿平台实例，不直接依赖具体 SDK。
4. **一切名字可注册**：`register_state / register_platform / register_translation_strategy / register_llm / register_source / register_notifier` 六个装饰器让整个框架可被外部完全扩展，无需 fork 源码。

