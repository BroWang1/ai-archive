# pylint: disable=line-too-long

"""字段 schema —— 面向 UI 的"配置项清单"。

把 YAML 的每个关键字段抽象成一个描述项：
    * key:            点分路径（如 ``vcs.url``）
    * label:          中文标签
    * type:           表单控件类型（string / password / int / float / bool / select / list / dict / textarea）
    * required:       是否必填（在当前"启用场景"下）
    * placeholder:    输入框占位符
    * example:        示例值（给用户参考）
    * help:           详细说明（显示在输入框下方）
    * options:        select / radio 的候选项
    * secret:         是否敏感字段（UI 用 password 组件 + 建议走环境变量）
    * env_hint:       对应的环境变量名（可选）
    * default:        默认值
    * group:          表单分组标题

本模块**只是**面向 UI 的描述数据，并不承担数据校验职责——真正校验仍走
框架内部的 ``validate(config)``。
"""



from __future__ import annotations

from typing import Any, Dict, List


def _f(**kw: Any) -> Dict[str, Any]:
    """构造一个字段描述，key 必填，其他可选。

    支持的额外元信息（前端据此做条件渲染/校验）：
        depends_on: str
            父字段路径（如 ``"provider"`` 或 ``"vcs.type"``）。配合
            ``applies_to`` / ``required_if`` 使用。
        applies_to: list[str]
            仅当父字段的值 ∈ 列表时才显示本字段；未命中则 UI 隐藏。
        required_if: list[str]
            仅当父字段的值 ∈ 列表时才视为必填；否则按选填处理。
    """
    kw.setdefault("required", False)
    kw.setdefault("secret", False)
    return kw


