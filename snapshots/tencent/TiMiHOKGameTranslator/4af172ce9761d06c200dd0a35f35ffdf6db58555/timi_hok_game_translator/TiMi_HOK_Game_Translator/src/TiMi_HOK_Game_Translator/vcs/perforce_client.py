"""基于 ``p4`` CLI 的 Perforce（Helix Core）后端。

Perforce 以 workspace 为中心，与 SVN/Git 思维不同；本适配器将 :class:`VcsClient`
操作映射到最接近的 Perforce 命令：

* :meth:`checkout`——``p4 sync`` 到已配置的 client workspace。
* :meth:`update`——``p4 sync``。
* :meth:`add`——``p4 add`` / ``p4 edit``（已纳管文件需 ``edit`` 才能编辑，
  新文件需 ``add``）。
* :meth:`commit`——``p4 submit`` 提交当前 changelist。
* :meth:`revert`——``p4 revert``。
* :meth:`cleanup`——空实现，Perforce 无工作副本锁。

若使用 SSO / MFA，请在进入前完成鉴权；本适配器不会自动执行 ``p4 login``。
"""

from __future__ import annotations

import time
from typing import List, Optional, Sequence

from ..commons import DEFAULT_HTTP_RETRIES, DEFAULT_HTTP_RETRY_INTERVAL_SECONDS
from .base import VcsClient, VcsCommandResult, VcsCredentials, VcsStatus


