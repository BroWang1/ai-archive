# TiMi_HOK_Game_Translator 接入指南

> 面向内部开发/运维的实战文档。看完本篇你应该能够：接 1 种新语种、换 1 种 VCS、换 1 种审校平台、换 1 种 LLM，全程**不改代码**。

---

## 一、这是什么？

一个**可插拔、基于状态机**的游戏本地化自动化框架：

```
拉源文(VCS) → AI 预翻译(LLM) → 多轮审校(Platform) → 合并回写 → 推送发布 + 通知
```

一句话：**接入靠配置、扩展靠装饰器、状态可回放**。

---

## 二、能力矩阵（都能换，不改代码）

| 维度 | 当前支持 | 对应配置字段 | 想换 / 加？ |
|---|---|---|---|
| **VCS** | `svn`、`git`、`perforce`、`mock` | `vcs.type` | 改 `conf/config.yaml` 的 `vcs` 块 |
| **文件格式** | `xlsx`、`json`、`yaml`、`xml`、`csv`、`dtxml`、`xliff` | `source.format` | 改 `conf/languages/<lang>.yaml` 的 `source.format` |
| **审校平台** | `phrase`、`crowdin`、`none` | `reviews.<stage>.platform` | 一审走 Phrase、二审走 Crowdin，可自由组合 |
| **LLM 模型** | OpenAI/Anthropic/Venus/HY-MT/DeepSeek/GLM/Qwen/mock | `llm_profile` | 全部在 `conf/llm.yaml` 维护，用名字引用 |
| **翻译策略** | 一步直译 / 两步枢纽（中→英→目标） | `strategy_config.class` | YAML 一行切换，详见 README "翻译策略选择指南" |
| **通知渠道** | `wecom`、`slack`、`email`、`console`、`none` | `notification.type` | 改 `type` + 对应 `webhook` |
| **工作流状态** | 17 种内置状态，可任意拼顺序 | `workflow:` 列表 | 想删步骤直接从列表里删 |

---

## 三、5 分钟接入

### 3.1 环境准备

- **Python 3.8+**
- **VCS 客户端**（选一个）：`svn` CLI / `git` CLI / `p4` CLI
- （可选）**openpyxl**（走 xlsx 格式时自动用）
- （可选）**requests**（走企业微信/Slack/HTTP LLM 时自动用）

### 3.2 安装

```bash
# 克隆、建虚拟环境、安装
git clone <repo> && cd TiMi_HOK_Game_Translator
python -m venv .venv && .\.venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

### 3.3 配置 3 个文件

| 文件 | 做什么 |
|---|---|
| `conf/config.yaml` | 全局：VCS、默认平台、workspace 位置、日志 |
| `conf/llm.yaml` | 把你的 LLM 模型注册到名字（供 profile 引用） |
| `conf/languages/<lang>.yaml` | 单个语种的接入——这是日常**最常改的文件** |

### 3.4 跑一下

```bash
python main.py run --language vi
```

---

## 四、新接入一个语种，一张清单

假设你要新接 **"韩语(ko)"**：

```yaml
# conf/languages/ko.yaml
id: ko
display_name: 韩语（联调样本）
source_locale: zh-CN
target_locale: ko

locale_names:
  cn: 韩语
  en: Korean

# 1. 源文件在 VCS 工作副本里的路径（相对于 vcs.local_path）
source:
  format: xlsx                              # 文件格式
  path: trunk/tests/fixtures/ko/99.incr.xlsx

# 2. 用哪个 LLM profile（必须在 conf/llm.yaml 里存在）
llm_profile: hunyuan_mt2_plus

# 3. 翻译策略（可选）
strategy_config:
  class: TwoStepTranslationStrategy         # 中→英→韩两步策略；省略则一步直译
  pivot_locale: en

# 4. 一审 / 二审配置
reviews:
  first:
    platform: phrase
    project_id: "xxxxx"
    project_name: KO First Review (Phrase)
    target_language_id: ko
    stop_time: "21:00"
    extra:
      region: eu
  second:
    platform: crowdin
    project_id: "123456"
    project_name: KO Second Review (Crowdin)
    target_language_id: ko