# =============================================================================
# 全局 config.yaml 的字段清单
# =============================================================================
def global_config_schema() -> List[Dict[str, Any]]:
    return [
        # ----- 项目基础 -----
        _f(key="project_code", label="项目标识 project_code",
           type="string", required=True, group="项目基础",
           placeholder="my_game", example="dragon_quest_mobile",
           help="产品 slug，出现在日志前缀、通知标题、状态文件名；建议小写字母+下划线。"),
        _f(key="stage", label="发版阶段 stage",
           type="select", group="项目基础",
           options=["exp_week", "trunk_week", "pub_week", "hot_week"],
           default="trunk_week",
           help="当前流水线阶段，可被命令行 --stage 覆盖。"),
        _f(key="source_locale", label="源语种 source_locale",
           type="string", required=True, group="项目基础",
           default="zh-CN", example="zh-CN",
           help="源语种 BCP-47 代码。中国出海项目通常固定为 zh-CN。"),

        # ----- VCS -----
        _f(key="vcs.type", label="VCS 类型",
           type="select", required=True, group="版本控制",
           options=["local", "git", "svn", "perforce"],
           default="local",
           help="选 **local** 可零依赖试跑（无需远端 URL / 账号密码，流水线直接在本地工作副本路径读写源文件与译文）；真实项目选对应的后端。老配置里的 `mock` 自动视为 `local`。"),
        _f(key="vcs.url", label="仓库地址 vcs.url",
           type="string", group="版本控制",
           depends_on="vcs.type", applies_to=["git", "svn", "perforce"],
           required_if=["git", "svn", "perforce"],
           placeholder="https://github.com/you/game-i18n.git",
           example="https://svn.example.com/game-i18n/trunk",
           help="远端仓库地址；选 mock 时不需要。"),
        _f(key="vcs.local_path", label="本地工作副本 vcs.local_path",
           type="string", required=True, group="版本控制",
           placeholder="D:/workspace/game-i18n  或  workspace/repo",
           example="C:/data/game-i18n   或   svn/game",
           help="**所有 VCS 类型都必填**。可填**绝对路径**（如 `D:/workspace/xxx`，推荐 mock 场景使用，流水线直接读写该目录）；也可填**相对路径**（factory 自动拼接 workspace 根，git/svn/perforce 常用）；不要加 'workspace/' 前缀。"),
        _f(key="vcs.revision", label="修订号 vcs.revision",
           type="string", group="版本控制", default="HEAD",
           depends_on="vcs.type", applies_to=["git", "svn", "perforce"],
           help="默认 HEAD，可指定 commit / changelist / rev。"),
        _f(key="vcs.username", label="用户名 vcs.username",
           type="string", group="版本控制", secret=True,
           depends_on="vcs.type", applies_to=["svn", "perforce"],
           env_hint="GAME_TRANS_TOOLCHAIN__VCS__USERNAME",
           help="建议走环境变量注入；仅 svn / perforce 场景需要。"),
        _f(key="vcs.password", label="密码 vcs.password",
           type="password", group="版本控制", secret=True,
           depends_on="vcs.type", applies_to=["svn", "perforce"],
           env_hint="GAME_TRANS_TOOLCHAIN__VCS__PASSWORD",
           help="**严禁明文提交**；优先走环境变量。"),
        _f(key="vcs.cli_timeout_seconds", label="CLI 超时(秒)",
           type="int", group="版本控制", default=600,
           depends_on="vcs.type", applies_to=["git", "svn", "perforce"],
           help="单条 svn / git / p4 命令超时时间。"),
        _f(key="vcs.default_commit_message", label="默认提交消息",
           type="string", group="版本控制",
           default="[TiMi_HOK_Game_Translator] commit translation data",
           depends_on="vcs.type", applies_to=["git", "svn", "perforce"],
           help="push_vcs 阶段的提交消息兜底。"),

        # ----- LLM profile 引用 -----
        _f(key="llm_profile", label="默认 LLM profile",
           type="llm_profile_ref", group="LLM 引用", required=True,
           placeholder="echo",
           help="指向 conf/llm.yaml 的 profiles 下的 key，必须存在；下拉列表来自已配置的 profiles。"),

        # ----- 全局平台（统一审校平台配置） -----
        _f(key="platform.type", label="审校平台 type",
           type="select", group="审校平台",
           options=["none", "phrase", "crowdin"], default="none",
           help="**统一**审校平台 —— 一审 / 二审 / 轻校对**都用这一个平台**，只是在各语种的 reviews.* 下填不同的 project_id 来区分项目。"),
        _f(key="platform.api_base", label="api_base",
           type="string", group="审校平台",
           depends_on="platform.type", applies_to=["phrase", "crowdin"],
           placeholder="https://api.crowdin.com/api/v2",
           help="Phrase 常见：https://cloud.memsource.com/web/api2 ；EU 账户：https://cloud.memsource.com/web/api2 ；US 账户：https://us.cloud.memsource.com/web/api2"),
        _f(key="platform.api_token", label="api_token",
           type="password", group="审校平台", secret=True,
           depends_on="platform.type", applies_to=["phrase", "crowdin"],
           env_hint="GAME_TRANS_TOOLCHAIN__PLATFORM__API_TOKEN",
           help="**敏感**；Crowdin 使用；Phrase 推荐改用下方 subject_token。建议走环境变量。"),
        _f(key="platform.project_id", label="默认 project_id",
           type="string", group="审校平台",
           depends_on="platform.type", applies_to=["phrase", "crowdin"],
           help="全局默认项目；多项目场景下在语种 profile 的 reviews.* 阶段覆盖。"),
        _f(key="platform.extra.region", label="Phrase region",
           type="select", group="审校平台",
           depends_on="platform.type", applies_to=["phrase"],
           options=["", "eu", "us"],
           help="仅 Phrase 使用：EU 账户 → eu，US 账户 → us。"),
        _f(key="platform.extra.subject_token", label="Phrase subject_token",
           type="password", group="审校平台", secret=True,
           depends_on="platform.type", applies_to=["phrase"],
           env_hint="GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN",
           help="**敏感**；Phrase 推荐的鉴权方式，走环境变量更安全。"),

        # ----- 通知 -----
        _f(key="notification.type", label="通知渠道 type",
           type="select", group="通知",
           options=["none", "console", "wecom"],
           default="none",
           help="none 不通知；console 走日志；wecom 走企业微信群机器人 webhook。"),
        _f(key="notification.webhook", label="webhook 地址",
           type="password", group="通知", secret=True,
           depends_on="notification.type", applies_to=["wecom"],
           required_if=["wecom"],
           env_hint="GAME_TRANS_TOOLCHAIN__NOTIFICATION__WEBHOOK",
           placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
           help="企业微信群机器人地址，**敏感**，建议走环境变量注入。"),

        # ----- Workspace / 日志 -----
        _f(key="workspace.root", label="workspace 绝对路径",
           type="string", group="工作区",
           help="留空则取 ${CWD}/workspace。"),
        _f(key="workspace.subdir", label="workspace 子目录",
           type="string", group="工作区", default="workspace"),
        _f(key="workspace.state_filename", label="状态文件名",
           type="string", group="工作区", default="workflow_state.json",
           help="断点续跑状态落盘文件名。"),
        _f(key="logging.level", label="日志级别",
           type="select", group="日志",
           options=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
           default="INFO"),
        _f(key="logging.directory", label="日志目录",
           type="string", group="日志", default="logs"),
        _f(key="logging.filename", label="日志文件名",
           type="string", group="日志", default="TiMi_HOK_Game_Translator.log"),
        _f(key="logging.console", label="同时输出到控制台",
           type="bool", group="日志", default=True),
    ]


