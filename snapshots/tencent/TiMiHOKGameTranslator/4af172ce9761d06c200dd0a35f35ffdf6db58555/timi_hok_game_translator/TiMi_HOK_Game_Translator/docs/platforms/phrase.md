# Phrase TMS 平台适配指南

`PhrasePlatform` 是 [Phrase TMS](https://developers.phrase.com/en/api/tms/latest/introduction)（原 Memsource）的官方适配器，支持一审 / 二审 / 轻校对三个 `review_stage`。

## 一句话上手（推荐：Subject Token Exchange）

```json
{
  "id": "vi",
  "target_locale": "vi",
  "reviews": {
    "first": {
      "platform": "phrase",
      "project_id": "abcdef1234",
      "target_language_id": "vi",
      "stop_time": "19:00",
      "extra": {
        "subject_token": "PASTE_YOUR_TOKEN_HERE_OR_USE_ENV",
        "region": "eu",
        "workflow_step_uid": ""
      }
    }
  }
}
```

```bash
export GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN=xxx
python main.py run --language vi --languages-dir configs/languages/
```

## 三种认证模式

| # | 模式 | 何时使用 | 请求头 |
|---|---|---|---|
| 1 | **Subject Token Exchange** ⭐ | 官方 2024+ 推荐；从 Phrase UI *Settings → API tokens → Generate token* 复制的令牌 | `Authorization: Bearer <access_token>` |
| 2 | **Legacy ApiToken** | 早期 Memsource 部署里 UI 生成的长期 token | `Authorization: ApiToken <token>` |
| 3 | **Username + Password** | SSO 关闭且未开放 API token 的场景 | 内部先 `/auth/login` 换 24h ApiToken，然后同模式 2 |

### 模式 1 · Subject Token Exchange（RFC 8693）

参考文档：<https://developers.phrase.com/en/api/platform/authentication>

**流程**：
1. 从 Phrase UI *Settings → API tokens → Generate token* 复制得到形如 `a2todDBjNXBEVjZM...` 的字符串（内部是 base64 的 `client_id:client_secret`）；
2. 适配器把它作为 `subject_token`，向 IDM 端点交换出 Bearer 短期 access token：
   ```
   POST https://eu.phrase.com/idm/oauth/token
   Content-Type: application/x-www-form-urlencoded

   grant_type=urn:ietf:params:oauth:grant-type:token-exchange&subject_token=<TOKEN>
   ```
3. 服务器返回 `{"access_token":"eyJ...", "expires_in":14399, "token_type":"Bearer"}`；适配器缓存 Bearer 直到过期前 60s，自动无感刷新；
4. 后续调用 TMS API 均使用 `Authorization: Bearer <access_token>`。

**区域切换**：EU 账户走 `https://eu.phrase.com`，US 账户走 `https://us.phrase.com`。通过 `extra.region: "eu" | "us"` 指定，默认 EU。

**注入方式**（三选一）：

```bash
# A. 环境变量（推荐用于 CI / 服务端）
export GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN=xxx

# B. 语种配置 JSON 的 reviews.<stage>.extra.subject_token
```

```yaml
# C. 全局 config.yaml
platform:
  type: phrase
  extra:
    subject_token: xxx
    region: eu
```

### 模式 2 · Legacy ApiToken

```bash
export GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN=phrase_xxx
python main.py run --language vi --languages-dir configs/languages/
```

请求头 `Authorization: ApiToken <token>`。适用于早期 Memsource 后台仍能查到「长期 API Token」的账号。

### 模式 3 · Username + Password

首次调用时适配器会 `POST /web/api2/v3/auth/login`（若 tenant 未升级则回退到 `/v1/auth/login`）换取 **24 小时**有效 token。多公司账号需在 `extra.user_uid` 里指定登录到哪家。

401 自动重登：在**模式 1** 与**模式 3** 下，一旦服务器返回 401（token 过期），适配器会强制重新认证一次再重试。

## API 基址

- **TMS API**：`https://cloud.memsource.com/web/api2`（EU / US 均使用同一域名，区域信息由 Bearer 的 `aud` claim 决定）；
- **IDM（仅模式 1）**：`https://eu.phrase.com` 或 `https://us.phrase.com`；
- 私有部署：覆盖 `api_base` 与 `idm_base`。

## 端点覆盖

| 用途 | HTTP 方法 & 路径 |
|---|---|
| IDM 交换 Bearer（模式 1） | `POST <idm_base>/idm/oauth/token` |
| 登录换 token（模式 3，首选） | `POST /web/api2/v3/auth/login` |
| 登录换 token（模式 3，回退） | `POST /web/api2/v1/auth/login` |
| 当前身份 whoAmI | `GET /web/api2/v1/auth/whoAmI` |
| 上传 job（源文件） | `POST /web/api2/v1/projects/{projectUid}/jobs` (multipart) |
| 查 job | `GET /web/api2/v1/projects/{projectUid}/jobs/{jobUid}` |
| 下载译文 | `GET /web/api2/v1/projects/{projectUid}/jobs/{jobUid}/targetFile` |
| 删除 job | `DELETE /web/api2/v1/projects/{projectUid}/jobs` |
| 查项目 | `GET /web/api2/v1/projects/{projectUid}` |

## file_id 编码

`upload_source` 返回的 `file_id` 是不透明字符串 `"phrase::<projectUid>::<jobUid>"`。这样即便适配器在崩溃后重启，只要从 `AutoSaveDict` 里读回 `file_id` 也能立即定位到原任务，无需保留额外本地映射。

## 状态映射

| Phrase 状态 | 框架 `TaskStatus` |
|---|---|
| `NEW` / `EMAILED` | `PENDING` |
| `ASSIGNED` / `ACCEPTED_BY_LINGUIST` / `COMPLETED_BY_LINGUIST` | `IN_PROGRESS` |
| `COMPLETED` / `DELIVERED` | `APPROVED` |
| `DECLINED_BY_LINGUIST` / `CANCELLED` / `REJECTED` | `REJECTED` |

未识别状态映射为 `UNKNOWN` —— 由调用方决定重试策略。

## 常用 extra 键

| 键 | 类型 | 说明 |
|---|---|---|
| `subject_token` | str | ⭐ 模式 1：Phrase UI 生成的令牌，会被换成 4 小时 Bearer |
| `region` | str | ⭐ 模式 1：`"eu"`（默认）/ `"us"` |
| `idm_base` | str | 模式 1：覆盖 IDM 域名（私有部署或代理时使用） |
| `username` / `password` | str | 模式 3：降级换 token 凭据 |
| `user_uid` | str | 模式 3：多公司账号时指定登录哪家；`/auth/login` 请求体的 `userUid` |
| `workflow_step_uid` | str | 把新建 job 绑定到指定 workflow step |
| `timeout_seconds` | float | HTTP 超时（默认 30s） |
| `retries` | int | 网络失败重试次数（默认 3） |
| `retry_interval_seconds` | float | 重试间隔（默认 30s） |
| `session_factory` | callable | 测试专用：返回自定义 `requests.Session` |
| `clock` | callable | 测试专用：注入自定义 UNIX 时间戳源，用于测试 Bearer 过期刷新 |

## 快速验证令牌是否可用（`--whoami`）

拿到 subject_token 后无需真正上传文件，用探针脚本一键验证账号连通：

```bash
export GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN=xxx
python scripts/probe_platform.py --platform phrase --region eu --whoami
```

期望输出：

```
[INFO] PhrasePlatform: exchanged subject token for Bearer via https://eu.phrase.com/idm/oauth/token (expires in 14399s)
[OK] whoAmI -> user=your-username role=ADMIN org=your-org (uid=xxx)
```

一旦看到这行 `[OK] whoAmI`，说明**整套认证链路完全打通**：`subject_token → IDM 交换 → Bearer 缓存 → TMS API 调用 → 用户身份返回`。

## 已知限制

- Phrase 原生不区分「approved / pending」段，本适配器通过 `get_task_status` 的整体 `status` 近似：`COMPLETED` 视为全部通过，其余视为 pending。真正需要按段落粒度分裂的项目应覆盖 `split_approved_data`。
- `export_review_report` 仅生成一个基于 job 元数据的简短 txt 报告，不调用 Phrase 的 Analytics 高级模块。

## 常见问题

**Q：`AuthInvalidCredentials` / 401 `auth: not logged`。**
A：优先检查是否使用了 subject_token 模式（模式 1）。传统 `ApiToken` 头对新发的 Phrase Platform 令牌无效 —— 那种令牌**必须**先走 IDM Token Exchange 换成 Bearer。

**Q：IDM 返回 `invalid_grant`。**
A：99% 是区域错了。EU 账户去 `https://eu.phrase.com/idm/oauth/token`，US 账户去 `https://us.phrase.com/idm/oauth/token`。设置 `extra.region` 或 `--region eu|us`。

**Q：出现 `PhrasePlatform: project_id is empty`。**
A：`reviews.first.project_id` 或全局 `platform.project_id` 至少要有一个非空。

**Q：想测适配器却不想联网。**
A：注入 `extra["session_factory"] = lambda: FakeSession(...)`，详见 [`tests/unit/test_platform_phrase.py`](../../tests/unit/test_platform_phrase.py)。
