<h1 align="center">TiMiHOKGameTranslator</h1>

<p align="center">
  <strong>面向游戏出海的工业级本地化自动化流水线</strong><br/>
  <em>Bridge your game to the world — automated, auditable, extensible.</em>
</p>

<p align="center">
  <a href="https://www.python.org/"><img alt="Python 3.8+" src="https://img.shields.io/badge/python-3.8+-blue.svg"></a>
  <a href="./docs/architecture.md"><img alt="Architecture" src="https://img.shields.io/badge/docs-architecture-blue.svg"></a>
  <a href="../LICENSE.txt"><img alt="License" src="https://img.shields.io/badge/license-Apache%202.0-blue"></a>
</p>

<p align="center">
  拉取源文 → AI 预翻译 → 多轮审校 → 合并回写 → 提交发布 → 通知
</p>

---

## 🎯 Why TiMiHOKGameTranslator？

游戏本地化不是"调一次 ChatGPT 就能发版"的事。**TiMiHOKGameTranslator** 专门为游戏厂商
出海场景打造，解决传统方案无法覆盖的真实痛点：

- 🏭 **工业级 ≠ 玩具** —— 支持**断点续跑**、**跨天尾巴任务续审**、**线程安全持久化**，
  一次性跑完一周的增量翻译且崩溃可恢复，不是"run 一次 translate 一次"的脚手架；
- 🔀 **双平台双轮审校** —— 一审 Phrase、二审 Crowdin 可以同时跑，所有已审 approved
  精准路由到"该走的下一个阶段"，而不是无差别回炉；
- 🎮 **游戏场景原生** —— 内置术语注入、兄弟行广播（同源文一译多扩散）、
  TM 回灌、小语种两步枢纽翻译（中→英→目标），针对游戏文案痛点深度优化；
- 🔌 **真·可插拔** —— VCS（svn/git/perforce）、源文件格式（6+ 种）、LLM、翻译平台、
  通知渠道，每个层都是**协议 + 工厂 + 装饰器注册**三件套，加新后端零改框架；
- 📝 **YAML-first 配置** —— 新增语种、切换策略、调整审校流程全部走 YAML，
  运维/测试同学无需碰代码。

## 👥 适合谁 / 不适合谁

| ✅ 适合 | ❌ 不适合 |
|---|---|
| 多语种游戏（10+ locales）的持续迭代本地化 | 一次性翻译一份 README 的小需求（用 ChatGPT 更快）|
| 已有 Phrase/Crowdin 等平台但想接 AI 预译的团队 | 对翻译质量零容忍且不愿人工审校的场景 |
| 需要 TM 积累 + 增量翻译 + 跨天审校的生产流水线 | 没有 VCS、也不走审校的个人 side-project |
| 要在 SVN/Git/Perforce 多仓协同的大型项目 | 完全离线、无 LLM API 预算的场景（可用 mock 跑通但无实际翻译）|

## 🔧 平台支持矩阵

| 层 | 内置实现 | 可扩展 |
|---|---|---|
| **VCS** | `svn` / `git` / `perforce` / `mock` | ✅ 继承 `VcsClient` |
| **源文件格式** | `json` / `yaml` / `xml` / `csv` / `dtxml` / `xliff` / `xlsx` | ✅ `@register_source("myfmt")` |
| **LLM 提供方** | `mock`（零依赖）/ `openai` / `openai_compatible` / `anthropic` / `venus` / `hunyuan_translation` | ✅ 实现 `LLMClient` 协议 |
| **翻译平台** | **Phrase TMS**（原 Memsource）/ **Crowdin API v2** / `none` | ✅ `@register_platform("myp")` |
| **翻译策略** | `generic`（直译）/ `two_step`（枢纽翻译）| ✅ `@register_translation_strategy("vi")` |
| **通知渠道** | `console` / `webhook` | ✅ 实现 `Notifier` 协议 |

---

## 🚀 快速开始（1 分钟 mock demo）

跑通一个**零依赖、零凭据**的 demo，验证安装无误：

```bash
# 1. 克隆 + 进入项目目录
git clone https://github.com/<your-org>/TiMi_HOK_Game_Translator.git
cd TiMi_HOK_Game_Translator

# 2. 创建虚拟环境（要求 Python 3.8+）
python -m venv .venv
# Linux / macOS：source .venv/bin/activate
# Windows PowerShell：.venv\Scripts\Activate.ps1

# 3. 安装依赖
pip install -r requirements.txt

# 4. 跑一个全 mock 的 demo（不需要任何外部服务）
python main.py run --config docs/examples/demo.yaml

# 5. 查看最终生效配置（敏感字段自动脱敏为 ***）
python main.py config dump --config docs/examples/demo.yaml
```

