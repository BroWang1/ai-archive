# 配置详解

本页集中介绍 `TiMi_HOK_Game_Translator` 的三份 YAML 配置：

```
conf/
├── config.yaml           # 主运行配置（VCS / platform / notification / workspace / logging）
├── llm.yaml              # LLM 模型注册表（跨业务项目共享的模型 profile）
└── languages/
    ├── <lang>.yaml       # 单个语种 profile（source / reviews / workflow / strategy）
    └── ...
```

> 📌 整体心智模型：**全局 `config.yaml` 定下框架默认值，语种 profile 可覆盖/新增，`llm.yaml` 以 "profile 名" 形式被前两者按名引用。**

- [1. `conf/config.yaml` — 主运行配置](#1-confconfigyaml--主运行配置)
- [2. `conf/llm.yaml` — LLM profile 注册表](#2-confllmyaml--llm-profile-注册表)
- [3. `conf/languages/<lang>.yaml` — 语种 profile](#3-conflanguageslangyaml--语种-profile)
- [4. 源文件格式（source）参考](#4-源文件格式source参考)
- [5. 敏感字段与环境变量注入](#5-敏感字段与环境变量注入)
- [6. 为什么 `platform` 不区分一审 / 二审？](#6-为什么-platform-不区分一审--二审)

---

## 1. `conf/config.yaml` — 主运行配置

**作用**：定义**全局默认**的 VCS、翻译/审校平台、通知渠道、workspace 位置与日志，供所有语种 profile 继承。
**运行时覆盖优先级**：`环境变量` > `命令行参数` > `conf/languages/<lang>.yaml` > `conf/config.yaml`。

### 1.1 顶层字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `project_code` | str | ✅ | - | 产品 slug，出现在日志前缀、通知标题、状态文件名 |
| `stage` | enum | ❌ | `trunk_week` | 运行阶段，可选 `exp_week` / `trunk_week` / `pub_week` / `hot_week`，可被 `--stage` 覆盖 |
| `source_locale` | str | ❌ | `zh-CN` | 源语种 BCP-47 代码；目标语种由各语种 profile 的 `target_locale` 决定 |
| `languages_dir` | str | ❌ | `conf/languages` | 扫描语种 profile 的目录（支持 `*.yaml` / `*.json`） |

### 1.2 `vcs` — 版本控制

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | enum | ✅ | `svn` / `git` / `perforce` / `mock`；用 `mock` 做零依赖试跑 |
| `url` | str | ✅ | 远端仓库地址 |
| `revision` | str | ❌ | 签出修订号，默认 `HEAD` |
| `local_path` | str | ✅ | **相对路径**，factory 自动拼接 `workspace` 根；**不要加 "workspace/" 前缀** |
| `username` / `password` | str | 🔒 | 凭据，**走环境变量 `GAME_TRANS_TOOLCHAIN__VCS__USERNAME` / `GAME_TRANS_TOOLCHAIN__VCS__PASSWORD`** |
| `cli_timeout_seconds` | int | ❌ | 单条 CLI 调用超时，默认 600 |
| `default_commit_message` | str | ❌ | `push_vcs` 阶段提交消息兜底 |

> SVN 遇 `wc locked / E155004` 时跑 `svn cleanup <local_path>`；**不要用 `svn status` 判断是否锁定**，`svn update` 或 `svn info` 更可靠。

#### VCS 配置示例

<details>
<summary><b>Git</b></summary>

```yaml
vcs:
  type: git
  url: https://github.com/YOUR_ACCOUNT/game-i18n.git
  local_path: workspace/repo
  # revision: main              # 可选，默认 HEAD
  default_commit_message: "chore(i18n): TiMi_HOK_Game_Translator auto commit"
```

</details>

<details>
<summary><b>SVN</b></summary>

```yaml
vcs:
  type: svn
  url: https://svn.example.com/game-i18n/trunk
  local_path: workspace/repo
  # username: your-svn-user     # 🔒 GAME_TRANS_TOOLCHAIN__VCS__USERNAME
  # password: your-svn-pass     # 🔒 GAME_TRANS_TOOLCHAIN__VCS__PASSWORD
  revision: HEAD
  default_commit_message: "chore(i18n): TiMi_HOK_Game_Translator auto commit"
```

</details>

<details>
<summary><b>Perforce</b></summary>

```yaml
vcs:
  type: perforce
  url: "perforce.example.com:1666"            # P4PORT
  local_path: workspace/repo                  # 本地映射目录（client root）
  # username / password 🔒 走环境变量
  extra:
    client: game-i18n-workspace               # p4 client 名
    stream: "//depot/game-i18n/main"          # 流式仓库
    charset: utf8
```

</details>

<details>
<summary><b>Mock（零依赖试跑）</b></summary>

```yaml
vcs:
  type: mock
  url: mock://local
  local_path: "."                             # 相对 cwd；不实际克隆
```

该模式配合 `platform.type: none` + `llm.provider: mock` 即可无网络跑通
整条流水线，适合首次验证安装。见 [快速开始](./quickstart.md)。

</details>


### 1.3 `source` — 全局源文件默认

多数情况下这段**只做新建语种的"复制起点"**，真实路径以 `conf/languages/<lang>.yaml` 的 `source` 为准。

```yaml
source:
  format: json          # xlsx | json | yaml | xml | csv | dtxml | xliff
  path: "vi/json/99.incr.json"   # 相对 vcs.local_path
  encoding: utf-8
```

### 1.4 `llm_profile` — 默认 LLM

```yaml
llm_profile: hunyuan_mt2_plus   # 必须在 conf/llm.yaml 的 profiles 下存在
```

单个语种若需换模型，到 `conf/languages/<lang>.yaml` 覆盖同名字段即可。

### 1.5 `platform` — **全局默认审校平台**

```yaml
platform:
  type: crowdin                    # crowdin | phrase | none | <自定义名>
  api_base: "https://api.crowdin.com/api/v2"
  api_token: ""                    # 🔒 GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN
  project_id: ""
  extra: {}                        # 平台专属扩展
```

> ⚠️ 本配置**不区分一审 / 二审** —— 它只是全局兜底。真正的"一审走 Phrase + 二审走 Crowdin"配置在
> `conf/languages/<lang>.yaml` 的 `reviews.first` / `reviews.second`。详情见第 6 节。

### 1.6 `notification` — 通知渠道

```yaml
notification:
  type: none            # none | wecom | console
  webhook: ""           # 🔒 GAME_TRANS_TOOLCHAIN__NOTIFICATION__WEBHOOK
```

### 1.7 `workspace` 与 `logging`

```yaml
workspace:
  root: ""                               # 空 → ${CWD}/workspace
  subdir: workspace
  state_filename: workflow_state.json    # 断点续跑状态持久化文件名

logging:
  level: INFO                            # DEBUG | INFO | WARNING | ERROR
  directory: logs
  filename: TiMi_HOK_Game_Translator.log
  console: true
```

---

## 2. `conf/llm.yaml` — LLM profile 注册表

**作用**：集中维护所有可用模型 "profile"，业务配置按名引用，避免每个语种重复写一遍 `api_base` / `temperature` 等。

### 2.1 顶层结构

```yaml
default: openai_gpt4o_mini       # config.yaml / 语种 profile 都没指定时的兜底
profiles:
  <profile_name>:
    provider: openai             # openai | openai_compatible | anthropic | venus | hunyuan_translation | mock
    model: gpt-4o-mini
    api_base: ""
    api_key: ""                  # 🔒 GAME_TRANS_TOOLCHAIN__LLM__API_KEY
    temperature: 0.2
    max_tokens: 1024
    batch_size: 32
    timeout_seconds: 30
    retries: 3
    retry_interval_seconds: 30
    extra: {}                    # provider 专属字段
```

### 2.2 字段逐项

| 字段 | 必填 | 说明 |
|---|---|---|
| `provider` | ✅ | 决定走哪个 `LLMClient` 实现；详见 [`docs/extending_llm.md`](./extending_llm.md) |
| `model` | ✅ | 模型名；venus / hunyuan_translation 走的是服务端模型 ID |
| `api_base` | ⚠️ | OpenAI 系省略即走官方 endpoint，其它必填 |
| `api_key` | 🔒 | 走环境变量注入；venus 用 `secret_id:secret_key` 形式 |
| `temperature` | ❌ | 翻译建议 `0.1 ~ 0.3` 之间 |
| `max_tokens` | ❌ | 单次响应上限；长文本可设 4096 |
| `batch_size` | ❌ | 单次打包多少条 Entry（框架按此分批） |
| `timeout_seconds` | ❌ | 单次 HTTP 超时 |
| `retries` / `retry_interval_seconds` | ❌ | 网络抖动重试 |
| `extra` | ❌ | provider 专属，常见键见下表 |

### 2.3 常用 `extra` 键

| provider | 键 | 说明 |
|---|---|---|
| `venus` | `server_id` / `app_group_id` | Venus 平台模型路由 |
| `venus` | `secret_id` / `secret_key` | 鉴权（也可合并到 `api_key`） |
| `venus` | `model_params.top_p / top_k / repetition_penalty / do_sample` | 解码参数 |
| `hunyuan_translation` | `wsid` | HY-MT 工作空间 ID（必填） |
| `hunyuan_translation` | `top_p / top_k / repetition_penalty / reasoning_effort / system_prompt / stream` | HY-MT 解码参数 |

---

## 3. `conf/languages/<lang>.yaml` — 语种 profile

**作用**：接入一门新语种的**唯一**入口。日常改动最多的文件。

### 3.1 基础字段

```yaml
id: vi                      # 必填：语种短 ID（与文件名一致）
display_name: 越南语        # 日志 / 通知使用的中文名
source_locale: zh-CN
target_locale: vi
locale_names:
  cn: 越南语                # 用于提示词
  en: Vietnamese
```

### 3.2 `source` — 本语种源文件

```yaml
source:
  format: json              # 覆盖全局 config.yaml 的 source.format
  path: trunk/tests/fixtures/vi/99.incr.json   # 相对 vcs.local_path
  encoding: utf-8
```

> 👉 可用的 `format` 值与各格式的字段约定见 [第 4 节](#4-源文件格式source参考)。

### 3.3 `vcs` — 可选，覆盖全局

多数语种共用一个 svn 工作副本时留空；需要本语种独立 VCS 时填：

```yaml
vcs:
  url: "svn://..."
  local_path: svn/vi_dedicated
```

### 3.4 `llm_profile` 与 `strategy_config` — 翻译

```yaml
llm_profile: hunyuan_mt2_plus     # 必须在 conf/llm.yaml 中存在

strategy_config:
  # ① 短名   —— GenericTranslationStrategy / TwoStepTranslationStrategy / generic / two_step
  # ② 完整导入路径 —— my_pkg.strategies.MyStrategy
  # 省略 class 字段 → 走装饰器注册表，再兜底 Generic
  class: TwoStepTranslationStrategy
  pivot_locale: en                # 两步策略专属，默认 en
  display_name: 越南语翻译
  use_concurrent_by_default: true
  default_max_workers: 32
  progress_log_interval: 100
```

详细说明见 [`README.md`](../README.md#-翻译策略选择指南) 的"翻译策略选择指南"。

### 3.5 `reviews` — **一审 / 二审 / 轻校对配置**

这是语种 profile 里**最容易踩坑**的一段。核心约定：

- **每个审校阶段独立选择平台**，互不影响；
- `platform: none`（或字段省略）即跳过该阶段；
- 阶段级 `api_token` / `api_base` 为空且**全局 `platform.type` 等于本阶段 `platform`** 时，自动继承全局的凭据（避免跨平台污染）；
- `extra.target_language_id` 是**平台侧**的语种 ID（与 BCP-47 可能不同，比如 Phrase 用 `vi`、Crowdin 用 `vi`，但有的平台会用数字 ID）。

```yaml
reviews:
  light:
    platform: none
    project_name: VI_LightReview

  first:                           # 一审
    platform: phrase
    project_id: ""                 # Phrase project UID
    project_name: VI First Review (Phrase)
    target_language_id: vi
    poll_interval_seconds: 60
    stop_time: "17:00"             # "HH:MM" 绝对或 "+5m"/"+2h" 相对
    extra:
      region: eu                   # Phrase 专属：eu / us
      subject_token: ""            # 🔒 可改走 GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN

  second:                          # 二审
    platform: crowdin
    project_id: ""
    project_name: VI Second Review (Crowdin)
    target_language_id: vi
    poll_interval_seconds: 60
    stop_time: "18:00"
```

### 3.6 `notification` — 覆盖全局通知

```yaml
notification:
  type: wecom
  webhook: ""                      # 🔒 GAME_TRANS_TOOLCHAIN__NOTIFICATION__WEBHOOK
  mentioned:                       # 审校关键节点 @ 的企业微信用户
    - some_user_id
```

### 3.7 `workflow` — 工作流编排

按声明顺序执行；每个条目都是已注册的状态名。常见组合：

```yaml
# 完整链路（一审 + 二审）
workflow:
  - last_first_review              # 续审昨日未完成的一审任务
  - last_second_review             # 续审昨日未完成的二审任务
  - pull_vcs
  - last_merge_data                # 续审任务到位后先合并
  - translate
  - light_review                   # 轻校对（可省）
  - update_tm                      # 一审 TM 回灌
  - first_review
  - update_grn_tm                  # 二审 TM 回灌
  - second_review
  - validate_data
  - merge_data
  - push_vcs

# 仅翻译 + 推送（跳过所有审校），例如 ar.yaml
workflow:
  - pull_vcs
  - translate
  - merge_data
  - push_vcs
```

内置状态清单见 [`state_registry.md`](./state_registry.md)。

### 3.8 `merge_start_time`

```yaml
merge_start_time: ""     # 空 → 立即执行；"08:30" → 等到当日 08:30 之后再合并
```

---

## 4. 源文件格式（source）参考

内置支持 **7 种**源文件格式，统一映射到 `Entry`：

```python
@dataclass
class Entry:
    key: str                 # 稳定标识，惯例 "ui.mainmenu.play"
    source_text: str         # 源语文本
    target_text: str = ""    # 目标语译文（未翻译时为空）
    context: str = ""        # 自由形式上下文
    comment: str = ""        # 术语/占位符提醒
    en_terms: list = []      # [(zh, en), ...] 中→英术语对
    terms: list = []         # [(zh, target), ...] 中→目标语术语对
    metadata: dict = {}      # 后端自定义字段（往返保留）
```

| 格式 | 后缀 | 适合场景 | 术语列 | 备注 |
|---|---|---|---|---|
| `json` | `.json` | 现代 Web / Unity 项目 | ❌ 不建议 | 结构见 4.1 |
| `yaml` | `.yaml` / `.yml` | 可读性高、人工维护 | ❌ 不建议 | 和 JSON 同 schema |
| `xml` | `.xml` | 遗留 Flash / Unreal | ❌ 不建议 | 结构见 4.3 |
| `csv` | `.csv` | Excel 导出首选 | ❌ 不建议 | UTF-8 BOM 可选 |
| `xliff` | `.xliff` / `.xlf` | 标准化翻译交付 | ❌ 不建议 | OASIS XLIFF 1.2 |
| `dtxml` | `.dtxml` | 内部 metalib 格式 | ❌ 不建议 | 保留 struct 名 |
| `xlsx` | `.xlsx` | **一审/二审上传的首选**；LLM 翻译链路 | ✅ `EnTerms` / `Terms` | 结构见 4.7 |

### 4.1 JSON

```json
{
  "meta": {
    "project_code": "example_game",
    "source_locale": "en",
    "target_locale": "zh-CN"
  },
  "entries": [
    {
      "key": "ui.mainmenu.play",
      "source_text": "Play",
      "context": "Main menu — start a new game.",
      "comment": "Short action button."
    }
  ]
}
```

必填字段：`entries[].key` / `entries[].source_text`。
`target_text` / `context` / `comment` 可省略，缺省为空串。

### 4.2 YAML

同 JSON schema，缩进+注释更友好：

```yaml
meta:
  project_code: example_game
  source_locale: en
  target_locale: zh-CN

entries:
  - key: ui.mainmenu.play
    source_text: Play
    context: "Main menu — start a new game."
    comment: ""
```

### 4.3 XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<localization project_code="example_game" source_locale="en" target_locale="zh-CN">
  <entry key="ui.mainmenu.play"
         context="Main menu — start a new game."
         comment="Short action button.">
    <source>Play</source>
    <!-- 翻译后会被框架写入 <target>...</target> -->
  </entry>
</localization>
```

### 4.4 CSV

```csv
key,source_text,context,comment
ui.mainmenu.play,Play,Main menu — start a new game.,Short action button.
hud.health,"HP: {value}/{max}",HUD label.,"Placeholders must be preserved."
```

- 首行**必须**是表头，列名大小写不敏感；
- 包含逗号的字段需用双引号包裹；
- UTF-8 推荐带 BOM 保证 Excel 直接双击可读。

### 4.5 XLIFF（OASIS 1.2）

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" version="1.2">
  <file source-language="zh-CN" datatype="plaintext" target-language="vi">
    <body>
      <trans-unit id="ui.mainmenu.play">
        <source>Play</source>
        <target state="translated">Chơi</target>
      </trans-unit>
    </body>
  </file>
</xliff>
```

`state` / 自定义属性会被塞进 `Entry.metadata`，`load → dump` 往返保留。

### 4.6 DTXML（内部 metalib 格式）

```xml
<?xml version="1.0" encoding="UTF-8"?>
<metalib xmlns="http://schemas.example.com/dtxml/2026">
  <struct name="LocalizationEntry" version="1">
    <entry key="ui.mainmenu.play">
      <source>Play</source>
      <context>Main menu — start a new game.</context>
      <comment>Short action button.</comment>
    </entry>
  </struct>
</metalib>
```

> 这是示意版 schema；真实业务里的 DTXML 列定义是私有的，接入时请覆盖 `DtxmlSource` 的 `load` / `dump`。

### 4.7 XLSX（审校/翻译首选）

**固定表头，顺序即列顺序**：

| 列 | 必填 | 说明 |
|---|---|---|
| `Key` | ✅ | 稳定标识 |
| `Source` | ✅ | 源语文本 |
| `Target` | ❌ | 译文（增量表翻译前为空） |
| `Context` | ❌ | 上下文 |
| `Comment` | ❌ | 备注 / 占位符提醒 |
| `EnTerms` | ❌ | **中→英术语对**，一个单元格内多行，格式：`艾薇塔=Evita` |
| `Terms` | ❌ | **中→目标语术语对**，格式同上，如 `艾薇塔=Evita` 或 `护盾=khiên` |
| `EnglishSide` | ❌ | 两步翻译 Step 1 的英文中间结果（框架自动写入） |

```
┌───────────────────┬────────┬────────┬─────────┬─────────┬──────────────┬──────────────┬─────────────┐
│       Key         │ Source │ Target │ Context │ Comment │   EnTerms    │    Terms     │ EnglishSide │
├───────────────────┼────────┼────────┼─────────┼─────────┼──────────────┼──────────────┼─────────────┤
│ ui.mainmenu.play  │ 开始    │        │ 主菜单   │          │              │              │             │
│ hud.health        │ 血量    │        │ HUD     │          │ 血量=HP      │ 血量=Máu     │             │
└───────────────────┴────────┴────────┴─────────┴─────────┴──────────────┴──────────────┴─────────────┘
```

术语列每行一个 `源文=译文`，用**单元格内换行**（Alt+Enter）分隔。
一步策略只读 `Terms`，两步策略两列都读并做 inner-join 映射。

### 4.8 可用列名容错

JSON/YAML 的 `source` / `source_text` / `original` 都识别；XLSX 的 `EnTerms` / `en_terms` / `ENTERMS` 都认，不区分大小写与下划线。

---

## 5. 敏感字段与环境变量注入

**所有标注 🔒 的字段**都应走环境变量注入，严禁明文写进仓库 YAML。

### 命名规则

```
GAME_TRANS_TOOLCHAIN__<SECTION>__<FIELD>
```

两层下划线分隔，`<SECTION>` 对应 YAML 顶层键。

### 常用环境变量清单

| 环境变量 | 对应配置路径 |
|---|---|
| `GAME_TRANS_TOOLCHAIN__VCS__USERNAME` / `GAME_TRANS_TOOLCHAIN__VCS__PASSWORD` | `vcs.username` / `vcs.password` |
| `GAME_TRANS_TOOLCHAIN__LLM__API_KEY` | `llm_profile` 指向的 profile 的 `api_key` |
| `GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN` | `platform.api_token`（全局） |
| `GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN` | Phrase 一审的 `reviews.first.extra.subject_token` |
| `GAME_TRANS_TOOLCHAIN__NOTIFICATION__WEBHOOK` | `notification.webhook` |

### 验证

```bash
python main.py config dump --config conf/config.yaml --language vi
```

敏感字段应打印为 `***`。若还看到原文，立刻排查注入是否生效。

---

## 6. 为什么 `platform` 不区分一审 / 二审？

一句话：**`config.yaml.platform` 是全局兜底；一审 / 二审的真正差异靠 `reviews.first.platform` / `reviews.second.platform` 做阶段级独立选择。**

### 为什么这样设计？

- **常见场景**：单平台（例如全部走 Crowdin）—— 只在 `config.yaml.platform.api_token` 填一次，一审 / 二审都用；
- **游戏出海典型场景**：**一审 Phrase + 二审 Crowdin** —— 两份凭据分别放 `reviews.first.extra.subject_token` 与 `platform.api_token`，各走各的；
- **跨平台污染保护**：工厂 `build_review_tool` 在回退到全局 `platform` 时，仅当全局 `type` 与阶段 `platform` 相同时才共享 `api_base/api_token/project_id`，避免 "Phrase 用了 Crowdin 的 token / 请求打到对方 nginx" 的 404；
- **扩展友好**：新接入第三家 TMS 时，只需在**阶段**里写 `platform: lokalise` 即可，不用动全局。

### 配置解析优先级（`build_review_tool`）

```
reviews[stage].platform (非 none)
   └── 用该平台
reviews[stage].platform == "none" / 空
   └── fallback 参数（内部调用方指定）
       └── 全局 platform.type（如果非 none）
           └── NoopPlatform（无操作兜底）
```

详细代码：[`src/TiMi_HOK_Game_Translator/platforms/factory.py#build_review_tool`](../src/TiMi_HOK_Game_Translator/platforms/factory.py)。

### 场景示例

**场景 A：全局单平台**

```yaml
# config.yaml
platform:
  type: crowdin
  api_token: ""
  project_id: "123"
# 语种 profile 两阶段都省略 → 都走全局 Crowdin
```

**场景 B：一审 Phrase + 二审 Crowdin**

```yaml
# config.yaml
platform:
  type: crowdin                 # 二审用它的 api_token / project_id 做兜底
  api_token: ""                 # 🔒 GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN
# conf/languages/vi.yaml
reviews:
  first:
    platform: phrase            # 阶段级覆盖，强制走 Phrase
    extra:
      region: eu
      subject_token: ""         # 🔒 GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN
  second:
    platform: crowdin           # 跟全局同名 → 自动继承 api_token / project_id
    project_id: ""              # 若此处留空，会从 config.yaml 的 platform.project_id 继承
```

**场景 C：只做翻译不走审校**

```yaml
# 语种 profile 直接从 workflow 里移除 first_review / second_review：
workflow:
  - pull_vcs
  - translate
  - merge_data
  - push_vcs
reviews:
  first:  { platform: none }    # 显式声明 none（可省，但显式更安全）
  second: { platform: none }
```

---

## 相关文档

- 项目总览：[`../README.md`](../README.md)
- 架构详解：[`architecture.md`](./architecture.md)
- 工作流状态清单：[`state_registry.md`](./state_registry.md)
- 平台扩展：[`extending_platforms.md`](./extending_platforms.md)
- Phrase 专项：[`platforms/phrase.md`](./platforms/phrase.md)
- 源文件扩展：[`extending_sources.md`](./extending_sources.md)
- LLM 扩展：[`extending_llm.md`](./extending_llm.md)
- VCS 扩展：[`extending_vcs.md`](./extending_vcs.md)
