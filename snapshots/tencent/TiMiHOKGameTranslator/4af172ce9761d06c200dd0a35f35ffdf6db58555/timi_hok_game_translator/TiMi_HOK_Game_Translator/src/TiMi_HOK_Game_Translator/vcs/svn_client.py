"""基于 ``svn`` CLI 的 SVN 后端。

提供工程中实际用到的核心 SVN 操作，剥离了业务耦合的内容
（项目专用操作模板、缺陷 ID 等）。重试与工作副本锁的恢复策略
简化为少量可理解的步骤；如需扩展行为，可通过继承或插入
:meth:`_run_with_retry` 实现。
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List, Optional, Sequence

from ..commons import (
    DEFAULT_HTTP_RETRIES,
    DEFAULT_HTTP_RETRY_INTERVAL_SECONDS,
    VcsCommandError,
)
from .base import VcsClient, VcsCommandResult, VcsCredentials, VcsStatus

# 匹配工作副本锁/脏状态错误的正则，不区分大小写。
_WC_LOCKED_RE = re.compile(r"E155004|is locked|previous operation has not finished", re.IGNORECASE)
_TREE_CONFLICT_RE = re.compile(r"remains in conflict|conflict discovered", re.IGNORECASE)


class SvnClient(VcsClient):
    """:class:`VcsClient` 的 SVN 实现。"""

    cli_name = "svn"

    def __init__(
        self,
        url: str,
        local_path: str,
        credentials: Optional[VcsCredentials] = None,
        *,
        retries: int = DEFAULT_HTTP_RETRIES,
        retry_interval_seconds: int = DEFAULT_HTTP_RETRY_INTERVAL_SECONDS,
        **kwargs: object,
    ) -> None:
        super().__init__(url=url, local_path=local_path, credentials=credentials, **kwargs)  # type: ignore[arg-type]
        self.retries = max(1, int(retries))
        self.retry_interval_seconds = max(0, int(retry_interval_seconds))

    # ------------------------------------------------------------------
    # VcsClient 接口实现
    # ------------------------------------------------------------------
    def checkout(self) -> VcsStatus:
        Path(self.local_path).mkdir(parents=True, exist_ok=True)
        cmd = [
            "svn", "checkout", self.url, self.local_path,
            *self._auth_args(), "--non-interactive",
        ]
        self._run_with_retry(cmd, cwd=None)
        return VcsStatus(revision=self.get_revision())

    def update(self, revision: Optional[str] = None) -> VcsStatus:
        cmd = ["svn", "update"]
        if revision:
            cmd.extend(["-r", revision])
        cmd.extend([*self._auth_args(), "--non-interactive"])
        self._run_with_retry(cmd)
        return VcsStatus(revision=self.get_revision())

    def add(self, paths: Sequence[str]) -> None:
        if not paths:
            return
        cmd = ["svn", "add", "--force", *paths, *self._auth_args(), "--non-interactive"]
        self._run(cmd, check=True)

    def commit(self, paths: Sequence[str], message: Optional[str] = None) -> VcsStatus:
        if paths:
            self.add(paths)
        cmd = [
            "svn",
            "commit",
            "-m",
            message or self.default_commit_message,
            *paths,
            *self._auth_args(),
            "--non-interactive",
        ]
        self._run_with_retry(cmd)
        return VcsStatus(revision=self.get_revision(), modified_paths=list(paths))

    def revert(self, paths: Sequence[str]) -> None:
        if not paths:
            return
        cmd = ["svn", "revert", "--recursive", *paths]
        self._run(cmd, check=True)

    def status(self, paths: Optional[Sequence[str]] = None) -> VcsStatus:
        cmd = ["svn", "status", *(paths or ())]
        result = self._run(cmd, check=False)
        modified: List[str] = []
        conflicts: List[str] = []
        for line in result.stdout.splitlines():
            if not line or line.startswith("?"):
                continue
            code = line[0]
            path = line[8:].strip() if len(line) > 8 else ""
            if code == "C":
                conflicts.append(path)
            elif code in {"M", "A", "D", "R"}:
                modified.append(path)
        return VcsStatus(revision=self.get_revision(), modified_paths=modified, conflicts=conflicts)

    def cleanup(self) -> None:
        cmd = ["svn", "cleanup", self.local_path or "."]
        self._run(cmd, check=False)

    def get_revision(self) -> str:
        result = self._run(["svn", "info", "--show-item", "revision"], check=False)
        return result.stdout.strip()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _auth_args(self) -> List[str]:
        args: List[str] = []
        if self.credentials.username:
            args.extend(["--username", self.credentials.username])
        if self.credentials.password:
            args.extend(["--password", self.credentials.password])
        return args

    def _run_with_retry(
        self, cmd: Sequence[str], *, cwd: Optional[str] = None
    ) -> VcsCommandResult:
        """运行 ``cmd``，遇到工作副本锁/树冲突时自动恢复后重试。"""
        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                return self._run(cmd, cwd=cwd, check=True)
            except VcsCommandError as exc:
                stderr = str(exc)
                if _WC_LOCKED_RE.search(stderr):
                    self.cleanup()
                elif _TREE_CONFLICT_RE.search(stderr):
                    self._run(["svn", "resolve", "--accept", "working", "--recursive",
                               self.local_path or "."], check=False)
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.retry_interval_seconds)
        assert last_error is not None
        raise last_error


__all__ = ["SvnClient"]