# =============================================================================
# 单个 LLM profile 的字段清单
# =============================================================================
def llm_profile_schema() -> List[Dict[str, Any]]:
    return [
        # ---------- 基础（所有 provider 通用） ----------
        _f(key="name", label="profile 名称",
           type="string", required=True, group="基础",
           placeholder="my_openai_gpt4o_mini",
           help="**必须全局唯一**。被 config.yaml 的 llm_profile 字段或语种 profile 的 llm_profile 字段按名引用，重名会导致冲突。建议格式：`<provider>_<model_short>`，例如 `openai_gpt4o_mini`、`hunyuan_mt2_plus`、`venus_deepseek_v3`。注意：带 `_example` 后缀的是模板示例，请复制后重命名再使用。"),
        _f(key="provider", label="provider 提供商",
           type="select", required=True, group="基础",
           options=["echo", "openai", "openai_compatible", "anthropic", "gemini", "venus", "hunyuan_translation"],
           default="echo",
           help="选 **echo** 零依赖试跑（回显式占位 LLM，把原文打上语种标签输出，无需 api_key / api_base）；openai_compatible 可对接 DeepSeek / Kimi / GLM / Qwen 等；gemini 走 Google AI Studio。老配置里的 `mock` 自动视为 `echo`。"),
        _f(key="model", label="模型名 model",
           type="string", group="基础",
           depends_on="provider", applies_to=["openai", "openai_compatible", "anthropic", "gemini", "venus", "hunyuan_translation"],
           required_if=["openai", "openai_compatible", "anthropic", "gemini", "venus", "hunyuan_translation"],
           placeholder="gpt-4o-mini", example="gemini-2.5-flash / claude-3-5-sonnet",
           help="模型 ID；gemini 常用 gemini-2.5-flash / gemini-2.5-pro；venus / hunyuan_translation 走的是服务端模型路由。"),

        # ---------- 接入（根据 provider 条件显示） ----------
        _f(key="api_base", label="api_base",
           type="string", group="接入",
           depends_on="provider",
           applies_to=["openai", "openai_compatible", "anthropic", "gemini", "venus", "hunyuan_translation"],
           required_if=["openai_compatible", "venus", "hunyuan_translation"],
           placeholder="https://api.openai.com/v1",
           help="**OpenAI** 官方可省；**gemini** 默认 `https://generativelanguage.googleapis.com`；**venus** 常用 `http://v2.open.venus.oa.com/chat/single`（内网）；**openai_compatible** / **hunyuan_translation** 必填完整 URL。"),
        _f(key="api_key", label="api_key",
           type="password", group="接入", secret=True,
           depends_on="provider",
           applies_to=["openai", "openai_compatible", "anthropic", "gemini", "hunyuan_translation"],
           required_if=["openai", "openai_compatible", "anthropic", "gemini", "hunyuan_translation"],
           env_hint="GAME_TRANS_TOOLCHAIN__LLM__API_KEY",
           help="**敏感**；建议走环境变量。gemini 也支持 GOOGLE_API_KEY。**venus 的凭据**不在此处填写，请到下方「Venus 专属」分组分别填 secret_id / secret_key。"),

        # ---------- Venus 专属 ----------
        _f(key="extra.server_id", label="server_id",
           type="int", group="Venus 专属",
           depends_on="provider", applies_to=["venus"], required_if=["venus"],
           placeholder="3", example="3 / 42",
           help="Venus 平台的服务 ID（整数），**必填**。来自 Venus 控制台 → 服务管理。"),
        _f(key="extra.app_group_id", label="app_group_id",
           type="int", group="Venus 专属",
           depends_on="provider", applies_to=["venus"], required_if=["venus"],
           placeholder="4", example="4 / 128",
           help="Venus 平台的应用组 ID（整数），**必填**。来自 Venus 控制台 → 应用组。"),
        _f(key="extra.secret_id", label="secret_id",
           type="password", group="Venus 专属", secret=True,
           depends_on="provider", applies_to=["venus"],
           env_hint="GAME_TRANS_TOOLCHAIN__LLM__API_KEY",
           placeholder="Venus 控制台生成的 secret_id",
           help="Venus 鉴权凭据之一，与 secret_key 配对使用。**敏感**，上线前请改走环境变量 `GAME_TRANS_TOOLCHAIN__LLM__API_KEY=<secret_id>:<secret_key>`。"),
        _f(key="extra.secret_key", label="secret_key",
           type="password", group="Venus 专属", secret=True,
           depends_on="provider", applies_to=["venus"],
           env_hint="GAME_TRANS_TOOLCHAIN__LLM__API_KEY",
           placeholder="Venus 控制台生成的 secret_key",
           help="Venus 鉴权凭据之一，与 secret_id 配对使用。**敏感**，上线前请改走环境变量。"),
        _f(key="extra.model_params", label="model_params 生成参数",
           type="dict", group="Venus 专属",
           depends_on="provider", applies_to=["venus"],
           placeholder='{"repetition_penalty": 1.1, "do_sample": false}',
           example='{"repetition_penalty": 1.1, "do_sample": false, "top_p": 0.9, "top_k": 40}',
           help="**JSON 对象**，透传到 Venus 请求体，用于控制解码行为。常用键：`repetition_penalty`（重复惩罚，1.0~2.0）、`do_sample`（是否采样）、`top_p`、`top_k`、`max_new_tokens` 等。留空则不传。"),

        # ---------- 混元翻译专属 ----------
        _f(key="extra.wsid", label="wsid 工作空间 ID",
           type="string", group="混元翻译专属",
           depends_on="provider", applies_to=["hunyuan_translation"], required_if=["hunyuan_translation"],
           help="混元翻译服务的工作空间 ID，**必填**。"),
        _f(key="extra.top_p", label="top_p",
           type="float", group="混元翻译专属", default=1.0,
           depends_on="provider", applies_to=["hunyuan_translation"],
           help="解码参数：核采样阈值，取 0.0~1.0。"),
        _f(key="extra.top_k", label="top_k",
           type="int", group="混元翻译专属", default=-1,
           depends_on="provider", applies_to=["hunyuan_translation"],
           help="解码参数：候选词数量，-1 表示不限制。"),
        _f(key="extra.repetition_penalty", label="repetition_penalty",
           type="float", group="混元翻译专属", default=1.0,
           depends_on="provider", applies_to=["hunyuan_translation"],
           help="重复惩罚系数，大于 1 会抑制重复，范围 1.0~2.0。"),

        # ---------- 调用参数（所有真实 provider 通用） ----------
        _f(key="temperature", label="temperature",
           type="float", group="调用参数", default=0.2,
           depends_on="provider",
           applies_to=["openai", "openai_compatible", "anthropic", "gemini", "venus", "hunyuan_translation"],
           help="翻译建议 0.1 ~ 0.3，稳定性优先。"),
        _f(key="max_tokens", label="max_tokens",
           type="int", group="调用参数", default=1024,
           depends_on="provider",
           applies_to=["openai", "openai_compatible", "anthropic", "gemini", "venus", "hunyuan_translation"],
           help="单次响应上限；长文本建议 4096。"),
        _f(key="batch_size", label="batch_size",
           type="int", group="调用参数", default=16,
           depends_on="provider",
           applies_to=["openai", "openai_compatible", "anthropic", "gemini", "venus", "hunyuan_translation"],
           help="单次打包多少条 Entry；越大越省调用次数但更易超时。"),

        # ---------- 重试与超时 ----------
        _f(key="timeout_seconds", label="timeout_seconds",
           type="int", group="重试与超时", default=60,
           depends_on="provider",
           applies_to=["openai", "openai_compatible", "anthropic", "gemini", "venus", "hunyuan_translation"]),
        _f(key="retries", label="retries",
           type="int", group="重试与超时", default=3,
           depends_on="provider",
           applies_to=["openai", "openai_compatible", "anthropic", "gemini", "venus", "hunyuan_translation"]),
        _f(key="retry_interval_seconds", label="retry_interval_seconds",
           type="int", group="重试与超时", default=10,
           depends_on="provider",
           applies_to=["openai", "openai_compatible", "anthropic", "gemini", "venus", "hunyuan_translation"]),
    ]


