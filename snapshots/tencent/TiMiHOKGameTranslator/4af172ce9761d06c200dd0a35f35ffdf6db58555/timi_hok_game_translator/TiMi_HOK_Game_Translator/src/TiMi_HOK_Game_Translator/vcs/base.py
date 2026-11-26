"""版本控制抽象层。

``TiMi_HOK_Game_Translator`` 中所有 VCS 操作都经由 :class:`VcsClient` 接口。
具体后端（:class:`~.svn_client.SvnClient` 、 :class:`~.git_client.GitClient` 、
:class:`~.perforce_client.PerforceClient` 、 :class:`~.mock_client.MockClient`）
实现本接口，由 :func:`~.factory.create_vcs_client` 在运行时选择。

设计目标：

* 方法名与后端无关——不暴露 svn / git / p4 的术语；
* 重试与错误处理位于客户端内部，而不侵入工作流；
* 外部 CLI（``svn`` / ``git`` / ``p4``）统一通过
  :meth:`VcsClient._run` 子进程调用，保证单测 mock 只需处理一个接口。
"""

from __future__ import annotations

import abc
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from ..commons import (
    DEFAULT_VCS_CLI_TIMEOUT_SECONDS,
    DEFAULT_VCS_COMMIT_MESSAGE,
    VcsCliMissingError,
    VcsCommandError,
)


# ---------------------------------------------------------------------------
# 数据对象
# ---------------------------------------------------------------------------
@dataclass
class VcsCredentials:
    """VCS 后端的鉴权信息。

    字段均为可选，因为部分后端（如启用 SSO 的 Perforce、走 SSH 的 Git、
    还有 mock 后端）不需要显式凭据。
    """

    username: str = ""
    password: str = ""


@dataclass
class VcsCommandResult:
    """单次 CLI 调用的捕获结果。"""

    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class VcsStatus:
    """操作后工作副本的粗粒度状态。

    后端自定义细节（如冲突文件列表）可放入 :attr:`extra`，不影响接口契约。
    """

    revision: str = ""
    modified_paths: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------
