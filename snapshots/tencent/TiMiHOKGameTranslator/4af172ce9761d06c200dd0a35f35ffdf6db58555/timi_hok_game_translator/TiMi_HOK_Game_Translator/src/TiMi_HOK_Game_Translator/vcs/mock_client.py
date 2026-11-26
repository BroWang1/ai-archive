"""供 demo/单测使用的内存 mock VCS 后端。

本后端**不进行任何网络与子进程调用**，仅在本地目录中模拟工作副本，
并将每一次操作记录到 :attr:`MockClient.history`，便于单测断言。

典型用法::

    client = MockClient(url="mock://demo", local_path="/tmp/wc")
    client.checkout()
    (Path(client.local_path) / "hello.txt").write_text("hi")
    client.add(["hello.txt"])
    client.commit(["hello.txt"], message="init")
"""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .base import VcsClient, VcsCredentials, VcsStatus


class MockClient(VcsClient):
    """适用于本地 demo 与单测的空操作 VCS 后端。"""

    cli_name = None  # 无需任何外部二进制。

    def __init__(
        self,
        url: str,
        local_path: str,
        credentials: Optional[VcsCredentials] = None,
        **kwargs: object,
    ) -> None:
        super().__init__(url=url, local_path=local_path, credentials=credentials, **kwargs)  # type: ignore[arg-type]
        self._counter = itertools.count(start=1)
        self._current_revision = "r0"
        self._staged: List[str] = []
        self.history: List[Tuple[str, tuple]] = []

    # ------------------------------------------------------------------
    def _record(self, op: str, *args: object) -> None:
        self.history.append((op, tuple(args)))

    def _ensure_local_dir(self) -> Path:
        path = Path(self.local_path or "")
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ------------------------------------------------------------------
    # VcsClient 接口实现
    # ------------------------------------------------------------------
    def checkout(self) -> VcsStatus:
        self._ensure_local_dir()
        self._current_revision = f"r{next(self._counter)}"
        self._record("checkout", self.url, self.local_path)
        return VcsStatus(revision=self._current_revision)

    def update(self, revision: Optional[str] = None) -> VcsStatus:
        self._ensure_local_dir()
        self._current_revision = revision or f"r{next(self._counter)}"
        self._record("update", self._current_revision)
        return VcsStatus(revision=self._current_revision)

    def add(self, paths: Sequence[str]) -> None:
        self._staged.extend(paths)
        self._record("add", tuple(paths))

    def commit(self, paths: Sequence[str], message: Optional[str] = None) -> VcsStatus:
        self._ensure_local_dir()
        effective = message or self.default_commit_message
        self._current_revision = f"r{next(self._counter)}"
        modified = list(dict.fromkeys([*self._staged, *paths]))
        self._staged.clear()
        self._record("commit", tuple(paths), effective, self._current_revision)
        return VcsStatus(revision=self._current_revision, modified_paths=modified)

    def revert(self, paths: Sequence[str]) -> None:
        self._staged = [p for p in self._staged if p not in paths]
        self._record("revert", tuple(paths))

    def status(self, paths: Optional[Sequence[str]] = None) -> VcsStatus:
        self._record("status", tuple(paths or ()))
        return VcsStatus(revision=self._current_revision, modified_paths=list(self._staged))

    def cleanup(self) -> None:
        self._staged.clear()
        self._record("cleanup")

    def get_revision(self) -> str:
        return self._current_revision


__all__ = ["MockClient"]
