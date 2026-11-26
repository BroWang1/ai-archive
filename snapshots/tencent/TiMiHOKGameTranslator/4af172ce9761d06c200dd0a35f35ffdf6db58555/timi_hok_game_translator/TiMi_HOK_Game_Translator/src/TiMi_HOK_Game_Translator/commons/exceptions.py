"""项目级异常层次。

用一组小而语义明确的异常，方便调用方（以及 CI）区分用户错误（配置错）、
基础设施错误（VCS CLI 缺失、上游 500）和程序缺陷（bug）。
"""

from __future__ import annotations


class OpenLocalizerError(Exception):
    """:mod:`TiMi_HOK_Game_Translator` 所有异常的基类。"""


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
class ConfigError(OpenLocalizerError):
    """配置类问题的基类。"""


class ConfigFileError(ConfigError):
    """配置文件缺失、格式错误或不可读。"""


class MissingRequiredConfigError(ConfigError):
    """所有配置层合并后，某个必填字段仍为空。

    错误信息应包含出错字段名，以及可以提供该字段的环境变量。
    """


# ---------------------------------------------------------------------------
# VCS
# ---------------------------------------------------------------------------
class VcsError(OpenLocalizerError):
    """版本控制类失败的基类。"""


class VcsCliMissingError(VcsError):
    """所需的 VCS CLI（``svn`` / ``git`` / ``p4``）未安装或未在 PATH 中。"""


class VcsCommandError(VcsError):
    """VCS 命令在完成所有重试后仍以非零状态退出。"""


# ---------------------------------------------------------------------------
# 源文件
# ---------------------------------------------------------------------------
class SourceError(OpenLocalizerError):
    """本地化源文件解析/写入失败的基类。"""


class UnknownSourceFormatError(SourceError):
    """请求的 ``source.format`` 没有已注册的实现。"""


# ---------------------------------------------------------------------------
# LLM 与平台
# ---------------------------------------------------------------------------
class LLMError(OpenLocalizerError):
    """LLM 提供商相关失败的基类。"""


class LLMProviderMissingError(LLMError):
    """请求的 LLM 提供商未知，或其可选依赖未安装。"""


class PlatformError(OpenLocalizerError):
    """翻译平台适配器失败的基类。"""