class PerforceClient(VcsClient):
    """:class:`VcsClient` 的 Perforce 实现。"""

    cli_name = "p4"

    def __init__(
        self,
        url: str,
        local_path: str,
        credentials: Optional[VcsCredentials] = None,
        *,
        p4port: str = "",
        p4client: str = "",
        retries: int = DEFAULT_HTTP_RETRIES,
        retry_interval_seconds: int = DEFAULT_HTTP_RETRY_INTERVAL_SECONDS,
        **kwargs: object,
    ) -> None:
        super().__init__(url=url, local_path=local_path, credentials=credentials, **kwargs)  # type: ignore[arg-type]
        # ``url`` 在 Perforce 下被视为 depot spec（如 ``//depot/loc/...``）。
        self.depot_spec = url or "//..."
        self.p4port = p4port
        self.p4client = p4client
        self.retries = max(1, int(retries))
        self.retry_interval_seconds = max(0, int(retry_interval_seconds))

    # ------------------------------------------------------------------
    # VcsClient 接口实现
    # ------------------------------------------------------------------
    def checkout(self) -> VcsStatus:
        self._retry(["p4", *self._global_args(), "sync", self.depot_spec])
        return VcsStatus(revision=self.get_revision())

    def update(self, revision: Optional[str] = None) -> VcsStatus:
        # P4 的 revision 表达法与 SVN/Git 不同：
        #   * ``@HEAD`` 不合法（HEAD 是 SVN/Git 语义）；
        #   * 不加任何后缀即同步到最新；
        #   * 若需要 pin 到具体 changelist，用 ``@12345``。
        # 为了与通用上游（``PullVcsState``）兼容，这里把 "HEAD"（或空）
        # 都归一为"不加后缀"。
        spec = self._build_sync_spec(revision)
        self._retry(["p4", *self._global_args(), "sync", spec])
        return VcsStatus(revision=self.get_revision())

    def _build_sync_spec(self, revision: Optional[str]) -> str:
        """把通用 ``revision`` 翻译成 P4 ``depot_spec`` 后缀。

        * ``None`` / ``""`` / ``"HEAD"`` / ``"head"``：同步到最新 → 不加后缀；
        * 纯数字（例如 ``"12345"``）：当作 changelist → ``@12345``；
        * 其它字符串：原样作为 P4 revision 修饰符（``@label``、``@date``、
          ``@client``、``#have`` 等）直接拼接——若用户已自带 ``@`` / ``#``
          前缀则不再追加。
        """
        if not revision:
            return self.depot_spec
        rev = str(revision).strip()
        if not rev or rev.upper() == "HEAD":
            return self.depot_spec
        if rev.startswith("@") or rev.startswith("#"):
            return f"{self.depot_spec}{rev}"
        return f"{self.depot_spec}@{rev}"

    def add(self, paths: Sequence[str]) -> None:
        if not paths:
            return
        # 'p4 add' 处理新文件；'p4 edit' 打开已有文件。先试 edit（未打开时开销很小），
        # 再试 add；两命令均会忽略已打开的文件。
        self._run(["p4", *self._global_args(), "edit", *paths], check=False)
        self._run(["p4", *self._global_args(), "add", *paths], check=False)

    def commit(self, paths: Sequence[str], message: Optional[str] = None) -> VcsStatus:
        """提交当前 workspace 的默认 changelist。

        ``paths`` 的作用是：**让它们先被 ``p4 edit`` / ``p4 add`` 加入默认
        changelist**（由 :meth:`add` 完成）。``p4 submit`` **本身不接受
        多文件参数**（Usage: ``submit [-d description] [file]`` 的 ``[file]``
        是单数，且要求是 depot path / wildcard，不是绝对路径），因此
        这里不把 ``paths`` 追加到 submit 命令后面——否则会报
        ``Missing/wrong number of arguments``。

        **副作用提醒**：``p4 submit -d msg`` 会提交 workspace **默认 changelist
        里的所有 open 文件**。如果用户在本流程之外手动 ``p4 edit`` 了别的
        文件、且未关进其它 changelist，会被一并提交。TiMi_HOK_Game_Translator 的
        标准运行场景下，workspace 由本工具独占，不会出现此情况。
        """
        if paths:
            self.add(paths)
        effective_msg = message or self.default_commit_message
        cmd = ["p4", *self._global_args(), "submit", "-d", effective_msg]
        self._retry(cmd)
        return VcsStatus(revision=self.get_revision(), modified_paths=list(paths))

    def revert(self, paths: Sequence[str]) -> None:
        if not paths:
            return
        self._run(["p4", *self._global_args(), "revert", *paths], check=True)

    def prepare_for_write(self, paths: Sequence[str]) -> None:
        """P4 工作副本文件默认是只读的；写入前必须 ``p4 edit``。

        * 对**已纳管**的文件：``p4 edit`` 会取消本地只读属性并把文件加入
          默认 changelist；
        * 对**不存在于 depot** 的新文件：``p4 edit`` 会报 "file(s) not on
          client"——这是预期；真正的 ``p4 add`` 由后续 ``commit() → add()``
          自动处理。
        * 不存在于磁盘的路径（例如本轮尚未落地的 full 表）跳过。
        * 任何 CLI 失败都**不中断主流程**——真正的提交由 ``commit()`` 兜底，
          本方法只是"事前最佳努力去只读"。
        """
        from pathlib import Path as _Path  # noqa: WPS433 — 局部，避免顶层多一处 import

        existing = [p for p in paths if p and _Path(p).exists()]
        if not existing:
            return
        self._run(
            ["p4", *self._global_args(), "edit", *existing],
            check=False,
        )

    def status(self, paths: Optional[Sequence[str]] = None) -> VcsStatus:
        result = self._run(["p4", *self._global_args(), "opened", *(paths or ())], check=False)
        modified: List[str] = []
        for line in result.stdout.splitlines():
            if line:
                modified.append(line.strip())
        return VcsStatus(revision=self.get_revision(), modified_paths=modified)

    def cleanup(self) -> None:
        # Perforce 无工作副本锁；保留方法仅为了接口完整。
        return None

    def get_revision(self) -> str:
        result = self._run(
            ["p4", *self._global_args(), "changes", "-m", "1", f"{self.depot_spec}#have"],
            check=False,
        )
        # 输出格式："Change 12345 on 2024/01/01 by user@client 'msg'"
        parts = result.stdout.split()
        if len(parts) >= 2 and parts[0] == "Change":
            return parts[1]
        return result.stdout.strip()

    # ------------------------------------------------------------------
    def _global_args(self) -> List[str]:
        args: List[str] = []
        if self.p4port:
            args.extend(["-p", self.p4port])
        if self.p4client:
            args.extend(["-c", self.p4client])
        if self.credentials.username:
            args.extend(["-u", self.credentials.username])
        if self.credentials.password:
            args.extend(["-P", self.credentials.password])
        return args

    def _retry(self, cmd: Sequence[str]) -> VcsCommandResult:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                return self._run(cmd, check=True)
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.retry_interval_seconds)
        assert last_error is not None
        raise last_error


__all__ = ["PerforceClient"]