# 5. 通知配置
notification:
  type: wecom
  webhook: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
  mentioned:
    - "currylong"

# 6. 工作流编排（按顺序执行）
workflow:
  - last_first_review
  - last_second_review
  - pull_vcs
  - translate
  - last_merge_data
  - update_tm                               # 🆕 回灌 TM 到一审平台
  - first_review
  - update_grn_tm                           # 🆕 回灌 TM 到二审平台
  - second_review
  - validate_data
  - merge_data
  - push_vcs
```

**跑一下**：

```bash
python main.py run --language ko
```

---

## 五、关键配置字段速查

### 5.1 `conf/config.yaml`（全局）

| 字段 | 类型 | 说明 |
|---|---|---|
| `project_code` | str | 产品 slug，出现在日志前缀、通知标题、状态文件 |
| `stage` | enum | `exp_week` / `trunk_week` / `pub_week` / `hot_week` |
| `source_locale` | str | 源语种 BCP-47（通常 `zh-CN`） |
| `vcs.type` | enum | `svn` / `git` / `perforce` / `mock` |
| `vcs.url` | str | 仓库地址 |
| `vcs.local_path` | str | 本地工作副本目录（相对 workspace） |
| `vcs.username` / `vcs.password` | str | 凭据，**建议走环境变量** |
| `platform.type` | enum | 全局默认审校平台 |
| `platform.api_token` | str | 平台 token，**敏感字段** |
| `llm_profile` | str | 全局默认 LLM，指向 `conf/llm.yaml` 的 key |
| `languages_dir` | str | 语种 profile 目录（默认 `conf/languages`） |
| `workspace.root` | str | workspace 绝对路径；为空则 `$CWD/workspace` |
| `logging.level` | enum | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

### 5.2 `conf/llm.yaml`（LLM 注册表）

每个 profile 的字段：

| 字段 | 说明 |
|---|---|
| `provider` | `openai` / `openai_compatible` / `anthropic` / `venus` / `hunyuan_translation` / `mock` |
| `model` | 模型名 |
| `api_base` | API 根地址 |
| `api_key` | 鉴权，**敏感字段** |
| `temperature` / `max_tokens` / `batch_size` | 调用参数 |
| `timeout_seconds` / `retries` / `retry_interval_seconds` | 重试策略 |
| `extra` | provider 专属字段（如 `wsid`、`server_id`、`app_group_id`） |

### 5.3 `conf/languages/<lang>.yaml`（语种 profile）

| 字段 | 说明 |
|---|---|
| `id` | 语种短 ID（与文件名一致） |
| `display_name` | 日志/通知里显示的中文名 |
| `source_locale` / `target_locale` | BCP-47 代码 |
| `locale_names.cn` / `locale_names.en` | 提示词中语种名的中英文显示覆盖 |
| `source.format` | 源文件格式，见能力矩阵 |
| `source.path` | 文件路径（相对 `vcs.local_path`） |
| `vcs` | 可选，覆盖全局 VCS 配置 |
| `llm_profile` | 用哪个 LLM profile |
| `strategy_config.class` | 翻译策略类名或完整 import 路径（见 README） |
| `strategy_config.pivot_locale` | 两步策略的中转语种，默认 `en` |
| `strategy_config.display_name` | 翻译器日志标签 |
| `strategy_config.use_concurrent_by_default` | 是否并发 |
| `strategy_config.default_max_workers` | 并发线程数 |
| `reviews.<stage>.platform` | `phrase` / `crowdin` / `none` |
| `reviews.<stage>.project_id` | 平台项目 ID |
| `reviews.<stage>.target_language_id` | 平台的语种 ID（与 BCP-47 可能不同） |
| `reviews.<stage>.stop_time` | 审校轮询截止 `HH:MM` 或 `+5m` 相对时间 |
| `reviews.<stage>.poll_interval_seconds` | 轮询间隔 |
| `reviews.<stage>.extra` | 平台专属字段（如 Phrase 的 `region`） |
| `notification.type` | `wecom` / `slack` / `email` / `console` / `none` |
| `notification.webhook` | 群机器人地址，**敏感字段** |
| `notification.mentioned` | 需要 @ 的用户 ID 列表 |
| `workflow` | 工作流状态有序列表 |
| `merge_start_time` | 合并窗口起始 `HH:MM`；为空立即执行 |

### 5.4 Workflow 可用状态清单

```
pending → pull_vcs → translate → update_tm → first_review
       → update_grn_tm → second_review → validate_data → merge_data
       → push_vcs / push_multi_vcs → finished

