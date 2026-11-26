"""平台适配器的工厂与注册表。

提供两个入口：

* :func:`create_platform`——从**全局** :class:`~TiMi_HOK_Game_Translator.config.PlatformConfig`
  构造平台，适合整个流水线使用单一平台的情形。
* :func:`build_review_tool`——为
  :class:`~TiMi_HOK_Game_Translator.config.LanguageProfile` 上的**某个审校阶段**构造平台；
  ``FirstReviewState`` / ``SecondReviewState`` 之类工作流状态应调用它。

两个函数共享同一份由 :func:`register_platform` 填充的注册表。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Type

from ..commons import PlatformError, PlatformType, ReviewStage
from ..config.schema import LanguageProfile, PlatformConfig, ReviewConfig
from .base import TranslationPlatform
from .noop import NoopPlatform

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, Type[TranslationPlatform]] = {
    PlatformType.NONE.value: NoopPlatform,
}


def register_platform(name: str, platform_cls: Type[TranslationPlatform]) -> None:
    """以 ``name`` 为名注册自定义 :class:`TranslationPlatform` 实现。

    名称大小写不敏感（``"Phrase"`` 与 ``"phrase"`` 合并为同一个）。
    允许重复注册，插件需要掩盖内置实现时很常见。
    """
    _REGISTRY[name.lower()] = platform_cls


def registered_platforms() -> list:
    """返回当前已注册的平台名称列表（排序后）。"""
    return sorted(_REGISTRY)


def create_platform(platform_config: PlatformConfig) -> TranslationPlatform:
    """根据 ``platform_config`` 构造 :class:`TranslationPlatform`。

    异常：
        PlatformError: ``type`` 未注册。
    """
    key = (platform_config.type or "").lower()
    if key not in _REGISTRY:
        raise PlatformError(
            f"Unknown platform.type '{platform_config.type}'. "
            f"Registered platforms: {registered_platforms()}. "
            "Install the matching plugin (e.g. 'TiMi_HOK_Game_Translator[phrase]') "
            "or set platform.type to 'none' to disable the integration."
        )
    cls = _REGISTRY[key]
    return cls(
        api_base=platform_config.api_base,
        api_token=platform_config.api_token,
        project_id=platform_config.project_id,
        extra=dict(platform_config.extra or {}),
    )


def build_review_tool(
    profile: LanguageProfile,
    review_stage: str = ReviewStage.FIRST.value,
    *,
    fallback: Optional[str] = None,
    global_platform: Optional[PlatformConfig] = None,
) -> TranslationPlatform:
    """为 ``profile`` 在 ``review_stage`` 上选择平台。

    解析顺序：

    1. ``profile.reviews[review_stage]`` ——阶段级最具体的配置；
    2. 当其 ``platform`` 为空或 ``"none"`` 时，尝试 ``fallback`` 名称；
    3. 仍为空时回退到 ``global_platform``（顶层 :class:`PlatformConfig`）；
    4. 均无时返回 :class:`NoopPlatform`，便于工作流状态判定“无需处理”而不报错。

    参数：
        profile: 当前运行使用的语种 profile。
        review_stage: :class:`~TiMi_HOK_Game_Translator.commons.ReviewStage` 之一（
            ``"light"`` / ``"first"`` / ``"second"``）。
        fallback: 当阶段平台为 ``"none"`` 时的回退平台名，可选。
        global_platform: :attr:`Config.platform`，仅在 profile 级无配置时使用。

    返回：
        已初始化的 :class:`TranslationPlatform`。

    异常：
        PlatformError: 解析出的平台名未注册。
    """
    review_cfg = profile.review(review_stage) if profile else ReviewConfig(stage=review_stage)
    chosen: Optional[str] = None
    source_of_config: Optional[ReviewConfig] = None

    if review_cfg.platform and review_cfg.platform != PlatformType.NONE.value:
        chosen = review_cfg.platform
        source_of_config = review_cfg
    elif fallback:
        chosen = fallback
        source_of_config = review_cfg
    elif global_platform and global_platform.type and global_platform.type != PlatformType.NONE.value:
        chosen = global_platform.type

    if chosen is None:
        chosen = PlatformType.NONE.value

    key = chosen.lower()
    if key not in _REGISTRY:
        raise PlatformError(
            f"Unknown review platform '{chosen}' for stage {review_stage!r} "
            f"on language {profile.id!r}. Registered: {registered_platforms()}."
        )

    cls = _REGISTRY[key]

    # 优先使用阶段级凭据；为空时回退到全局配置。
    api_base = ""
    api_token = ""
    project_id = ""
    extra: Dict[str, Any] = {}

    if source_of_config is not None:
        api_base = source_of_config.api_base
        api_token = source_of_config.api_token
        project_id = source_of_config.project_id
        extra = dict(source_of_config.extra or {})
        # 透传 ReviewConfig.target_language_id —— 平台适配器（如 PhrasePlatform
        # 需要在 Memsource 头的 ``targetLangs`` 字段里带目标语种）通过
        # ``extra["target_language_id"]`` 读到它。其他未读此键的平台不受影响。
        if source_of_config.target_language_id:
            extra.setdefault("target_language_id", source_of_config.target_language_id)

    if global_platform is not None:
        # ⚠️ 跨平台类型保护（针对**强绑定**字段）：
        # ``api_base`` / ``api_token`` / ``project_id`` 强绑定具体平台 —— 若
        # 全局 ``platform.type`` 与当前阶段选中平台不一致，就不能回退，否则
        # 会出现"Phrase 用了 Crowdin 的 api_base"这种污染（请求打到对方
        # nginx，直接 ``404 {"error":{"message":"Not Found","code":404}}``）。
        if (global_platform.type or "").lower() == key:
            api_base = api_base or global_platform.api_base
            api_token = api_token or global_platform.api_token
            project_id = project_id or global_platform.project_id
        else:
            logger.debug(
                "[REVIEW_TOOL_FACTORY] skipping global api_base/api_token/"
                "project_id fallback: global.type=%r != stage.platform=%r "
                "(would cross-contaminate endpoint).",
                global_platform.type, chosen,
            )
        # ``extra`` 字典按原方式 setdefault 透传，不做类型隔离 —— 因为 extra
        # 里的键都是**平台特定**的（Phrase 读 ``subject_token``/``region``；
        # Crowdin 读 ``base_url``/``organization`` 等），各平台只读自己认识
        # 的键，互不干扰；而且用户经常把令牌通过环境变量注入**全局**
        # ``platform.extra`` 块（如 ``GAME_TRANS_TOOLCHAIN__PLATFORM__SUBJECT_TOKEN``
        # → ``platform.extra.subject_token``），不透传反而破坏这个约定。
        for k, v in (global_platform.extra or {}).items():
            extra.setdefault(k, v)

    instance = cls(
        api_base=api_base,
        api_token=api_token,
        project_id=project_id,
        extra=extra,
    )
    if not instance.supports(review_stage):
        raise PlatformError(
            f"Platform {chosen!r} does not support review_stage={review_stage!r}. "
            f"Supported stages: {instance.supports_stages}."
        )

    logger.info(
        "[REVIEW_TOOL_FACTORY] language=%s stage=%s platform=%s project=%s",
        profile.id, review_stage, chosen, project_id,
    )
    return instance


__all__ = [
    "build_review_tool",
    "create_platform",
    "register_platform",
    "registered_platforms",
]
