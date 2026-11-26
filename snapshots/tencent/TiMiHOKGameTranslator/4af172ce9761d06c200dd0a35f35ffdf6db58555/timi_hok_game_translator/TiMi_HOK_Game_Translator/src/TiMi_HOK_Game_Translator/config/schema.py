"""带类型注解的配置 schema。

整个框架由一棵 dataclass 树驱动，目的在于：

* 每个字段都有**默认值**（确保一份空白 ``config.yaml`` 也能启动）；
* 每个字段都有**类型注解**，供 :func:`config.loader.load`
  在 YAML/env/CLI 层之间自动转换类型；
* 导出当前生效配置时行为确定且安全（敏感字段自动脱敏）。

用户一般不需手工构造这些 dataclass——直接调用
:func:`TiMi_HOK_Game_Translator.config.load` 即可。
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..commons import (
    DEFAULT_HTTP_RETRIES,
    DEFAULT_HTTP_RETRY_INTERVAL_SECONDS,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_LLM_BATCH_SIZE,
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_LOG_DIRNAME,
    DEFAULT_STATE_FILENAME,
    DEFAULT_VCS_CLI_TIMEOUT_SECONDS,
    DEFAULT_VCS_COMMIT_MESSAGE,
    DEFAULT_WORKSPACE_DIRNAME,
    SENSITIVE_FIELD_MARKERS,
    SENSITIVE_MASK,
    LLMProvider,
    LogLevel,
    NotifierType,
    PlatformType,
    ReviewStage,
    SourceFormat,
    Stage,
    VcsType,
)


# ---------------------------------------------------------------------------
# 子区域
# ---------------------------------------------------------------------------
@dataclass
class VcsConfig:
    """版本控制配置。"""

    type: str = VcsType.MOCK.value
    """后端类型，取值参见 :class:`VcsType`。"""

    url: str = ""
    """仓库地址（``svn://…`` / ``https://…`` / ``ssh://…``）。"""

    revision: str = "HEAD"
    """目标版本 / commit / changelist。"""

    local_path: str = ""
    """本地工作副本目录；为空时使用 ``{workspace}/vcs``。"""

    username: str = ""
    """登录用户名；建议从环境变量注入。"""

    password: str = ""
    """登录密码/密钥；建议从环境变量注入。"""

    cli_timeout_seconds: int = DEFAULT_VCS_CLI_TIMEOUT_SECONDS
    default_commit_message: str = DEFAULT_VCS_COMMIT_MESSAGE

    extra: Dict[str, Any] = field(default_factory=dict)
    """后端自定义参数（如 Perforce 的 ``p4port`` 、 Git 的 ``ssh_key``）。"""


@dataclass
class SourceConfig:
    """本地化源文件配置。"""

    format: str = SourceFormat.JSON.value
    """格式标识，取值参见 :class:`SourceFormat`。"""

    path: str = ""
    """待加载/写入的文件路径（相对于 workspace）。"""

    encoding: str = "utf-8"

    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMConfig:
    """LLM 提供商配置。"""

    provider: str = LLMProvider.MOCK.value
    model: str = ""
    temperature: float = DEFAULT_LLM_TEMPERATURE
    max_tokens: int = DEFAULT_LLM_MAX_TOKENS
    batch_size: int = DEFAULT_LLM_BATCH_SIZE
    timeout_seconds: int = DEFAULT_HTTP_TIMEOUT_SECONDS
    retries: int = DEFAULT_HTTP_RETRIES
    retry_interval_seconds: int = DEFAULT_HTTP_RETRY_INTERVAL_SECONDS

    # 敏感字段：``dump`` 会自动脱敏。
    api_key: str = ""
    api_base: str = ""

    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlatformConfig:
    """翻译/审校平台适配器配置。"""

    type: str = PlatformType.NONE.value
    api_base: str = ""

    # 敏感字段：``dump`` 会自动脱敏。
    api_token: str = ""
    project_id: str = ""

    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationConfig:
    """通知渠道配置。"""

    type: str = NotifierType.CONSOLE.value

    # 敏感字段：``dump`` 会自动脱敏。
    webhook: str = ""
    mentioned: List[str] = field(default_factory=list)

    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkspaceConfig:
    """运行时的文件布局配置。"""

    root: str = ""
    """workspace 的绝对路径；为空时默认为 ``$PWD/workspace``。"""

    subdir: str = DEFAULT_WORKSPACE_DIRNAME
    state_filename: str = DEFAULT_STATE_FILENAME


