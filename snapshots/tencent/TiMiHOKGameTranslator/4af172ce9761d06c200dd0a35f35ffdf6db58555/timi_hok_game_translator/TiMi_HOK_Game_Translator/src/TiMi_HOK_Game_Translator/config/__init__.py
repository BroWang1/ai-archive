"""配置包。

对外 API::

    from TiMi_HOK_Game_Translator.config import Config, load, validate, require_valid
"""

from .language_loader import (
    attach_language_profiles,
    load_language_profile,
    load_language_profiles,
)
from .loader import build_argparser, load, require_valid, validate
from .schema import (
    Config,
    LanguageProfile,
    LLMConfig,
    LoggingConfig,
    NotificationConfig,
    PlatformConfig,
    PublishTarget,
    ReviewConfig,
    SourceConfig,
    VcsConfig,
    WorkspaceConfig,
)

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
    "attach_language_profiles",
    "build_argparser",
    "load",
    "load_language_profile",
    "load_language_profiles",
    "require_valid",
    "validate",
]