辅助状态：
  last_first_review / last_second_review / last_merge_data
  （处理昨日续审任务）
  light_review（轻量审校）、increment_match（增量匹配）
```

---

## 六、常见扩展

| 需求 | 操作 |
|---|---|
| **加一个新语种** | 复制 `vi.yaml` 改 `id` / `target_locale` / `reviews.<stage>.project_id` 即可 |
| **切 LLM** | 改 `llm_profile` 字段指向 `conf/llm.yaml` 的另一个 key |
| **一步 ↔ 两步策略** | 加/去 `strategy_config.class: TwoStepTranslationStrategy` |
| **换审校平台** | 改 `reviews.first.platform` / `project_id` |
| **一审 Phrase + 二审 Crowdin** | 两个 `reviews.*` 块各写各的 |
| **跳过某阶段** | 从 `workflow:` 列表里删掉该状态 |
| **不发通知** | `notification.type: none` |
| **只跑翻译，不审校** | `workflow` 保留 `pull_vcs/translate/merge_data/push_vcs` 即可（参见 `conf/languages/de.yaml`） |
| **临时换 token** | 环境变量 `GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN=xxx`（配置键用 `__` 分层） |

---

## 七、敏感字段 & 环境变量

**所有标注"敏感字段"的配置项**（`password` / `api_key` / `api_token` / `webhook` 等）：

- `conf/*.yaml` 里**可以写明文**（联调方便），但**上线前必须清空**
- 用环境变量注入覆盖，变量名规则：`GAME_TRANS_TOOLCHAIN__<SECTION>__<FIELD>`
  - 例：`GAME_TRANS_TOOLCHAIN__VCS__PASSWORD=xxx`
  - 例：`GAME_TRANS_TOOLCHAIN__LLM__API_KEY=xxx`
  - 例：`GAME_TRANS_TOOLCHAIN__NOTIFICATION__WEBHOOK=xxx`
- 导出当前配置时（`config dump`），敏感字段会自动脱敏为 `****`

---

## 八、常见问题

| 问题 | 原因 / 处理 |
|---|---|
| `Unknown source format 'xxx'` | `source.format` 不在支持列表里，查第二节能力矩阵 |
| svn `wc locked` / E155004 | 跑 `svn cleanup <local_path>` 清锁；不要用 `svn status` 判断 |
| LLM 响应超时 | 增大 `conf/llm.yaml` 对应 profile 的 `timeout_seconds` / `retries` |
| Phrase 没找到项目 | 检查 `reviews.first.extra.region`（eu 账户用 `eu.phrase.com`） |
| 任务已创建但没发通知 | 检查 `notification.type` 是否 `none`；企业微信看 `webhook` 是否配好 |
| 想看 Step 1 英文中间结果 | 看最终 xlsx 的 `EnglishSide` 列（第 8 列） |

---

## 九、相关文档

- 项目总览与特性清单：[`../README.md`](../README.md)
- 配置详解（字段逐项 + 源文件格式参考）：[`./configuration.md`](./configuration.md)
- 架构详解：[`./architecture.md`](./architecture.md)
- VCS 扩展指南：[`./extending_vcs.md`](./extending_vcs.md)
- 文件格式扩展：[`./extending_sources.md`](./extending_sources.md)
- LLM 扩展：[`./extending_llm.md`](./extending_llm.md)
- 平台扩展：[`./extending_platforms.md`](./extending_platforms.md)
- Phrase 平台专项：[`./platforms/phrase.md`](./platforms/phrase.md)