class VcsClient(abc.ABC):
    """所有 VCS 后端需实现的接口。

    子类需提供类属性 ``cli_name: str``（``"svn"`` / ``"git"`` / ``"p4"``），
    工厂会在首次命令之前预检 PATH。
    """

    #: PATH 上必须存在的可执行文件；``None`` 时跳过检查（适用于 mock
    #: 后端和纯 Python 实现）。
    cli_name: Optional[str] = None

    def __init__(
        self,
        url: str,
        local_path: str,
        credentials: Optional[VcsCredentials] = None,
        *,
        cli_timeout_seconds: int = DEFAULT_VCS_CLI_TIMEOUT_SECONDS,
        default_commit_message: str = DEFAULT_VCS_COMMIT_MESSAGE,
    ) -> None:
        self.url = url
        self.local_path = str(Path(local_path).expanduser()) if local_path else ""
        self.credentials = credentials or VcsCredentials()
        self.cli_timeout_seconds = cli_timeout_seconds
        self.default_commit_message = default_commit_message

    # ------------------------------------------------------------------
    # 类级别辅助方法
    # ------------------------------------------------------------------
    @classmethod
    def ensure_cli_available(cls) -> None:
        """当所需 CLI 不存在时抛出 :class:`VcsCliMissingError`。

        子类可覆写，以支持多个开发包或提供更友好的提示。
        """
        if cls.cli_name is None:
            return
        if shutil.which(cls.cli_name) is None:
            raise VcsCliMissingError(
                f"The required VCS CLI '{cls.cli_name}' was not found on PATH. "
                f"Install it (or adjust your PATH) and try again."
            )

    # ------------------------------------------------------------------
    # 抽象 API
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def checkout(self) -> VcsStatus:
        """从 ``self.url`` 拉取一份全新工作副本到 ``self.local_path``。"""

    @abc.abstractmethod
    def update(self, revision: Optional[str] = None) -> VcsStatus:
        """将工作副本同步到 ``revision``（``None`` 时同步到最新）。"""

    @abc.abstractmethod
    def add(self, paths: Sequence[str]) -> None:
        """将指定路径添加到下一次提交的暂存区。"""

    @abc.abstractmethod
    def commit(self, paths: Sequence[str], message: Optional[str] = None) -> VcsStatus:
        """提交已暂存的路径。

        支持原子 add+commit 的后端可一步完成；默认行为为：
        暂存 → 提交 → 返回状态。
        """

    @abc.abstractmethod
    def revert(self, paths: Sequence[str]) -> None:
        """丢弃指定路径的本地修改。"""

    @abc.abstractmethod
    def status(self, paths: Optional[Sequence[str]] = None) -> VcsStatus:
        """返回当前工作副本状态。"""

    @abc.abstractmethod
    def cleanup(self) -> None:
        """从中断的操作中恢复工作副本（锁、未完成事务等）。"""

    @abc.abstractmethod
    def get_revision(self) -> str:
        """返回当前 revision / commit / changelist 的字符串表示。"""

    # ------------------------------------------------------------------
    # 可选钩子（有默认实现，子类按需覆写）
    # ------------------------------------------------------------------
    def prepare_for_write(self, paths: Sequence[str]) -> None:
        """在**对外部写**磁盘之前通知 VCS 后端 "即将修改这些路径"。

        * SVN / Git / mock：无需操作（工作副本文件天然可写）→ 默认 no-op；
        * Perforce：必须先 ``p4 edit``，否则本地文件是只读的，
          Python 直接 ``open(..., "w")`` 会抛 ``PermissionError``。

        调用方（``MergeDataState`` / ``PushVcsState``）在 ``source.dump()``
        或 ``merge_incremental_into_full()`` **之前**调用本方法；对后端
        而言这是"幂等 + 容错"的——文件不存在、CLI 调用失败都**不应**
        中断主流程（真正的 commit 失败由 ``commit()`` 自己负责报告）。
        """
        return None

    # ------------------------------------------------------------------
    # 共享基础设施
    # ------------------------------------------------------------------
    def _run(
        self,
        cmd: Sequence[str],
        *,
        cwd: Optional[str] = None,
        check: bool = True,
    ) -> VcsCommandResult:
        """执行 ``cmd`` 并返回 :class:`VcsCommandResult`。

        参数：
            cmd: 完整 argv，首元素必须为 CLI 可执行文件。
            cwd: 工作目录；默认为 ``self.local_path``。
            check: 为 ``True`` 时（默认），非零退出码会在脱敏并
                记录后抛出 :class:`VcsCommandError`。

        备注：
            子类不应重写本方法，应在自己的方法里拼接命令后委托本方法，
            以保证单测只需 mock 一处。
        """
        proc = subprocess.run(  # noqa: S603 — 命令仅内部拼接
            list(cmd),
            cwd=cwd or self.local_path or None,
            capture_output=True,
            text=True,
            timeout=self.cli_timeout_seconds,
        )
        result = VcsCommandResult(
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )
        if check and not result.ok:
            masked_cmd = self._mask_cmd(cmd)
            raise VcsCommandError(
                f"Command failed with code {result.returncode}: {masked_cmd}\n"
                f"stderr: {result.stderr.strip()}"
            )
        return result

    def _mask_cmd(self, cmd: Iterable[str]) -> str:
        """将命令串化输出，并对密码参数进行脱敏。"""
        masked: List[str] = []
        skip_next = False
        for token in cmd:
            if skip_next:
                masked.append("***")
                skip_next = False
                continue
            if token in {"--password", "-p"}:
                skip_next = True
            masked.append(token)
        return " ".join(masked)


__all__ = [
    "VcsClient",
    "VcsCommandResult",
    "VcsCredentials",
    "VcsStatus",
]