@dataclass
class LoggingConfig:
    """日志配置（级别 + 文件路径）。"""
    level: str = LogLevel.INFO.value
    directory: str = DEFAULT_LOG_DIRNAME
    filename: str = "TiMi_HOK_Game_Translator.log"
    console: bool = True


# ---------------------------------------------------------------------------
# 单语种配置 profile（通过 ``conf/languages/<lang>.yaml``/``*.json``
# 加载的产品无关形式）。取配置文件并转为
# :class:`LanguageProfile` 的加载器见
# :mod:`TiMi_HOK_Game_Translator.config.language_loader`。
# ---------------------------------------------------------------------------
@dataclass
class ReviewConfig:
    """单个审校阶段在翻译平台上的配置。

    字段：
        stage: 本记录服务于哪一轮审校（LIGHT / FIRST / SECOND），
            取值参见 :class:`~TiMi_HOK_Game_Translator.commons.ReviewStage`。
        platform: 平台类型标识（如 ``"phrase"`` / ``"crowdin"`` / ``"none"``），
            由 :func:`TiMi_HOK_Game_Translator.platforms.factory.build_review_tool` 解析为具体类。
        project_id: 平台侧的项目/工作区 ID。
        project_name: 人可读的项目名，用于通知。
        api_base / api_token: 可选的阶段级凭据覆盖；为空时使用
            全局 :class:`PlatformConfig`。**敏感字段**，
            ``config dump`` 会脱敏。
        target_language_id: 平台侧的语种代码（各平台可能与 BCP-47 不同）。
        webhook_url / mentioned: 阶段级通知覆盖。
        stop_time: 本地时区下的审校轮询截止时间（``"HH:MM"`` 格式，空串代表禁用）。
        extra: 保留给平台自定义参数（如 Phrase 的 ``workflowStep`` UID、
            Crowdin 的 ``directoryId``）。
    """

    stage: str = ReviewStage.FIRST.value
    platform: str = PlatformType.NONE.value
    project_id: str = ""
    project_name: str = ""
    api_base: str = ""
    api_token: str = ""
    target_language_id: str = ""
    webhook_url: str = ""
    mentioned: List[str] = field(default_factory=list)
    stop_time: str = ""
    #: 单次 ``get_task_status`` 轮询之间的间隔秒数；``0`` 代表使用框架默认
    #: （:const:`DEFAULT_REVIEW_POLL_INTERVAL_SECONDS`）。
    poll_interval_seconds: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PublishTarget:
    """``multi_publish_targets`` 列表中的单条目标。

    对应旧项目中的 ``trunk_tdr_configs`` / ``pub_tdr_configs`` 概念：
    同一份翻译结果合并后，可能需要推送到多个目标路径/分支。

    字段：
        name: 日志/通知中使用的人可读名称。
        source_path: 额外写入翻译结果的路径（相对于 workspace 或绝对）。
        vcs_url_override: 当前目标单独使用的 VCS URL（空则复用 profile / 全局）。
        use_trunk_vcs: True → 推送到 profile 上配置的 "trunk" 分支/URL；
            False → 推送到当前选中的 VCS URL。
        stages: 当前目标适用的流水线阶段（``Stage`` 值）；
            空元组代表“任何阶段都适用”。
        bundles: 自由形式的标签，描述当前目标发布的资源包
            （由上层业务自定义，框架本身不解释）。
        extra: 平台自定义参数。
    """

    name: str = ""
    source_path: str = ""
    vcs_url_override: str = ""
    use_trunk_vcs: bool = False
    stages: Tuple[str, ...] = ()
    bundles: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LanguageProfile:
    """单语种流水线配置 profile。

    profile 是描述“单个目标语种如何被处理”的**唯一实例**：
    运行哪些工作流状态、每一轮审校由哪个平台处理、选择哪种翻译策略，
    以及最终数据发布到哪些目标位置。

    profile 通常从 ``<languages_dir>/<lang>.json`` 经
    :func:`TiMi_HOK_Game_Translator.config.language_loader.load_language_profiles`
    加载——``languages_dir`` 由 :attr:`Config.languages_dir` 指定
    （本仓库惯用 ``conf/languages``，demo 默认 ``configs/languages``），
    也可以以编程方式构造。

    字段：
        id: 语种短标识，在状态文件、日志前缀、流水线查找中均使用。
            惯例采用 BCP-47 或产品自定义 slug（如 ``"vi"`` / ``"vi_exp"``）。
        display_name: 人可读名称，用于日志和通知（如 ``"Vietnamese (Production)"``）。
        source_locale / target_locale: BCP-47 标签；为空时运行时
            继承全局 :class:`Config` 的值。
        source: 可选的 :class:`SourceConfig` 覆盖（各语种的源文件往往位于不同路径）。
        vcs: 可选的 :class:`VcsConfig` 覆盖（各语种可能属于不同分支/工作副本）。
        llm: 可选的 :class:`LLMConfig` 覆盖（部分语种需要不同模型或提示词）。
        reviews: ``ReviewStage.value → ReviewConfig`` 的映射；
            ``workflow`` 里出现的每个审校阶段都应在此有对应项。
        notification: 可选的 :class:`NotificationConfig` 覆盖。
        workflow: 工作流状态名称的有序列表（必须与
            :data:`TiMi_HOK_Game_Translator.workflow.state_registry.STATE_REGISTRY` 一致）。
        multi_publish_targets: 额外发布目标（参见 :class:`PublishTarget`）。
        strategy_config: 供当前语种的
            :class:`~TiMi_HOK_Game_Translator.translation.BaseTranslationStrategy` 使用的
            自由字典（展示名、提示词模板、最大并发、过滤开关…）。
            默认解释参见 :mod:`TiMi_HOK_Game_Translator.translation.generic_strategy`。
        locale_names: 可选的 ``{"cn": "...", "en": "..."}`` 字典，供提示词
            渲染时覆盖内置的中/英文语种名（例如把 ``vi`` 显示为
            "越南文（游戏术语版）"）。未填写时自动回落到
            :data:`TiMi_HOK_Game_Translator.llm.prompts.LOCALE_CN_NAME` /
            :data:`~TiMi_HOK_Game_Translator.llm.prompts.LOCALE_EN_NAME`，再兜底使用
            locale code 字面量。
        extra: 插件用户可以额外携带的任意内容。
    """

    id: str = ""
    display_name: str = ""
    source_locale: str = ""
    target_locale: str = ""
    locale_names: Dict[str, str] = field(default_factory=dict)

    source: SourceConfig = field(default_factory=SourceConfig)
    vcs: VcsConfig = field(default_factory=VcsConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)

    reviews: Dict[str, ReviewConfig] = field(default_factory=dict)
    workflow: Tuple[str, ...] = ()
    multi_publish_targets: Tuple[PublishTarget, ...] = ()
    strategy_config: Dict[str, Any] = field(default_factory=dict)

    #: 导表（``dtxml_merge`` + ``push_vcs``）的目标启动时间，格式 ``"HH:MM"``。
    #: 为空（默认）表示"立即执行"；非空时 ``dtxml_merge`` state 会阻塞等待
    #: 到达该本地时刻再开跑，常用于把合表 + commit 压到夜间低峰窗口。
    merge_start_time: str = ""

    extra: Dict[str, Any] = field(default_factory=dict)

    # -----------------------------------------------------------------
    # 便捷方法
    # -----------------------------------------------------------------
    def review(self, stage: str) -> ReviewConfig:
        """返回 ``stage`` 对应的 :class:`ReviewConfig`。

        当 stage 未配置时返回空壳的 ``ReviewConfig``（``platform="none"``），
        方便工作流状态判定“跳过当前阶段”而无需抛异常。
        """
        return self.reviews.get(stage, ReviewConfig(stage=stage))

    def has_workflow_state(self, state_name: str) -> bool:
        """当 ``state_name`` 属于本 profile 的工作流时返回 True。"""
        return state_name in self.workflow


