# TiMi_HOK_Game_Translator 端到端测试指南

> 本文档帮你证明整套系统在**真实环境**下畅通：按**9 级端到端验证**顺序推进 —— 环境 → VCS 连通 → 源文件解析 → LLM 调用 → 审校平台 → 单语种 workflow → 多语种批处理 → 断点续跑 → 通知。

> 📌 **使用说明**：
> - 入口命令统一使用 `python main.py ...`（项目根的 `main.py` 已内置 `sys.path` 引导，无需安装成包）；
> - 示例源文件统一使用 [`docs/examples/data/`](./examples/data/) 下的 5 种格式（`example_game.en.{json,yaml,xml,csv,dtxml}`）；
> - 示例配置使用 [`docs/examples/demo.yaml`](./examples/demo.yaml) 或项目根 [`conf/config.yaml`](../conf/config.yaml)；
> - 语种 profile 使用 [`conf/languages/`](../conf/languages/) 下的 **YAML** 文件（如 `vi.yaml`），不是旧版的 JSON 文件。

---

## 目录

- [0. 前置准备](#0-前置准备)
- [1. 环境自检](#1-环境自检)
- [2. VCS 连通性测试](#2-vcs-连通性测试)
- [3. 源文件格式自检](#3-源文件格式自检)
- [4. LLM 连通性测试](#4-llm-连通性测试)
- [5. 审校平台连通性测试](#5-审校平台连通性测试)
- [6. 单语种端到端测试](#6-单语种端到端测试)
- [7. 多语种批处理测试](#7-多语种批处理测试)
- [8. 断点续跑验证](#8-断点续跑验证)
- [9. 通知渠道验证](#9-通知渠道验证)
- [附录 A：故障排查速查表](#附录-a故障排查速查表)
- [附录 B：如何准备一个可直接使用的测试仓库](#附录-b如何准备一个可直接使用的测试仓库)

---

## 0. 前置准备

### 0.1 装依赖

```bash
cd gpt/TiMi_HOK_Game_Translator

# 创建并激活虚拟环境（要求 Python 3.8+）
python -m venv .venv
# Linux/macOS：source .venv/bin/activate
# Windows PowerShell：.venv\Scripts\Activate.ps1

# 安装运行时依赖
pip install -r requirements.txt
```

### 0.2 准备测试数据

本仓库在 [`docs/examples/data/`](./examples/data/) 下自带 5 种格式的同一批词条样例：
`example_game.en.{json, yaml, xml, csv, dtxml}`，可直接用于 VCS / 源文件 / LLM 等各级探针。

如需在 Git / SVN / Perforce 远端仓库里铺这些数据，自行建一个 `locales/` 目录并把
`docs/examples/data/*` 复制进去即可：

```bash
mkdir -p my_i18n_test/locales
cp docs/examples/data/example_game.en.* my_i18n_test/locales/
```

### 0.3 环境变量三级注入

**永远不要**把凭据写到 YAML！用环境变量：

```bash
# VCS 凭据
export GAME_TRANS_TOOLCHAIN__VCS__USERNAME=your-username
export GAME_TRANS_TOOLCHAIN__VCS__PASSWORD=your-secret

# LLM 凭据
export GAME_TRANS_TOOLCHAIN__LLM__API_KEY=sk-xxxxx

# 审校平台凭据
export GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN=phrase_or_crowdin_token

# 通知凭据
export GAME_TRANS_TOOLCHAIN__NOTIFICATION__WEBHOOK=https://qyapi.weixin.qq.com/...
```

**PowerShell 语法**：`$env:GAME_TRANS_TOOLCHAIN__VCS__USERNAME="your-username"`

---

## 1. 环境自检

**目的**：验证 Python 与 CLI 装对了。

```bash
python --version                                       # >= 3.8
python main.py --help                                  # 应该列出 run / config 子命令
python main.py config dump --config docs/examples/demo.yaml
```

**期望输出**：一份完整的 YAML，敏感字段（`password / api_token / webhook`）应显示为 `***`。

**✅ 通过标准**：`config dump` 打印结束，退出码 0，且**未看到任何原始凭据**。

---

## 2. VCS 连通性测试

分四种后端讲，每种都有**独立命令 + TiMi_HOK_Game_Translator 侧的连通性测试**。

### 2.1 Git

#### 2.1.1 系统层探针

```bash
git --version                                                    # 确认装了 git
git ls-remote https://github.com/YOUR_ACCOUNT/game-i18n-test.git # 无凭据探测公开仓库
git clone https://github.com/YOUR_ACCOUNT/game-i18n-test.git /tmp/probe && rm -rf /tmp/probe
```

如果是**私有仓库**，用以下任一凭据方式确认：

```bash
# SSH：确认 ssh key 已加到 GitHub
ssh -T git@github.com

# HTTPS + Personal Access Token
git ls-remote https://oauth2:${GITHUB_PAT}@github.com/YOUR_ACCOUNT/game-i18n-test.git
```

#### 2.1.2 TiMi_HOK_Game_Translator 侧探针

```bash
# 复制项目自带的最小配置做修改
cp conf/config.yaml my_config.yaml
# 把 vcs.type 改为 git，vcs.url 指向你的仓库，vcs.local_path 填 "git/test_translation"

# 只跑 pull_vcs 一个状态（打印后立即停止）：
python -c "
from TiMi_HOK_Game_Translator.config import load
from TiMi_HOK_Game_Translator.vcs import create_vcs_client
cfg = load(config_path='my_config.yaml')
client = create_vcs_client(cfg.vcs, workspace='workspace')
status = client.checkout()
print('OK, files pulled:', status.files_touched)
"
```

**✅ 通过标准**：上述脚本打印 `OK, files pulled: N` 且 `workspace/<local_path>/locales/en.json` 已经存在。

**❌ 常见错误**：

| 错误 | 原因 | 处理 |
|---|---|---|
| `fatal: Authentication failed` | PAT 过期 / SSH key 未配置 | 到 GitHub Settings → Developer settings → PAT 重新生成 |
| `Repository not found` | 仓库名写错 / 权限不足 | 复核 `vcs.url` |
| `SSL certificate problem` | 企业代理拦 HTTPS | 设 `GIT_SSL_NO_VERIFY=true` 临时排查（**上线时切勿保留**） |

### 2.2 SVN

#### 2.2.1 系统层探针

```bash
svn --version                                            # 需 CLI 装了
svn info https://svn.example.com/game-i18n-test/trunk    # 匿名探测
svn info https://svn.example.com/game-i18n-test/trunk \
    --username $GAME_TRANS_TOOLCHAIN__VCS__USERNAME \
    --password $GAME_TRANS_TOOLCHAIN__VCS__PASSWORD \
    --non-interactive --trust-server-cert
```

**⚠️ 关键提示**：`svn status` **不能**可靠判断工作副本是否处于 `wc locked / needs cleanup` 状态。更可靠的方式是：
- 直接 `svn cleanup` （或较新版本支持的 `svn cleanup --dry-run`）；
- 或用 `svn update` / `svn info` 触发锁错误 `E155004`；
- 需区分**工作副本锁**（E155004，`svn cleanup` 修）与**版本库文件锁**（`svn lock/unlock` 用）。

#### 2.2.2 TiMi_HOK_Game_Translator 侧探针

```bash
# 项目根的 conf/config.yaml 默认即为 svn 模板，只需改 vcs.url / local_path
cp conf/config.yaml my_config.yaml
python -c "
from TiMi_HOK_Game_Translator.config import load
from TiMi_HOK_Game_Translator.vcs import create_vcs_client
cfg = load(config_path='my_config.yaml')
client = create_vcs_client(cfg.vcs, workspace='workspace')
print('checkout:', client.checkout().files_touched)
print('update:', client.update().revision)
"
```

**✅ 通过标准**：打印两行数字，`workspace/<local_path>` 下有 `locales/en.json`。

### 2.3 Perforce

```bash
p4 -p perforce.example.com:1666 -u YOUR_USER info      # 系统层探针
p4 -c game-i18n-test-workspace sync //depot/game-i18n-test/main/... # 拉一次
```

TiMi_HOK_Game_Translator 侧探针与 Git 相同，复制 `conf/config.yaml` 后将 `vcs.type` 改为 `perforce`。
配置字段清单详见 [`configuration.md` → VCS 配置示例](./configuration.md#vcs-配置示例)。

### 2.4 Mock（快速本地验证）

```bash
python main.py run --config docs/examples/demo.yaml --language vi --fresh
```

零依赖，用来在**任何 VCS 都不可用时**验证 TiMi_HOK_Game_Translator 本身正确（`demo.yaml` 已把 `vcs.type` 设为 `mock`）。

---

## 3. 源文件格式自检

**目的**：在真调 LLM 之前，先证明你的源文件能被正确解析。

```bash
python -c "
from TiMi_HOK_Game_Translator.sources import create_source
from TiMi_HOK_Game_Translator.config.schema import SourceConfig

for fmt, path in [
    ('json',  'docs/examples/data/example_game.en.json'),
    ('yaml',  'docs/examples/data/example_game.en.yaml'),
    ('xml',   'docs/examples/data/example_game.en.xml'),
    ('csv',   'docs/examples/data/example_game.en.csv'),
    ('dtxml', 'docs/examples/data/example_game.en.dtxml'),
]:
    src = create_source(SourceConfig(format=fmt, path=path))
    entries = src.load(path)
    print(f'{fmt:8} {len(entries):3} entries  first key={entries[0].key if entries else \"(empty)\"}')
"
```

**✅ 通过标准**：5 行都打印 `entries > 0` 且 `first key` 是合理字符串。

> 💡 内置源码还支持 `xliff` / `xlsx` / `properties`，可将这些格式的样例文件丢到
> `docs/examples/data/` 下并把路径加到循环中测通。

**如果你的项目用自定义格式**：

- 参考 `docs/extending_sources.md`
- 实现 `LocalizationSource.load / dump`
- 用 `@register_source("your_format")` 装饰器注册
- 把上面的循环加你的 format 就能立即测通

---

## 4. LLM 连通性测试

### 4.1 Mock LLM（默认）

无需任何配置。用它验证 pipeline 完整性。

```bash
python -c "
from TiMi_HOK_Game_Translator.llm import create_llm_client
from TiMi_HOK_Game_Translator.config.schema import LLMConfig
c = create_llm_client(LLMConfig(provider='mock'))
print(c.translate('Hello', source_locale='en', target_locale='vi').text)
"
```

**期望输出**：`[vi] Hello`

### 4.2 OpenAI

```bash
export GAME_TRANS_TOOLCHAIN__LLM__API_KEY="sk-xxxxx"
python -c "
import os
from TiMi_HOK_Game_Translator.llm import create_llm_client
from TiMi_HOK_Game_Translator.config.schema import LLMConfig
c = create_llm_client(LLMConfig(provider='openai', model='gpt-4o-mini',
                                api_key=os.environ['GAME_TRANS_TOOLCHAIN__LLM__API_KEY']))
r = c.translate('Hello, world.', source_locale='en', target_locale='vi',
                context='UI greeting')
print('OpenAI 返回：', r.text)
"
```

> 💡 bash 中含双下划线的环境变量用 `export KEY="value"` 定义没问题，但在 Python 代码
> 内读取时必须用 `os.environ['...']`，不能用 `$VAR` 直接插值（shell 解析不会穿透
> `python -c` 的字符串字面量）。

**❌ 常见错误**：

| 错误 | 原因 | 处理 |
|---|---|---|
| `AuthenticationError: 401` | key 错 / 项目未绑定支付 | 到 platform.openai.com 换 key |
| `RateLimitError: 429` | 免费额度用完 | 加信用卡、或用 `time.sleep` 拉低并发 |
| 中文乱码 | Windows CMD 编码 | `chcp 65001` 或改用 PowerShell |

### 4.3 自定义 LLM

例如你想接 Azure OpenAI / 内部部署 LLaMA：

```python
from TiMi_HOK_Game_Translator.llm import LLMClient, register_llm_provider


@register_llm_provider("my_llama")
class MyLlamaClient(LLMClient):
    def translate(self, text, *, source_locale, target_locale, context=""):
        # 你的 HTTP 调用
        ...
```

写完立刻能用：`llm.provider: my_llama` 加到 config.yaml。

---

## 5. 审校平台连通性测试

### 5.1 Phrase TMS（Phrase Platform）

Phrase 现在推荐的鉴权模式是**Subject Token Exchange**（RFC 8693）：从 UI 生成的 token 需要先向 IDM 端点换成 Bearer 短期 access token，再拿去调 TMS API。详见 <https://developers.phrase.com/en/api/platform/authentication>。

#### 5.1.1 最省事：`--whoami` 一键探针（推荐）

```bash
export GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN="your_phrase_token"
python scripts/probe_platform.py \
    --platform phrase --region eu --whoami
```

期望输出：

```
[INFO] PhrasePlatform: exchanged subject token for Bearer via https://eu.phrase.com/idm/oauth/token (expires in 14399s)
[OK] whoAmI -> user=your-username role=ADMIN org=your-org (uid=xxx)
```

看到 `[OK] whoAmI` 就说明整条链路（IDM 交换 → Bearer 缓存 → TMS `whoAmI`）全通。**这一步不需要任何 project_id，只要 token 有效就能跑**。

#### 5.1.2 手动 curl 验证（若脚本不方便）

```bash
# 1) IDM 交换 —— 注意 region！EU 账户用 eu.phrase.com，US 账户用 us.phrase.com
curl -s -X POST https://eu.phrase.com/idm/oauth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'grant_type=urn:ietf:params:oauth:grant-type:token-exchange' \
  -d "subject_token=${GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN}"
# → {"access_token":"eyJ...","expires_in":14399,"token_type":"Bearer",...}

# 2) 用返回的 access_token 调 TMS whoAmI
curl -s https://cloud.memsource.com/web/api2/v1/auth/whoAmI \
  -H "Authorization: Bearer eyJ..."
# → {"user":{"userName":"...","role":"ADMIN"}, "organization":{...}}
```

#### 5.1.3 用适配器写一个最小自检脚本

```bash
export GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN="your_phrase_token"
python -c "
import os
from TiMi_HOK_Game_Translator.platforms import PhrasePlatform
p = PhrasePlatform(
    api_base='https://cloud.memsource.com/web/api2',
    api_token='',
    project_id='YOUR_PROJECT_UID',
    extra={'subject_token': os.environ['GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN'],
           'region': 'eu'},
)
print('project name:', p.get_project_name())
"
```

**✅ 通过标准**：打印非空的 project 名称。

**❌ 常见错误**：

| 错误 | 原因 | 处理 |
|---|---|---|
| IDM `invalid_grant` | 区域错了（EU / US 弄反） | 改 `--region` 或 `extra.region` |
| TMS `auth: not logged` | 用了 `ApiToken` 头去调 subject_token 换出的 Bearer，或反之 | 让适配器自动选头，不要手动组装 |
| `AuthInvalidCredentials` | 直接把 subject_token 当用户名密码送去 `/auth/login` | 切换到 subject_token 模式（`extra.subject_token`） |
| `Not Found` 项目 UID | UID 拼错 / 项目在别的组织 | 到 Phrase UI 复制 URL 里的 UID 段 |

#### 5.1.4 遗留 ApiToken 模式（早期 Memsource 账号）

如果你的账号仍然能在 UI 里直接看到长期 ApiToken（无 base64 结构），可以走遗留模式：

```bash
export GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN="phrase_xxx"
python scripts/probe_platform.py \
    --platform phrase --project-id YOUR_UID \
    --file docs/examples/data/example_game.en.json --target vi
```

### 5.2 Crowdin

```bash
export GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN="your_crowdin_pat"
python -c "
import os
from TiMi_HOK_Game_Translator.platforms import CrowdinPlatform
p = CrowdinPlatform(
    api_base='https://api.crowdin.com/api/v2',
    api_token=os.environ['GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN'],
    project_id='YOUR_PROJECT_ID',
)
print('project name:', p.get_project_name())
"
```

企业版租户请把 `api_base` 换成 `https://<org>.api.crowdin.com/api/v2`。

### 5.3 上传 / 建 job / 查状态 / 下载 —— 完整回路

```bash
export GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN="your_token"
python scripts/probe_platform.py \
    --platform phrase \
    --project-id YOUR_PROJECT_UID \
    --file docs/examples/data/example_game.en.json \
    --target vi
```

这个脚本会：
1. `upload_source(en.json)` → 打印 `file_id`；
2. `create_task([file_id], "vi", review_stage="first")` → 打印 `task_id`；
3. `get_task_status(task_id)` → 打印 `status` 与 `percent`；
4. `download_translations(...)` → 保存到 `workspace/probe_out.json`；
5. `delete_task(task_id)` → 清理，避免占用配额。

任何一步失败都会打印**完整 HTTP 请求 + 响应** 供排查（尚未真上传前**先在 UI 里手动删掉遗留 job**）。

---

## 6. 单语种端到端测试

跑一次**最小四步 workflow**：`pull_vcs → translate → validate_data → push_vcs`

```bash
python main.py run \
    --config docs/examples/demo.yaml \
    --language vi \
    --fresh
```

**✅ 通过标准**（3 个都要满足）：

1. 退出码 0；
2. `workspace/vcs/en.json`（或你配的 `source.path`）里所有 entry 的 `target_text` 都以 `[vi] ` 开头（因为用了 mock LLM）；
3. `workspace/workflow_state.json` 里所有状态 `status = true`。

### 6.1 加入真实审校平台

改你的 `config.yaml` 中的 `platform` 段：

```yaml
platform:
  type: phrase
  api_base: https://cloud.memsource.com/web/api2
  project_id: YOUR_PROJECT_UID
  api_token: ""   # 走环境变量 GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN
```

> ℹ️ 配置模型中 **`platform` 段只有一个**，不区分一审/二审。真正的一审/二审路由在**语种
> profile** 的 `reviews.first` / `reviews.second` 中声明，由 `first_review` / `second_review`
> 两个工作流状态分别拾取。顶层 `platform` 只是“默认连接池”：profile 的 `reviews.*`
> 里省略的字段（如 `api_base`、`api_token`）会从顶层回填。详见
> [`docs/configuration.md`](./configuration.md)。

准备一份 `conf/languages/vi.yaml`（本仓库已自带，这里是最小示例）：

```yaml
id: vi
target_locale: vi
source:
  format: json
  path: trunk/tests/fixtures/vi/99.incr.json
reviews:
  first:
    platform: phrase
    project_id: YOUR_PROJECT_UID
    target_language_id: vi
    extra:
      region: eu
workflow:
  - pull_vcs
  - translate
  - first_review
  - validate_data
  - push_vcs
```

```bash
python main.py run \
    --config my_config.yaml \
    --language vi \
    --languages-dir conf/languages/ \
    --fresh
```

---

## 7. 多语种批处理测试

仓库自带的 `conf/languages/` 目录下已经有 14 份 YAML profile：

```
conf/languages/
├── vi.yaml
├── ja.yaml
├── ko.yaml
├── ar.yaml
└── ...（de / es / fr / id / pt-BR / ru / th / tr / zh-Hant / en）
```

然后循环运行：

```bash
for lang in vi ja ko; do
    python main.py run --config my_config.yaml --language "$lang" --fresh
done
```

**✅ 通过标准**：每语种一个独立的 `workspace/<lang>_workflow_state.json`（如果你 `workspace.root: workspace/{language}`）或者共享的 `workflow_state.json` 都全部完成。

---

## 8. 断点续跑验证

**目的**：证明真的可以恢复。

```bash
# 1. 起一次任务但故意中途 kill
python main.py run --config my_config.yaml --language vi --fresh &
sleep 2
kill -9 $!

# 2. 检查状态文件（部分状态应该已完成，部分未完成）
cat workspace/workflow_state.json

# 3. 不带 --fresh 再跑一次
python main.py run --config my_config.yaml --language vi

# 4. 现在所有 status 都应该 = true，且未完成的部分从上次断点继续
```

**✅ 通过标准**：第二次运行只处理**未完成**的状态，日志里能看到大量 `already completed — skipping` 行。

---

## 9. 通知渠道验证

### 9.1 Console（默认）

`python main.py run ...` 结束时直接 stdout 打印一行 "pipeline finished"。

### 9.2 企业微信

```bash
export GAME_TRANS_TOOLCHAIN__NOTIFICATION__TYPE="wecom"
export GAME_TRANS_TOOLCHAIN__NOTIFICATION__WEBHOOK="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
python main.py run --config my_config.yaml --language vi --fresh
```

**通知失败永远不会阻塞主流水线** —— 这是 TiMi_HOK_Game_Translator 的强约定。所以即使 webhook 写错，`python main.py run` 也不会失败，你需要**看日志**里是否有 `Notifier failed:` 警告。

### 9.3 Slack / Email

同理，见 `docs/architecture.md` 中"六个可插拔层"章节。

---

## 附录 A：故障排查速查表

| 错误关键字 | 出现位置 | 处理 |
|---|---|---|
| `Authentication failed` | git/svn/p4 拉代码 | 检查 PAT / 密码 / 是否被墙 |
| `SSL certificate problem` | https 请求 | 企业代理 → 走 `HTTPS_PROXY` 或 `SSL_CERT_FILE` |
| `E155004 working copy is locked` | svn | `svn cleanup` 然后重试 |
| `auth: not logged` | Phrase TMS | 用错认证模式：把 subject_token 当 ApiToken 直接发。切到 `extra.subject_token` 让适配器自动换 Bearer |
| `invalid_grant` | Phrase IDM | 区域错了：EU 账户走 `eu.phrase.com`，US 走 `us.phrase.com` |
| `401 Unauthorized` | Crowdin/OpenAI | token 错 / 配额用尽 |
| `429 Too Many Requests` | LLM | 调低并发 `default_max_workers` |
| `File not found` | source.load | 相对路径基于 `vcs.local_path`，不是当前目录 |
| `KeyError: source_text` | csv/xml 解析 | 确认列名/元素名，参考 `docs/examples/data/example_game.en.*` |
| `pipeline failed` 但没 traceback | runner | 加 `--log-level DEBUG` 或直接看 `workspace/workflow_state.json` 的 error 字段 |

---

## 附录 B：如何准备一个可直接使用的测试仓库

**目标**：复用仓库自带的样例数据与 profile，三步就能跑通最小端到端链路。

### B.1 用 `docs/examples/data/` 作为源文件库

仓库自带 5 种格式的同一批样例词条：

```
docs/examples/data/
├── example_game.en.json
├── example_game.en.yaml
├── example_game.en.xml
├── example_game.en.csv
└── example_game.en.dtxml
```

如果需要在远端 VCS 中验证，自行建一个仓库并把这些文件复制过去：

```bash
# 示例：git 远端仓库
mkdir -p my-i18n-test/locales
cp docs/examples/data/example_game.en.* my-i18n-test/locales/
cd my-i18n-test && git init && git add -A \
    && git commit -m "chore: initial i18n fixtures" \
    && git remote add origin https://github.com/YOUR_ACCOUNT/my-i18n-test.git \
    && git push -u origin main
```

### B.2 复制项目配置并指向你的仓库

在 TiMi_HOK_Game_Translator 项目根：

```bash
cp conf/config.yaml my_config.yaml
# 编辑 my_config.yaml：
#   vcs.type: git
#   vcs.url:  https://github.com/YOUR_ACCOUNT/my-i18n-test.git
#   vcs.local_path: git/my-i18n-test
#   source.format: json
#   source.path:   locales/example_game.en.json
python main.py run --config my_config.yaml --language vi --fresh
```

> 💡 想完全离线验证（不连任何 VCS），把 `vcs.type` 改为 `mock` 即可，相当于直接使用
> 已经准备好的本地文件。参见 [`docs/examples/demo.yaml`](./examples/demo.yaml)。

### B.3 想要多语种？

参考 [`conf/languages/`](../conf/languages/) 下已有的 14 份语种 profile（如
`vi.yaml` / `ja.yaml`），复制一份改 `id / target_locale / reviews / workflow`
即可。或者用脚本一键生成：

```bash
python scripts/generate_language_profiles.py ko ja th     # 批量生成占位 profile
```

按需编辑后运行：

```bash
python main.py run --config my_config.yaml --language vi \
    --languages-dir conf/languages/ --fresh
```

### B.4 加真实审校平台

- **Phrase**：见 [`docs/platforms/phrase.md`](./platforms/phrase.md)
- **Crowdin**：见 [`docs/extending_platforms.md`](./extending_platforms.md)

只需在 `conf/languages/vi.yaml` 的 `reviews.first` / `reviews.second` 段填 `project_id + target_language_id`，把 API Token 通过环境变量注入。**一审二审可以走完全不同的后端**。

---

## 结束语

通过本文档的 9 级测试，你可以确认：

- ✅ Python / CLI / VCS / 网络四大基础环境；
- ✅ VCS 后端（Git / SVN / Perforce）真实连通；
- ✅ 5 种源文件格式全部可解析；
- ✅ LLM 与审校平台真实调通；
- ✅ 单语种端到端流水线可完成；
- ✅ 多语种批处理可并发运行；
- ✅ 断点续跑真的能恢复；
- ✅ 通知渠道不会阻塞主流水线。

每一步都通过后，你的 TiMi_HOK_Game_Translator 环境就**具备了正式接入真实业务项目的能力**。
