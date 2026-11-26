"""工作流状态注册表。

框架内置一套**标准** 17 个状态（参见
:class:`TiMi_HOK_Game_Translator.commons.WorkflowState`），但任一语种 profile 只列出
实际需要的那一子集。本注册表就是运行时的 ``state_name → state_instance`` 映射，
供 :class:`~.runner.WorkflowRunner` 从 :class:`~TiMi_HOK_Game_Translator.config.LanguageProfile`
实例化完整工作流。

注册方式
--------
内置状态在导入时自行调用 :func:`register_state`；第三方状态可采同样方式，
既可在模块导入时产生副作用，也可在插件入口中延迟调用。

覆盖已有状态
------------
重复注册时必须传 ``replace=True``；这份提时可以避免无关导入静默覆盖关键状态。
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Iterable, List, Type, Union

from .state import WorkflowStateBase

logger = logging.getLogger(__name__)

# name → class-or-factory
_REGISTRY: Dict[str, Union[Type[WorkflowStateBase], Callable[[], WorkflowStateBase]]] = {}


def register_state(
    name: str,
    factory: Union[Type[WorkflowStateBase], Callable[[], WorkflowStateBase]],
    *,
    replace: bool = False,
) -> Union[Type[WorkflowStateBase], Callable[[], WorkflowStateBase]]:
    """将状态类或无参工厂注册为 ``name``。

    ``factory`` 可为类或无参可调用对象，后者方便“部分应用后再注册”。

    ``name`` 已存在时必须传 ``replace=True``，否则抛 :class:`ValueError`。
    """
    if not replace and name in _REGISTRY and _REGISTRY[name] is not factory:
        existing = _REGISTRY[name]
        existing_repr = getattr(existing, "__name__", repr(existing))
        raise ValueError(
            f"State {name!r} is already registered to {existing_repr}. "
            "Pass replace=True to override."
        )
    _REGISTRY[name] = factory
    return factory


def unregister_state(name: str) -> None:
    """从注册表中移除 ``name``（主要供测试使用）。"""
    _REGISTRY.pop(name, None)


def registered_state_names() -> List[str]:
    """返回已注册状态名称列表（排序后）。"""
    return sorted(_REGISTRY)


def build_state(name: str) -> WorkflowStateBase:
    """实例化 ``name`` 对应的状态。

    异常：
        KeyError: ``name`` 未注册。
    """
    if name not in _REGISTRY:
        raise KeyError(
            f"No workflow state registered under {name!r}. "
            f"Registered states: {registered_state_names()}."
        )
    factory = _REGISTRY[name]
    instance = factory()  # type: ignore[operator]
    if not isinstance(instance, WorkflowStateBase):
        raise TypeError(
            f"Factory for state {name!r} produced {type(instance).__name__}, "
            "which is not a WorkflowStateBase."
        )
    # 当类属性 ``name`` 未设置时，以注册时传入的名称为准。
    if not instance.name:
        instance.name = name
    return instance


def build_workflow(names: Iterable[str]) -> List[WorkflowStateBase]:
    """依次解析 ``names``，返回已实例化的工作流列表。"""
    return [build_state(name) for name in names]


__all__ = [
    "build_state",
    "build_workflow",
    "register_state",
    "registered_state_names",
    "unregister_state",
]