# ---------------------------------------------------------------------------
# 根配置
# ---------------------------------------------------------------------------
@dataclass
class Config:
    """唯一的根配置对象。

    字段
    ----
    project_code:
        当前游戏/产品的短 slug（取代旧代码中硬编码的 ``AOV_*`` 前缀），
        作为文件名、通知标题、状态文件的命名空间。
    stage:
        当前发版阶段，取值参见 :class:`Stage`。
    source_locale:
        源语言的 BCP-47 标签。
    target_locale:
        本次运行目标语言的 BCP-47 标签。
    """

    project_code: str = "example_game"
    stage: str = Stage.TRUNK_WEEK.value
    source_locale: str = "en"
    target_locale: str = ""

    vcs: VcsConfig = field(default_factory=VcsConfig)
    source: SourceConfig = field(default_factory=SourceConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    platform: PlatformConfig = field(default_factory=PlatformConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    #: 单语种流水线 profile，以 :attr:`LanguageProfile.id` 为键。
    #: 由 :func:`TiMi_HOK_Game_Translator.config.language_loader.load_language_profiles`
    #: 从 :attr:`languages_dir` 扫描填充（未配置时回落到 ``<cwd>/configs/languages``；
    #: 本仓库日常使用 ``conf/languages``，由 ``conf/config.yaml`` 显式指定）。
    languages: Dict[str, LanguageProfile] = field(default_factory=dict)

    #: 供扫描语种 profile JSON 的目录。为空则代表“未加载任何 profile”，
    #: 流水线会回退到顶层的 VCS/source/LLM 区域。
    languages_dir: str = ""

    # 供插件额外使用的自由字段。
    extra: Dict[str, Any] = field(default_factory=dict)

    # -----------------------------------------------------------------
    # 便捷方法
    # -----------------------------------------------------------------
    def workspace_path(self) -> Path:
        """返回当前 workspace 的绝对路径。"""
        if self.workspace.root:
            return Path(self.workspace.root).expanduser().resolve()
        return (Path.cwd() / self.workspace.subdir).resolve()

    def language_profile(self, language_id: str) -> LanguageProfile:
        """按 id 查找 :class:`LanguageProfile`。

        当未找到时，返回一份继承全局 :class:`Config` 子区域的**合成 profile**。
        这使得即使调用方未创建任何语种 profile 目录也能安全调用。
        """
        cached = self.languages.get(language_id)
        if cached is not None:
            return cached
        return LanguageProfile(
            id=language_id,
            display_name=language_id,
            source_locale=self.source_locale,
            target_locale=self.target_locale or language_id,
            source=self.source,
            vcs=self.vcs,
            llm=self.llm,
            notification=self.notification,
        )

    def to_dict(self, *, mask_sensitive: bool = True) -> Dict[str, Any]:
        """返回配置的 dict 视图。

        参数：
            mask_sensitive: 为 ``True`` 时（默认），字段名（大小写不敏感）
                与 :data:`SENSITIVE_FIELD_MARKERS` 完全匹配时会被替换为
                :data:`SENSITIVE_MASK`。
        """
        return _dataclass_to_dict(self, mask_sensitive=mask_sensitive)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _is_sensitive(field_name: str) -> bool:
    """判断字段名是否算敏感字段。

    采用大小写不敏感的**全名匹配**与 :data:`SENSITIVE_FIELD_MARKERS`，
    这能避免 ``max_tokens`` 被误判（包含 ``token``），
    也能避免 ``api_key`` 被遗漏（按词拆分会未命中）。
    """
    normalized = field_name.replace("-", "_").lower()
    return normalized in {marker.lower() for marker in SENSITIVE_FIELD_MARKERS}


def _mask_if_sensitive(field_name: str, value: Any) -> Any:
    """若字段敏感则返回脱敏后的占位，否则原样返回。"""
    if value in (None, "", [], {}):
        return value
    if _is_sensitive(field_name):
        return SENSITIVE_MASK
    return value


def _dataclass_to_dict(obj: Any, *, mask_sensitive: bool) -> Any:
    """递归地将 dataclass 树转为普通 dict。

    不使用 :func:`dataclasses.asdict` 是因为需要在字段名级别
    做敏感字段脱敏，asdict 未提供这个能力。
    """
    if is_dataclass(obj):
        out: Dict[str, Any] = {}
        for f in fields(obj):
            raw = getattr(obj, f.name)
            processed = _dataclass_to_dict(raw, mask_sensitive=mask_sensitive)
            if mask_sensitive and not is_dataclass(raw):
                processed = _mask_if_sensitive(f.name, processed)
            out[f.name] = processed
        return out
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v, mask_sensitive=mask_sensitive) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_dataclass_to_dict(v, mask_sensitive=mask_sensitive) for v in obj]
    return obj


__all__ = [
    "Config",
    "LLMConfig",
    "LanguageProfile",
    "LoggingConfig",
    "NotificationConfig",
    "PlatformConfig",
    "PublishTarget",
    "ReviewConfig",
    "SourceConfig",
    "VcsConfig",
    "WorkspaceConfig",
    # helpers (主要供测试导出)
    "_is_sensitive",
]
