"""TiMi_HOK_Game_Translator.platforms 子包。

对外 API::

    from TiMi_HOK_Game_Translator.platforms import (
        TranslationPlatform, TaskInfo, TaskStatus, UploadResult, SplitResult,
        NoopPlatform, PhrasePlatform, CrowdinPlatform,
        create_platform, build_review_tool,
        register_platform, registered_platforms,
    )
"""

from .base import (
    SplitResult,
    TaskInfo,
    TaskStatus,
    TranslationPlatform,
    UploadResult,
)

# 导入以下模块的副作用是把对应平台适配器注册到工厂。
from .crowdin_platform import CrowdinPlatform
from .factory import (
    build_review_tool,
    create_platform,
    register_platform,
    registered_platforms,
)
from .noop import NoopPlatform
from .phrase_platform import PhrasePlatform

__all__ = [
    "CrowdinPlatform",
    "NoopPlatform",
    "PhrasePlatform",
    "SplitResult",
    "TaskInfo",
    "TaskStatus",
    "TranslationPlatform",
    "UploadResult",
    "build_review_tool",
    "create_platform",
    "register_platform",
    "registered_platforms",
]
