"""根据 :class:`VcsConfig` 创建具体 :class:`VcsClient` 的工厂。"""

from __future__ import annotations

from typing import Any, Dict, Type

from ..commons import VcsType
from ..config.schema import VcsConfig
from .base import VcsClient, VcsCredentials
from .git_client import GitClient
from .mock_client import MockClient
from .perforce_client import PerforceClient
from .svn_client import SvnClient

_REGISTRY: Dict[str, Type[VcsClient]] = {
    VcsType.SVN.value: SvnClient,
    VcsType.GIT.value: GitClient,
    VcsType.PERFORCE.value: PerforceClient,
    VcsType.LOCAL.value: MockClient,
}

#: 老配置向后兼容：早期版本把"无 VCS、直接读写本地目录"的后端命名为
#: ``mock``；重命名为 ``local`` 之后，这里把老值翻译回新值，保证既有
#: ``config.yaml`` / ``languages/*.yaml`` 不升级就能继续加载。
_VCS_TYPE_ALIASES: Dict[str, str] = {
    "mock": VcsType.LOCAL.value,
}


def register_vcs_client(name: str, client_cls: Type[VcsClient]) -> None:
    """以 ``name`` 为名注册自定义 :class:`VcsClient` 实现。

    下游插件如需新增后端，无需 fork 本框架。
    """
    _REGISTRY[name.lower()] = client_cls


def create_vcs_client(vcs_config: VcsConfig, *, workspace: str = "") -> VcsClient:
    """根据 ``vcs_config`` 返回已初始化好的 :class:`VcsClient`。

    参数：
        vcs_config: 根配置下的 :class:`VcsConfig` 区域。
        workspace: 已解析的 workspace 目录；当 ``vcs.local_path`` 为相对路径时以其为基准。

    异常：
        VcsCliMissingError: PATH 上缺失需要的二进制。
        ValueError: ``vcs_config.type`` 未注册。
    """
    key = (vcs_config.type or "").lower()
    key = _VCS_TYPE_ALIASES.get(key, key)  # 兼容老的 "mock" → "local"
    if key not in _REGISTRY:
        raise ValueError(
            f"Unknown vcs.type '{vcs_config.type}'. "
            f"Registered backends: {sorted(_REGISTRY)}"
        )
    cls = _REGISTRY[key]
    cls.ensure_cli_available()

    local_path = _resolve_local_path(vcs_config.local_path, workspace)
    credentials = VcsCredentials(
        username=vcs_config.username, password=vcs_config.password,
    )
    extra: Dict[str, Any] = dict(vcs_config.extra or {})
    return cls(
        url=vcs_config.url,
        local_path=local_path,
        credentials=credentials,
        cli_timeout_seconds=vcs_config.cli_timeout_seconds,
        default_commit_message=vcs_config.default_commit_message,
        **extra,
    )


def _resolve_local_path(local_path: str, workspace: str) -> str:
    """返回绝对的工作副本路径。

    * ``local_path`` 为绝对路径时直接返回；
    * ``local_path`` 为相对路径且提供了 ``workspace`` 时，拼接两者；
    * ``local_path`` 为空时回退为 ``{workspace}/vcs``；
    * ``local_path`` 中出现 ``{workspace}`` 占位符时，先展开再按上述规则处理
      （避免模板里写了 ``{workspace}/svn/test_translation`` 导致被当成文字路径分量）。
    """
    import os

    if local_path and "{workspace}" in local_path:
        local_path = local_path.replace("{workspace}", workspace or "")
        # 展开后可能变成绝对路径（workspace 本身是绝对路径），走下方分支即可。

    if local_path:
        if os.path.isabs(local_path):
            return local_path
        if workspace:
            return os.path.join(workspace, local_path)
        return os.path.abspath(local_path)
    if workspace:
        return os.path.join(workspace, "vcs")
    return os.path.abspath("vcs")


__all__ = ["create_vcs_client", "register_vcs_client"]
