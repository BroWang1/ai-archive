"""工作流业务数据的自动持久化字典。

:class:`~.states_manager.StatesManager`（管理状态完成位）与基于
``project_run_data.json`` 的**业务数据**字典成对使用：字典任意改动
都会立即写回磁盘，保证崩溃/受 SIGTERM 后能断点续跑。

:class:`AutoSaveDict` 继承 ``dict``，以产品无关的形式复现上述契约：

* 每次 ``__setitem__`` / ``update`` / ``pop`` / ``setdefault``
  都会回调 ``save_callback``；
* :attr:`non_serialisable_keys` 中的 key 仅位于内存，**不会**写入磁盘磁盘（适合
  存放 DataFrame / 文件句柄等活对象）；
* 线程安全：所有变更方法均受 ``RLock`` 保护。

本类本身不开文件，持久化交给 ``save_callback``（一般由包封的
:class:`WorkflowContext` 提供），测试时可注入内存 sink。
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Iterable, Optional, Set


class AutoSaveDict(dict):
    """每次变更后自动落盘的 ``dict``。

    字段：
        save_callback: ``() -> None`` 回调，变更后自动调用；为 ``None`` 时
            禁用自动保存（适用于初始化阶段）。
        non_serialisable_keys: 列入此集的 key，:meth:`serialisable_items`
            不会将它们包含在内。
    """

    def __init__(
        self,
        *args: Any,
        save_callback: Optional[Callable[[], None]] = None,
        non_serialisable_keys: Optional[Iterable[str]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._save_callback: Optional[Callable[[], None]] = save_callback
        self._non_serialisable: Set[str] = set(non_serialisable_keys or ())
        self._lock = threading.RLock()
        # ``_saves_enabled`` 同时作为重入保护：如果 ``save_callback``
        # 自己又修改了字典（如写时间戳），避免无限递归。
        self._saves_enabled = True
    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    def set_save_callback(self, callback: Optional[Callable[[], None]]) -> None:
        """安装或清除 ``save_callback``。"""
        with self._lock:
            self._save_callback = callback

    def add_non_serialisable_key(self, key: str) -> None:
        """将 ``key`` 标为“不写入持久化输出”。"""
        with self._lock:
            self._non_serialisable.add(key)

    @property
    def non_serialisable_keys(self) -> Set[str]:
        with self._lock:
            return set(self._non_serialisable)

    def suspend_saves(self) -> _SavesSuspended:
        """上下文管理器：``with`` 块内暂停自动保存。

        用于一个状态需要原子地更新多个 key——只触发一次保存::

            with ctx.state_data.suspend_saves():
                ctx.state_data["a"] = 1
                ctx.state_data["b"] = 2
            # 仅在此处触发一次写盘。
        """
        return _SavesSuspended(self)

    # ------------------------------------------------------------------
    # dict 变更入口——所有修改均经由 ``_touch``
    # ------------------------------------------------------------------
    def __setitem__(self, key: Any, value: Any) -> None:
        with self._lock:
            super().__setitem__(key, value)
            self._touch(key)

    def __delitem__(self, key: Any) -> None:
        with self._lock:
            super().__delitem__(key)
            self._touch(key)

    def update(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        with self._lock:
            super().update(*args, **kwargs)
            self._touch(None)

    def pop(self, key: Any, *args: Any) -> Any:
        with self._lock:
            value = super().pop(key, *args)
            self._touch(key)
            return value

    def popitem(self) -> Any:
        with self._lock:
            item = super().popitem()
            self._touch(item[0] if item else None)
            return item

    def setdefault(self, key: Any, default: Any = None) -> Any:  # type: ignore[override]
        with self._lock:
            if key in self:
                return super().__getitem__(key)
            super().__setitem__(key, default)
            self._touch(key)
            return default

    def clear(self) -> None:  # type: ignore[override]
        with self._lock:
            super().clear()
            self._touch(None)

    # ------------------------------------------------------------------
    # 持久化辅助
    # ------------------------------------------------------------------
    def serialisable_items(self) -> Dict[str, Any]:
        """返回不包含 :attr:`non_serialisable_keys` 的 dict 副本。"""
        with self._lock:
            return {
                key: value
                for key, value in self.items()
                if key not in self._non_serialisable
            }

    def _touch(self, key: Optional[Any]) -> None:
        """触发 ``save_callback``；修改非持久化 key 时不触发。"""
        if not self._saves_enabled or self._save_callback is None:
            return
        if key is not None and key in self._non_serialisable:
            return
        try:  # noqa: SIM105
            self._save_callback()
        except Exception:  # pylint: disable=broad-except  # noqa: BLE001 — 不从变更钩子抛出
            # 持久化错误由上层上下文记日志；向外抛出会弄脏未处理持久化异常的用户代码。
            pass


class _SavesSuspended:
    """:meth:`AutoSaveDict.suspend_saves` 返回的上下文管理器。"""

    def __init__(self, target: AutoSaveDict) -> None:
        self._target = target
        self._previous: bool = True

    def __enter__(self) -> AutoSaveDict:
        # 避免同一个管理器重入。
        with self._target._lock:  # noqa: SLF001 — 友元类
            self._previous = self._target._saves_enabled
            self._target._saves_enabled = False
        return self._target

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        with self._target._lock:  # noqa: SLF001
            self._target._saves_enabled = self._previous
        if exc is None and self._target._save_callback is not None:  # noqa: SLF001
            try:  # noqa: SIM105
                self._target._save_callback()  # noqa: SLF001
            except Exception:  # pylint: disable=broad-except  # noqa: BLE001
                pass


__all__ = ["AutoSaveDict"]
