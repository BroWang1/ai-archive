"""基于 ``git`` CLI 的 Git 后端。

仅提供工作流使用到的最小能力集（clone / pull / add / commit / push）。
分支切换、cherry-pick、submodule、LFS 等高阶特性不包含在默认实现中，
如需可通过继承拓展。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Sequence

from ..commons import DEFAULT_HTTP_RETRIES, DEFAULT_HTTP_RETRY_INTERVAL_SECONDS
from .base import VcsClient, VcsCommandResult, VcsCredentials, VcsStatus


class GitClient(VcsClient):
    """:class:`VcsClient` 的 Git 实现。"""

    cli_name = "git"

    def __init__(
        self,
        url: str,
        local_path: str,
        credentials: Optional[VcsCredentials] = None,
        *,
        branch: str = "main",
        push: bool = True,
        retries: int = DEFAULT_HTTP_RETRIES,
        retry_interval_seconds: int = DEFAULT_HTTP_RETRY_INTERVAL_SECONDS,
        **kwargs: object,
    ) -> None:
        super().__init__(url=url, local_path=local_path, credentials=credentials, **kwargs)  # type: ignore[arg-type]
        self.branch = branch
        self.push_on_commit = push
        self.retries = max(1, int(retries))
        self.retry_interval_seconds = max(0, int(retry_interval_seconds))

    # ------------------------------------------------------------------
    # VcsClient 接口实现
    # ------------------------------------------------------------------
    def checkout(self) -> VcsStatus:
        Path(self.local_path).parent.mkdir(parents=True, exist_ok=True)
        cmd = ["git", "clone", self.url, self.local_path]
        if self.branch:
            cmd.extend(["--branch", self.branch])
        self._retry(cmd, cwd=None)
        return VcsStatus(revision=self.get_revision())

    def update(self, revision: Optional[str] = None) -> VcsStatus:
        if revision:
            self._run(["git", "fetch", "origin"], check=True)
            self._run(["git", "checkout", revision], check=True)
        else:
            self._retry(["git", "pull", "--ff-only"])
        return VcsStatus(revision=self.get_revision())

    def add(self, paths: Sequence[str]) -> None:
        if not paths:
            return
        self._run(["git", "add", "--", *paths], check=True)

    def commit(self, paths: Sequence[str], message: Optional[str] = None) -> VcsStatus:
        if paths:
            self.add(paths)
        effective_msg = message or self.default_commit_message
        self._run(["git", "commit", "-m", effective_msg], check=True)
        if self.push_on_commit:
            self._retry(["git", "push", "origin", self.branch or "HEAD"])
        return VcsStatus(revision=self.get_revision(), modified_paths=list(paths))

    def revert(self, paths: Sequence[str]) -> None:
        if not paths:
            return
        self._run(["git", "checkout", "--", *paths], check=True)

    def status(self, paths: Optional[Sequence[str]] = None) -> VcsStatus:
        result = self._run(["git", "status", "--porcelain", *(paths or ())], check=False)
        modified: List[str] = []
        conflicts: List[str] = []
        for line in result.stdout.splitlines():
            if not line:
                continue
            code = line[:2]
            path = line[3:].strip()
            if "U" in code or code.strip() == "AA":
                conflicts.append(path)
            else:
                modified.append(path)
        return VcsStatus(revision=self.get_revision(), modified_paths=modified, conflicts=conflicts)

    def cleanup(self) -> None:
        # 尽力而为的恢复：中止未完成的 merge / rebase / cherry-pick，
        # 保留本地修改以便调用方检查。
        for cmd in (
            ["git", "merge", "--abort"],
            ["git", "rebase", "--abort"],
            ["git", "cherry-pick", "--abort"],
        ):
            self._run(cmd, check=False)

    def get_revision(self) -> str:
        result = self._run(["git", "rev-parse", "HEAD"], check=False)
        return result.stdout.strip()

    # ------------------------------------------------------------------
    def _retry(self, cmd: Sequence[str], *, cwd: Optional[str] = None) -> VcsCommandResult:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                return self._run(cmd, cwd=cwd, check=True)
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — VcsCommandError 既属异常后续会重新抛出
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.retry_interval_seconds)
        assert last_error is not None
        raise last_error


__all__ = ["GitClient"]