# =============================================================================
# 语种 profile 的字段清单
# =============================================================================
def language_profile_schema() -> List[Dict[str, Any]]:
    return [
        # ----- 基础 -----
        _f(key="id", label="语种 ID",
           type="string", required=True, group="基础",
           placeholder="vi / ja / ko",
           help="与文件名一致的短 ID。"),
        _f(key="display_name", label="显示名",
           type="string", group="基础",
           placeholder="越南语",
           help="日志 / 通知中使用的中文名。"),
        _f(key="source_locale", label="source_locale",
           type="string", group="基础", default="zh-CN"),
        _f(key="target_locale", label="target_locale",
           type="string", required=True, group="基础",
           placeholder="vi",
           help="BCP-47 代码，如 vi、ja、ko、ar、tr。"),
        _f(key="locale_names.cn", label="locale_names.cn",
           type="string", group="基础", placeholder="越南语",
           help="提示词中语种名的中文显示覆盖。"),
        _f(key="locale_names.en", label="locale_names.en",
           type="string", group="基础", placeholder="Vietnamese",
           help="提示词中语种名的英文显示覆盖。"),

        # ----- source -----
        _f(key="source.format", label="源文件格式",
           type="select", required=True, group="源文件",
           options=["xlsx", "json", "yaml", "xml", "csv", "dtxml", "xliff"],
           default="xlsx",
           help="游戏项目强烈推荐 xlsx（支持 EnTerms/Terms 术语列）。💡 切换此项时，下方「源文件路径」若已是常见后缀会**自动同步**后缀。"),
        _f(key="source.path", label="源文件路径",
           type="string", required=True, group="源文件",
           placeholder="trunk/tests/fixtures/vi/99.incr.xlsx",
           help="**相对于** vcs.local_path 的路径。后缀建议与上方「源文件格式」一致（切换格式时会自动同步常见后缀）。"),
        _f(key="source.encoding", label="encoding",
           type="string", group="源文件", default="utf-8"),

        # ----- LLM / 策略 -----
        _f(key="llm_profile", label="llm_profile",
           type="llm_profile_ref", required=True, group="翻译策略",
           placeholder="echo",
           help="必须存在于 conf/llm.yaml 的 profiles 中；下拉列表来自已配置的 profiles。"),
        _f(key="strategy_config.class", label="策略类名",
           type="select", group="翻译策略",
           options=["", "GenericTranslationStrategy", "TwoStepTranslationStrategy"],
           help="留空走装饰器或 Generic 一步直译；小语种（de/fr/ru/tr/ar 等）推荐 TwoStepTranslationStrategy。"),
        _f(key="strategy_config.pivot_locale", label="pivot_locale（两步策略专属）",
           type="string", group="翻译策略", default="en",
           help="两步策略的中转语种，默认 en。"),
        _f(key="strategy_config.display_name", label="策略显示名",
           type="string", group="翻译策略", placeholder="越南语翻译"),
        _f(key="strategy_config.use_concurrent_by_default", label="默认并发",
           type="bool", group="翻译策略", default=True),
        _f(key="strategy_config.default_max_workers", label="并发线程数",
           type="int", group="翻译策略", default=32),
        _f(key="strategy_config.progress_log_interval", label="进度日志间隔",
           type="int", group="翻译策略", default=100),

        # ----- 一审 -----
        # 说明：一审是否启用，取决于 workflow 是否包含 first_review 状态 +
        # project_id/project_name 是否填写；平台类型统一走全局 platform.type。
        _f(key="reviews.first.project_id", label="一审 project_id",
           type="string", group="一审（first_review）",
           help="留空则跳过一审。Phrase 项目 UID / Crowdin 项目数字 ID。"),
        _f(key="reviews.first.project_name", label="一审 project_name",
           type="string", group="一审（first_review）",
           placeholder="VI First Review",
           help="仅用于日志 / 通知显示的项目名称。"),
        _f(key="reviews.first.target_language_id", label="一审 target_language_id",
           type="string", group="一审（first_review）",
           placeholder="vi",
           help="平台侧的语种 ID（可能与 BCP-47 不同，Phrase 用 vi、Crowdin 用数字 ID）。"),
        _f(key="reviews.first.stop_time", label="一审截止 stop_time",
           type="string", group="一审（first_review）", placeholder="17:00",
           help="HH:MM 绝对时间；或 +5m / +2h 相对时间。到点未完成会强制跳过。"),
        _f(key="reviews.first.poll_interval_seconds", label="轮询间隔(秒)",
           type="int", group="一审（first_review）", default=60),

        # ----- 二审 -----
        _f(key="reviews.second.project_id", label="二审 project_id",
           type="string", group="二审（second_review）",
           help="留空则跳过二审。"),
        _f(key="reviews.second.project_name", label="二审 project_name",
           type="string", group="二审（second_review）",
           placeholder="VI Second Review"),
        _f(key="reviews.second.target_language_id", label="二审 target_language_id",
           type="string", group="二审（second_review）"),
        _f(key="reviews.second.stop_time", label="二审截止 stop_time",
           type="string", group="二审（second_review）", placeholder="18:00"),
        _f(key="reviews.second.poll_interval_seconds", label="轮询间隔(秒)",
           type="int", group="二审（second_review）", default=60),

        # ----- 轻校对 -----
        _f(key="reviews.light.project_id", label="轻校对 project_id",
           type="string", group="轻校对（light_review）",
           help="留空则跳过轻校对。"),
        _f(key="reviews.light.project_name", label="轻校对 project_name",
           type="string", group="轻校对（light_review）"),

        # ----- 通知 -----
        _f(key="notification.type", label="通知渠道",
           type="select", group="通知",
           options=["none", "console", "wecom"],
           default="console",
           help="留空或与全局一致时，运行时会**字段级继承** config.yaml 的 notification 配置。"),
        _f(key="notification.webhook", label="webhook",
           type="password", group="通知", secret=True,
           depends_on="notification.type", applies_to=["wecom"],
           env_hint="GAME_TRANS_TOOLCHAIN__NOTIFICATION__WEBHOOK",
           help="企业微信群机器人地址。**留空自动继承全局 config.yaml 的 webhook**；填入则覆盖。敏感字段，建议走环境变量。"),
        _f(key="notification.mentioned", label="需要 @ 的用户",
           type="list", group="通知",
           depends_on="notification.type", applies_to=["wecom"],
           help="数组形式，如 ['user_a', 'user_b']。**留空自动继承全局 mentioned 列表**。"),

        # ----- 工作流 -----
        _f(key="workflow", label="工作流状态",
           type="workflow", required=True, group="工作流编排",
           help=""),
        _f(key="merge_start_time", label="merge_start_time",
           type="string", group="工作流编排",
           placeholder="08:30",
           help="空=立即执行；HH:MM=等到当日该时刻再合并。"),
    ]


def get_schema(kind: str) -> List[Dict[str, Any]]:
    if kind == "global":
        return global_config_schema()
    if kind == "llm_profile":
        return llm_profile_schema()
    if kind == "language":
        return language_profile_schema()
    raise ValueError(f"unknown schema kind: {kind!r}")