> 💡 跑过一次想从头再来：加 `--fresh`
> 续跑指定批次：`--batch <batch_id>`（与 `--fresh` 互斥）

完整的 demo 教程见 [`docs/quickstart.md`](./docs/quickstart.md)。

---

## 🧭 真实项目接入 5 步

跑通 mock demo 后，接入自己的真实项目按以下 5 步落地。每一步都给了跳转链接，
**全程不改一行代码**。

### Step 1 · 准备源文件（增量 / 全量）

支持 **xlsx / json / yaml / xml / csv / xliff / dtxml** 7 种格式，统一映射到 `Entry`。

- 📁 把增量文件放到 VCS 工作副本的 `fixtures/<lang>/99.incr.<fmt>`；
- 📖 完整字段 schema 和每种格式的示例：→ [配置详解 源文件格式](./docs/configuration.md#4-源文件格式source参考)
- 💡 不确定选哪种格式？游戏项目**强烈推荐 xlsx**（审校员最熟 + 支持 EnTerms/Terms 术语列）。

### Step 2 · 接入 VCS

改 `conf/config.yaml` 的 `vcs` 块，支持 `svn` / `git` / `perforce` / `mock`。

- 📖 四种后端的完整示例：→ [配置详解 VCS 配置示例](./docs/configuration.md#12-vcs--版本控制)
- 🔒 **凭据走环境变量**：`GAME_TRANS_TOOLCHAIN__VCS__USERNAME` / `GAME_TRANS_TOOLCHAIN__VCS__PASSWORD`，严禁明文提交。

### Step 3 · 配置 LLM 模型

在 `conf/llm.yaml` 的 `profiles` 下**按名字**注册一个 profile，然后在 `conf/config.yaml`
或 `conf/languages/<lang>.yaml` 用 `llm_profile: <profile_name>` 引用它。

- 📖 字段逐项 + extra 键说明：→ [配置详解 llm.yaml](./docs/configuration.md#2-confllmyaml--llm-profile-注册表)
- 🔒 **API Key 走环境变量**：`GAME_TRANS_TOOLCHAIN__LLM__API_KEY`
- 🧪 零预算调试：profile 用 `provider: mock` 即可，不发一次网络请求。

### Step 4 · 配置审校平台 Token

在 `conf/languages/<lang>.yaml` 的 `reviews.first` / `reviews.second` 分别选平台，
一审 Phrase + 二审 Crowdin 可以**同时跑**。

- 📖 一审 / 二审解耦机制：→ [配置详解](./docs/configuration.md#6-为什么-platform-不区分一审--二审)
- 📖 Phrase 鉴权 / 字段 / 排错：→ [Phrase 平台专项](./docs/platforms/phrase.md)
- 🔒 常用环境变量：
  - `GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN` —— Crowdin / Phrase ApiToken 模式
  - `GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN` —— Phrase 推荐的 Subject Token 模式

### Step 5 · 启用翻译记忆库（TM）回灌（可选）

在语种 profile 的 `workflow` 列表里加入 `update_tm` / `update_grn_tm`，
工作流会**在正式审校前**把历史 approved 自动灌回审校平台的默认 TM 库。

- 🧭 **TM 本身请直接在审校平台（Phrase / Crowdin）后台创建并绑定到项目**，
  框架只负责把历史 approved 以 `(source, target)` 形式回灌到项目默认 TM。
- ✅ 默认 Phrase 内置支持；Crowdin / 自定义平台不实现 `upload_tm` 时**自动跳过**，
  不阻塞主流程。
- 💤 不想做 TM 回灌？从 `workflow` 列表里删掉这两个状态即可。

### 跑起来

```bash
python main.py run --language vi
```

想一步到位理解全部字段，直接看 [`docs/getting_started.md`](./docs/getting_started.md) 的
"一张清单接入一个语种"章节。

---

## 🎯 翻译策略选择指南

本框架支持**三级优先**的策略绑定：**YAML 配置 → 装饰器 → Generic 兜底**。
推荐使用 YAML 方式，运维/测试同学无需改代码即可切换策略。

### 一、内置策略类

| 短名 | 行为 | 用到的术语列 | 适用场景 |
|---|---|---|---|
| `GenericTranslationStrategy`<br>或 `generic` | **一步直译**（中 → 目标） | `Terms` | 中文到目标语种模型效果稳定的语种（vi/th/id/ja 等） |
| `TwoStepTranslationStrategy`<br>或 `two_step` | **两步枢纽**（中 → 英 → 目标） | `EnTerms` + `Terms` | 直译效果不稳定的小语种（de/fr/ru/tr/ar/es/pt-BR 等）；<br>Step 1 注入 EnTerms，Step 2 用两列做 inner-join 后以"英→目标"术语对注入 |

### 二、三种配置方式（优先级从高到低）

**方式一（推荐）：YAML 声明式**

在 `conf/languages/<lang>.yaml` 的 `strategy_config` 加一行：

```yaml
strategy_config:
  class: TwoStepTranslationStrategy   # 短名；或完整 import 路径
  pivot_locale: en                    # 两步策略专属：中转语种，默认 en
  display_name: 越南语翻译
```

想回退一步直译？注释掉 `class:` 这一行即可。

**方式二：代码装饰器注册**

适合策略类需要重写 `filter` / `post_translate` 等方法的深度定制场景：

```python
# src/TiMi_HOK_Game_Translator/strategies/my_strategy.py
from TiMi_HOK_Game_Translator.translation.factory import register_translation_strategy
from TiMi_HOK_Game_Translator.strategies.minor_language_strategy import TwoStepTranslationStrategy


@register_translation_strategy("ru")
class RussianStrategy(TwoStepTranslationStrategy):
  display_name = "Russian"
  # ... 自定义 filter / translate 等
```

**方式三：第三方包 import 路径**

`class` 带 `.` 时，走 `importlib` 动态加载，不碰框架代码：

```yaml
strategy_config:
  class: my_company.strategies.RussianDialectStrategy
```

### 三、术语列（EnTerms / Terms）填法

增量 xlsx 的两列术语单元格内，每行一个 `源文=译文`，Alt+Enter 换行分隔：

```
艾薇塔=Evita
护盾=shield
噬源兽=Essence Devourer
```

- **一步策略**：只读 `Terms` 列（中→目标语术语），`EnTerms` 可留空；
- **两步策略**：两列都读，Step 2 会把 EnTerms/Terms 按中文源文做 inner-join
  映射为"英→目标语"术语对注入，命中率比直接用"中→目标"更高。

### 四、运行时日志自检

工厂首次创建策略时会打 INFO 日志，便于确认实际用的是哪个类：

```
[INFO] Translation strategy for 'vi' resolved via YAML strategy_config.class → TwoStepTranslationStrategy
```

错配置（如写错短名）不会炸——会打 WARNING 并降级到装饰器或 Generic：

```
[WARN] strategy_config.class='TwoStep' is not a known builtin short name
       (available: ['GenericTranslationStrategy', 'TwoStepTranslationStrategy',
        'generic', 'two_step']); falling back to decorator registry
```

## 🧩 架构总览

```
┌───────────────┐   ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  ingest       │──▶│  translate    │──▶│  review       │──▶│  merge        │
│  （VCS + 源） │   │  （LLMClient）│   │  （Platform） │   │  （Source.dump）│
└───────────────┘   └───────────────┘   └───────────────┘   └───────┬───────┘
                                                                    ▼
                                                            ┌───────────────┐
                                                            │  publish      │
                                                            │  （VCS 提交   │
                                                            │   + 通知）    │
                                                            └───────────────┘
```

完整架构见 [`docs/architecture.md`](./docs/architecture.md)。

## 📚 文档

**入门**
- [快速开始（JSON demo）](./docs/quickstart.md) · 5 分钟端到端跑通
- [完整入门指南](./docs/getting_started.md) · 详细教程，涵盖所有配置项
- [架构总览](./docs/architecture.md) · 核心抽象 + 分层设计

**配置参考**
- [配置详解](./docs/configuration.md) · `config.yaml` / `llm.yaml` / `languages/*.yaml` 字段逐项说明，含源文件格式参考
- [状态机状态表](./docs/state_registry.md) · 所有工作流状态一览

**扩展指南**
- [扩展 VCS 后端](./docs/extending_vcs.md) · 接入自定义版本控制系统
- [扩展源文件格式](./docs/extending_sources.md) · 新增 Properties/.resx 等格式
- [扩展 LLM 提供方](./docs/extending_llm.md) · 对接内网/私有大模型
- [扩展翻译平台](./docs/extending_platforms.md) · 接入新的 TMS
- [扩展翻译策略](./docs/extending_translation.md) · 自定义语种专属翻译逻辑

**运维参考**
- [Phrase TMS 平台专项](./docs/platforms/phrase.md) · 鉴权 / 字段 / 排错
- [E2E 测试指南](./docs/e2e_test_guide.md) · 完整联调手册
- [常见问题 FAQ](./docs/faq.md)

---

<p align="center">
  <sub>Built with ❤️ for game localization teams.</sub>
</p>
