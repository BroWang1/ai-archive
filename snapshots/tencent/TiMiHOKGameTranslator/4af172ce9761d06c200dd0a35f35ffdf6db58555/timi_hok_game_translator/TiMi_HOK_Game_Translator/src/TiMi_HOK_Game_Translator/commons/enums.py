"""框架内使用的枚举定义。

集中在一个模块，可以让状态机流转、VCS 选型、源文件格式选型、
CLI 参数取值保持一致。所有枚举都继承 ``str``，方便 YAML/JSON 序列化以及
argparse ``choices`` 使用。
"""

from __future__ import annotations

from enum import Enum


class VcsType(str, Enum):
    """支持的版本控制后端。

    :cvar LOCAL: **本地文件系统后端** —— 不走任何 VCS，直接在 ``local_path``
        目录读写翻译数据；用于本地开发 / demo / 单测。老字段值 ``"mock"``
        仍被加载器识别为同一枚举（见 :mod:`TiMi_HOK_Game_Translator.vcs.factory`）。
    """

    SVN = "svn"
    GIT = "git"
    PERFORCE = "perforce"
    LOCAL = "local"
    #: 向后兼容别名；老配置里的 ``vcs.type: mock`` 等价于 ``local``。
    MOCK = "local"

    @classmethod
    def values(cls) -> list[str]:
        """返回全部枚举的字符串值，便于用作 ``argparse(choices=...)``。"""
        return [member.value for member in cls]


class SourceFormat(str, Enum):
    """支持的本地化源文件格式。"""

    JSON = "json"
    YAML = "yaml"
    XML = "xml"
    CSV = "csv"
    DTXML = "dtxml"
    XLIFF = "xliff"

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]


class LLMProvider(str, Enum):
    """支持的 LLM 后端。

    :cvar ECHO: **回显式占位 provider** —— 把输入文本按 ``[target_locale] 原文``
        格式回显出来，不联网、确定性输出，用于本地 demo / 单测 / 配置试跑。
        老字段值 ``"mock"`` 仍被加载器识别为同一枚举（见
        :mod:`TiMi_HOK_Game_Translator.llm.factory`）。
    """

    ECHO = "echo"
    #: 向后兼容别名；老配置里的 ``llm.provider: mock`` 等价于 ``echo``。
    MOCK = "echo"
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    HUNYUAN_TRANSLATION = "hunyuan_translation"
    VENUS = "venus"
    CUSTOM = "custom"

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]


class PlatformType(str, Enum):
    """支持的审校平台适配器。"""

    NONE = "none"
    CROWDIN = "crowdin"
    PHRASE = "phrase"
    CUSTOM = "custom"

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]


class ReviewStage(str, Enum):
    """标识一个 :class:`TranslationPlatform` 实例服务于哪一轮审校。

    同一个 :class:`~TiMi_HOK_Game_Translator.config.LanguageProfile` 允许为不同轮次配置
    不同平台（例如一审用 Phrase、二审用 Crowdin）。工作流状态会依据本枚举
    从 profile 中挑选对应的 :class:`ReviewConfig`。
    """

    LIGHT = "light"
    FIRST = "first"
    SECOND = "second"

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]


class NotifierType(str, Enum):
    """支持的通知渠道。"""

    NONE = "none"
    WECOM = "wecom"
    SLACK = "slack"
    EMAIL = "email"
    CONSOLE = "console"

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]


class Stage(str, Enum):
    """整体流水线阶段 / 发版周期分类。"""

    EXP_WEEK = "exp_week"
    TRUNK_WEEK = "trunk_week"
    PUB_WEEK = "pub_week"
    HOT_WEEK = "hot_week"

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]


class ReviewRound(str, Enum):
    """当前工作流处于哪一轮审校。"""

    FIRST = "first"
    SECOND = "second"


class WorkflowState(str, Enum):
    """框架内建工作流状态的标准名称。

    :class:`~TiMi_HOK_Game_Translator.config.LanguageProfile.workflow` 字段以这些名称
    组成一个子集（并指定顺序）来编排该语种的流水线。第三方状态可通过
    :func:`TiMi_HOK_Game_Translator.workflow.state_registry.register_state` 用自定义名称注册。
    """

    # 生命周期首尾
    PENDING = "pending"
    FINISHED = "finished"
    FAILED = "failed"

    # VCS 相关
    PULL_VCS = "pull_vcs"
    PUSH_VCS = "push_vcs"
    PUSH_MULTI_VCS = "push_multi_vcs"

    # 上一轮遗留数据处理
    LAST_FIRST_REVIEW = "last_first_review"
    LAST_SECOND_REVIEW = "last_second_review"
    LAST_MERGE_DATA = "last_merge_data"

    # 翻译与翻译记忆
    TRANSLATE = "translate"
    UPDATE_TM = "update_tm"
    UPDATE_GRN_TM = "update_grn_tm"
    INCREMENT_MATCH = "increment_match"

    # 审校
    LIGHT_REVIEW = "light_review"
    FIRST_REVIEW = "first_review"
    SECOND_REVIEW = "second_review"

    # 数据装配
    MERGE_DATA = "merge_data"
    VALIDATE_DATA = "validate_data"

    # ------------------------------------------------------------------
    # 向后兼容别名。
    #
    # 框架早期使用 5 状态流水线（INGEST → TRANSLATE → REVIEW → MERGE →
    # PUBLISH）。上方 17 状态模型已是新标准，保留这些别名，让老状态类和
    # 单元测试在渐进迁移期间继续可用。
    #
    # ``str`` Enum 的语义使别名会解析到与其规范名相同的成员（别名不占
    # 独立槽位），因此 ``WorkflowState.INGEST is WorkflowState.PULL_VCS`` 恒真。
    # ------------------------------------------------------------------
    INGEST = "pull_vcs"
    REVIEW = "first_review"
    MERGE = "merge_data"
    PUBLISH = "push_vcs"

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]


class LogLevel(str, Enum):
    """标准日志级别，与 ``logging`` 模块名称一致。"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]
